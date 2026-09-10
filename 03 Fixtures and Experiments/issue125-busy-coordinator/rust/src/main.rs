use chrono::{DateTime, Duration as ChronoDuration, SecondsFormat, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use std::collections::BTreeMap;
use std::env;
use std::ffi::OsStr;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Seek, SeekFrom, Write};
use std::os::windows::ffi::OsStrExt;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::thread;
use std::time::{Duration, Instant, SystemTime};
use windows_sys::Win32::Foundation::CloseHandle;
use windows_sys::Win32::Storage::FileSystem::{
    MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH, MoveFileExW,
};
use windows_sys::Win32::System::Threading::{
    GetExitCodeProcess, OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION,
};

const LOCK_TIMEOUT: Duration = Duration::from_secs(2);
const LOCK_STALE: Duration = Duration::from_secs(15);
const LOCK_RETRY: Duration = Duration::from_millis(10);
const REPLACE_TIMEOUT: Duration = Duration::from_millis(500);
const REPLACE_RETRY: Duration = Duration::from_millis(10);
const TEMP_STALE: Duration = Duration::from_secs(60);
const MAX_SWEEP_TEMP_ITEMS: usize = 32;
const DEFAULT_LEASE_SECONDS: i64 = 240;
const MAX_LEASE_SECONDS: i64 = 240;
const MAX_OPERATIONS: usize = 512;

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
struct Claim {
    actor: String,
    scope: String,
    timestamp: String,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize, PartialEq)]
struct Job {
    #[serde(default)]
    job_id: String,
    #[serde(default)]
    scope: String,
    #[serde(default)]
    state: String,
    #[serde(default)]
    owner: Option<String>,
    #[serde(default)]
    lease_expires_at: Option<String>,
    #[serde(default)]
    claim_timestamp: Option<String>,
    #[serde(default)]
    checkpoint: Option<String>,
    #[serde(default)]
    updated_at: String,
    #[serde(flatten)]
    extra: BTreeMap<String, Value>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct Operation {
    at: String,
    signature: Value,
    result: Value,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct Coordinator {
    #[serde(default = "coordinator_version")]
    version: u32,
    #[serde(default)]
    jobs: BTreeMap<String, Job>,
    #[serde(default)]
    operations: BTreeMap<String, Operation>,
    #[serde(flatten)]
    extra: BTreeMap<String, Value>,
}

impl Default for Coordinator {
    fn default() -> Self {
        Self {
            version: coordinator_version(),
            jobs: BTreeMap::new(),
            operations: BTreeMap::new(),
            extra: BTreeMap::new(),
        }
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct StoreFile {
    claims: Vec<Claim>,
    #[serde(default)]
    coordinator: Coordinator,
    #[serde(flatten)]
    extra: BTreeMap<String, Value>,
}

fn coordinator_version() -> u32 {
    1
}

struct StoreLock {
    path: PathBuf,
    file: Option<File>,
}

impl StoreLock {
    fn acquire(store: &Path) -> io::Result<Self> {
        let path = PathBuf::from(format!("{}.lock", store.display()));
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let deadline = Instant::now() + LOCK_TIMEOUT;
        loop {
            match OpenOptions::new().write(true).create_new(true).open(&path) {
                Ok(mut file) => {
                    writeln!(file, "{}", std::process::id())?;
                    return Ok(Self {
                        path,
                        file: Some(file),
                    });
                }
                Err(error)
                    if matches!(
                        error.kind(),
                        io::ErrorKind::AlreadyExists | io::ErrorKind::PermissionDenied
                    ) =>
                {
                    let stale = fs::metadata(&path)
                        .and_then(|m| m.modified())
                        .ok()
                        .and_then(|m| SystemTime::now().duration_since(m).ok())
                        .is_some_and(|age| age > LOCK_STALE);
                    if stale {
                        let _ = fs::remove_file(&path);
                        continue;
                    }
                    if Instant::now() >= deadline {
                        return Err(io::Error::new(
                            io::ErrorKind::WouldBlock,
                            "busy store locked by another writer",
                        ));
                    }
                    thread::sleep(LOCK_RETRY);
                }
                Err(error) => return Err(error),
            }
        }
    }
}

impl Drop for StoreLock {
    fn drop(&mut self) {
        self.file.take();
        let _ = fs::remove_file(&self.path);
    }
}

fn default_store() -> PathBuf {
    if let Ok(path) = env::var("BUSY_STORE_PATH") {
        return PathBuf::from(path);
    }
    if let Ok(path) = env::var("MCP_BUSY_STORE_PATH") {
        return PathBuf::from(path);
    }
    let base = env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(env::temp_dir);
    base.join("ChatGPTMcpClean")
        .join(".state")
        .join("busy-claims.json")
}

fn empty_state() -> StoreFile {
    StoreFile {
        claims: Vec::new(),
        coordinator: Coordinator::default(),
        extra: BTreeMap::new(),
    }
}

fn load(store: &Path) -> Result<StoreFile, String> {
    match fs::read_to_string(store) {
        Ok(raw) => {
            let value: Value = serde_json::from_str(&raw)
                .map_err(|e| format!("cannot safely read BUSY store: {e}"))?;
            if !value.get("claims").is_some_and(Value::is_array) {
                return Err("invalid BUSY store shape".to_string());
            }
            let mut state: StoreFile = serde_json::from_value(value)
                .map_err(|e| format!("cannot safely read BUSY store: {e}"))?;

            let mut claims_by_scope: BTreeMap<String, Claim> = BTreeMap::new();
            for claim in state.claims {
                let scope = canonical_scope(&claim.scope)?;
                let normalized = Claim {
                    actor: claim.actor,
                    scope: scope.clone(),
                    timestamp: claim.timestamp,
                };
                match claims_by_scope.get(&scope) {
                    None => {
                        claims_by_scope.insert(scope, normalized);
                    }
                    Some(previous) if previous.actor != normalized.actor => {
                        return Err(format!(
                            "conflicting BUSY claims canonicalize to one scope: {scope}"
                        ));
                    }
                    Some(previous) if normalized.timestamp > previous.timestamp => {
                        claims_by_scope.insert(scope, normalized);
                    }
                    Some(_) => {}
                }
            }
            state.claims = claims_by_scope.into_values().collect();
            state.coordinator.version = coordinator_version();
            Ok(state)
        }
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(empty_state()),
        Err(e) => Err(format!("cannot safely read BUSY store: {e}")),
    }
}

fn wide_null(value: &OsStr) -> Vec<u16> {
    value.encode_wide().chain(std::iter::once(0)).collect()
}

fn persist(store: &Path, state: &StoreFile) -> Result<(), String> {
    if let Some(parent) = store.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let tmp = PathBuf::from(format!("{}.{}.tmp", store.display(), std::process::id()));
    let mut bytes = serde_json::to_vec_pretty(state).map_err(|e| e.to_string())?;
    bytes.push(b'\n');
    fs::write(&tmp, &bytes).map_err(|e| e.to_string())?;
    let src = wide_null(tmp.as_os_str());
    let dst = wide_null(store.as_os_str());
    let deadline = Instant::now() + REPLACE_TIMEOUT;
    loop {
        let ok = unsafe {
            MoveFileExW(
                src.as_ptr(),
                dst.as_ptr(),
                MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
            )
        };
        if ok != 0 {
            return Ok(());
        }
        let error = io::Error::last_os_error();
        if !matches!(error.raw_os_error(), Some(5 | 32)) {
            let _ = fs::remove_file(&tmp);
            return Err(format!("cannot replace BUSY store: {error}"));
        }
        if Instant::now() >= deadline {
            // A Windows reader can deny delete sharing while still allowing writes.
            // The coordinator lock serializes writers, so preserve progress by
            // overwriting the existing file in place when rename cannot ever win.
            let mut file = OpenOptions::new()
                .write(true)
                .open(store)
                .map_err(|fallback| {
                    format!(
                        "cannot replace BUSY store: {error}; in-place fallback failed: {fallback}"
                    )
                })?;
            file.seek(SeekFrom::Start(0)).map_err(|e| e.to_string())?;
            file.write_all(&bytes).map_err(|e| e.to_string())?;
            file.set_len(bytes.len() as u64)
                .map_err(|e| e.to_string())?;
            file.sync_all().map_err(|e| e.to_string())?;
            let _ = fs::remove_file(&tmp);
            return Ok(());
        }
        thread::sleep(REPLACE_RETRY);
    }
}

fn now_iso() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true)
}

fn capped_lease_seconds(value: i64) -> i64 {
    value.clamp(1, MAX_LEASE_SECONDS)
}

fn capped_lease_expiry(claim_timestamp: &str, raw_lease: Option<&str>) -> Result<String, String> {
    let claim_time = DateTime::parse_from_rfc3339(claim_timestamp)
        .map_err(|e| format!("invalid BUSY claim timestamp: {e}"))?
        .with_timezone(&Utc);
    let cap = claim_time + ChronoDuration::seconds(MAX_LEASE_SECONDS);
    let deadline = raw_lease
        .and_then(|value| DateTime::parse_from_rfc3339(value).ok())
        .map(|value| value.with_timezone(&Utc))
        .map(|value| std::cmp::min(value, cap))
        .unwrap_or(cap);
    Ok(deadline.to_rfc3339_opts(SecondsFormat::Millis, true))
}

fn canonical_repo_scope_prefix(raw: &str) -> Option<&'static str> {
    match raw.to_ascii_lowercase().as_str() {
        "regression-research" | "organicoverlords/regression-research" => {
            Some("regression-research")
        }
        "agents" | "organicoverlords/agents" => Some("agents"),
        _ => None,
    }
}

fn canonical_scope(raw: &str) -> Result<String, String> {
    let scope = raw.trim().to_string();
    if scope.is_empty() {
        return Err("scope must not be empty".into());
    }
    let path = Path::new(&scope);
    if path.is_absolute() {
        // Match Python's Windows normcase/normpath behavior without requiring
        // the claimed path to exist.
        let normalized = path
            .components()
            .collect::<PathBuf>()
            .to_string_lossy()
            .replace('/', "\\")
            .to_ascii_lowercase();
        return Ok(normalized);
    }

    // Keep arbitrary logical scopes opaque. Normalize only known repository
    // identities so owner-qualified and short spellings share one collision key.
    if let Some((repo, suffix)) = scope.split_once(':') {
        if let Some(canonical_repo) = canonical_repo_scope_prefix(repo) {
            return Ok(format!("{canonical_repo}:{suffix}"));
        }
    } else if let Some(canonical_repo) = canonical_repo_scope_prefix(&scope) {
        return Ok(canonical_repo.to_string());
    }
    Ok(scope)
}

fn ambiguous_relative_path_scope(raw: &str) -> bool {
    let scope = raw.trim();
    if scope.is_empty() || Path::new(scope).is_absolute() {
        return false;
    }
    // Bare repo-relative paths have no repository identity. Requiring an
    // absolute path or a namespaced logical scope prevents alias claims such as
    // `scripts/x.py` and `p3:file:scripts/x.py` from bypassing exact collision.
    (scope.contains('/') || scope.contains('\\')) && !scope.contains(':')
}

const CLAIM_ACTOR_HARNESSES: [&str; 6] = [
    "ChatGPT",
    "Codex",
    "Claude",
    "OpenCode",
    "CommandCode",
    "Traycer",
];

fn validate_claim_actor(raw: &str) -> Result<&str, String> {
    let actor = raw.trim();
    for harness in CLAIM_ACTOR_HARNESSES {
        if let Some(rest) = actor.strip_prefix(harness) {
            let mut chars = rest.chars();
            if matches!(chars.next(), Some('-' | ':' | '/')) && !chars.as_str().trim().is_empty() {
                return Ok(actor);
            }
        }
    }
    Err("claim actor must be <harness><separator><task/session suffix>".into())
}

fn claim_index(state: &StoreFile, scope: &str) -> Option<usize> {
    state.claims.iter().position(|claim| claim.scope == scope)
}

fn compact_job(job: &Job) -> Value {
    let mut map = Map::new();
    map.insert("scope".into(), json!(job.scope));
    map.insert("state".into(), json!(job.state));
    if let Some(owner) = &job.owner {
        map.insert("owner".into(), json!(owner));
    }
    if let Some(checkpoint) = &job.checkpoint {
        map.insert("checkpoint".into(), json!(checkpoint));
    }
    if let Some(lease) = &job.lease_expires_at {
        map.insert("lease_expires_at".into(), json!(lease));
    }
    map.insert("updated_at".into(), json!(job.updated_at));
    Value::Object(map)
}

fn normalize_jobs(state: &mut StoreFile) -> Result<bool, String> {
    let mut raw_jobs: BTreeMap<String, Job> = BTreeMap::new();
    for (raw_scope, raw_job) in state.coordinator.jobs.clone() {
        let source_scope = if raw_job.scope.is_empty() {
            raw_scope.as_str()
        } else {
            raw_job.scope.as_str()
        };
        let scope = canonical_scope(source_scope)?;
        // BTreeMap iteration makes alias collapse deterministic across runs.
        raw_jobs.insert(scope, raw_job);
    }

    let mut normalized = BTreeMap::new();
    for claim in &state.claims {
        let scope = claim.scope.clone();
        let mut job = raw_jobs.get(&scope).cloned().unwrap_or_default();
        let raw_lease = job.lease_expires_at.clone();
        job.job_id = scope.clone();
        job.scope = scope.clone();
        job.state = "active".into();
        job.owner = Some(claim.actor.clone());
        job.lease_expires_at = Some(capped_lease_expiry(&claim.timestamp, raw_lease.as_deref())?);
        job.claim_timestamp = Some(claim.timestamp.clone());
        job.updated_at = claim.timestamp.clone();
        normalized.insert(scope, job);
    }
    let changed = normalized != state.coordinator.jobs;
    state.coordinator.jobs = normalized;
    Ok(changed)
}

fn snapshot_state(
    state: &StoreFile,
    actor: Option<&str>,
    raw_scope: Option<&str>,
    limit: usize,
    expired: &[Value],
) -> Result<Value, String> {
    let limit = limit.clamp(1, 32);
    let mut claims = state.claims.clone();
    claims.sort_by(|a, b| a.scope.cmp(&b.scope));
    let mut active: Vec<&Job> = state
        .coordinator
        .jobs
        .values()
        .filter(|job| job.state == "active")
        .collect();
    active.sort_by(|a, b| a.scope.cmp(&b.scope));
    let managed: std::collections::BTreeSet<&str> =
        active.iter().map(|job| job.scope.as_str()).collect();
    let legacy_only: Vec<Claim> = claims
        .iter()
        .filter(|claim| !managed.contains(claim.scope.as_str()))
        .cloned()
        .collect();

    let mut result = Map::new();
    result.insert("ok".into(), json!(true));
    result.insert(
        "counts".into(),
        json!({
            "active": active.len(),
            "claims": claims.len(),
            "legacy_only_claims": legacy_only.len(),
        }),
    );
    result.insert(
        "legacy_only_claims".into(),
        json!(legacy_only.into_iter().take(limit).collect::<Vec<_>>()),
    );
    if let Some(actor) = actor {
        result.insert(
            "owned".into(),
            Value::Array(
                active
                    .iter()
                    .copied()
                    .filter(|job| job.owner.as_deref() == Some(actor))
                    .take(limit)
                    .map(compact_job)
                    .collect(),
            ),
        );
        result.insert(
            "active_other".into(),
            Value::Array(
                active
                    .iter()
                    .copied()
                    .filter(|job| job.owner.as_deref() != Some(actor))
                    .take(limit)
                    .map(compact_job)
                    .collect(),
            ),
        );
    } else {
        result.insert(
            "active".into(),
            Value::Array(active.into_iter().take(limit).map(compact_job).collect()),
        );
    }
    if let Some(raw_scope) = raw_scope {
        let scope = canonical_scope(raw_scope)?;
        let job = state
            .coordinator
            .jobs
            .get(&scope)
            .map(|job| json!(job))
            .unwrap_or(Value::Null);
        let claim = claim_index(state, &scope)
            .map(|index| json!(&state.claims[index]))
            .unwrap_or(Value::Null);
        result.insert(
            "focus".into(),
            json!({"scope": scope, "job": job, "claim": claim}),
        );
    }
    if !expired.is_empty() {
        result.insert(
            "expired".into(),
            Value::Array(expired.iter().take(limit).cloned().collect()),
        );
    }
    Ok(Value::Object(result))
}

fn prune_operations(state: &mut StoreFile) {
    if state.coordinator.operations.len() <= MAX_OPERATIONS {
        return;
    }
    let mut ordered: Vec<(String, String)> = state
        .coordinator
        .operations
        .iter()
        .map(|(key, op)| (key.clone(), op.at.clone()))
        .collect();
    ordered.sort_by(|a, b| a.1.cmp(&b.1));
    let remove_count = state.coordinator.operations.len() - MAX_OPERATIONS;
    for (key, _) in ordered.into_iter().take(remove_count) {
        state.coordinator.operations.remove(&key);
    }
}

fn idempotent(state: &StoreFile, operation_id: Option<&str>, signature: &Value) -> Option<Value> {
    let id = operation_id?;
    let current = state.coordinator.operations.get(id)?;
    if &current.signature != signature {
        return Some(json!({"ok": false, "reason": "idempotency_conflict", "operation_id": id}));
    }
    Some(current.result.clone())
}

fn remember(
    state: &mut StoreFile,
    operation_id: Option<&str>,
    signature: Value,
    result: Value,
) -> Value {
    if let Some(id) = operation_id {
        state.coordinator.operations.insert(
            id.to_string(),
            Operation {
                at: now_iso(),
                signature,
                result: result.clone(),
            },
        );
        prune_operations(state);
    }
    result
}

fn remove_scope_metadata(state: &mut StoreFile, scope: &str) {
    state.coordinator.jobs.remove(scope);
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum WriterProcessState {
    Live,
    Dead,
    Unknown,
}

fn writer_process_state(pid: u32) -> WriterProcessState {
    if pid == 0 {
        return WriterProcessState::Unknown;
    }
    let handle = unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid) };
    if handle.is_null() {
        return if io::Error::last_os_error().raw_os_error() == Some(87) {
            WriterProcessState::Dead
        } else {
            WriterProcessState::Unknown
        };
    }

    let mut exit_code = 0u32;
    let ok = unsafe { GetExitCodeProcess(handle, &mut exit_code) };
    unsafe {
        CloseHandle(handle);
    }
    if ok == 0 {
        WriterProcessState::Unknown
    } else if exit_code == 259 {
        WriterProcessState::Live
    } else {
        WriterProcessState::Dead
    }
}

fn sweep_stale_temp_files(store: &Path) -> Value {
    let mut removed_count = 0usize;
    let mut removed_files = Vec::new();
    let Some(parent) = store.parent() else {
        return json!({"removed_temp_count": 0, "removed_temp_files": []});
    };
    let Some(store_name) = store.file_name().and_then(OsStr::to_str) else {
        return json!({"removed_temp_count": 0, "removed_temp_files": []});
    };
    let prefix = format!("{store_name}.");
    let Ok(entries) = fs::read_dir(parent) else {
        return json!({"removed_temp_count": 0, "removed_temp_files": []});
    };
    let now = SystemTime::now();
    let mut candidates: Vec<_> = entries.filter_map(Result::ok).collect();
    candidates.sort_by_key(|entry| entry.file_name());

    for entry in candidates {
        let file_name = entry.file_name();
        let Some(name) = file_name.to_str() else {
            continue;
        };
        let Some(raw_pid) = name
            .strip_prefix(&prefix)
            .and_then(|value| value.strip_suffix(".tmp"))
        else {
            continue;
        };
        let Ok(pid) = raw_pid.parse::<u32>() else {
            continue;
        };
        if pid == 0 {
            continue;
        }
        let Ok(file_type) = entry.file_type() else {
            continue;
        };
        if !file_type.is_file() {
            continue;
        }
        let Ok(metadata) = entry.metadata() else {
            continue;
        };
        let Ok(modified) = metadata.modified() else {
            continue;
        };
        let Ok(age) = now.duration_since(modified) else {
            continue;
        };
        if age < TEMP_STALE || writer_process_state(pid) != WriterProcessState::Dead {
            continue;
        }
        if fs::remove_file(entry.path()).is_err() {
            continue;
        }
        removed_count += 1;
        if removed_files.len() < MAX_SWEEP_TEMP_ITEMS {
            removed_files.push(json!({"name": name, "pid": pid}));
        }
    }

    json!({"removed_temp_count": removed_count, "removed_temp_files": removed_files})
}

fn sweep_expired(state: &mut StoreFile) -> (Vec<Value>, bool) {
    let now = Utc::now();
    let scopes: Vec<String> = state.coordinator.jobs.keys().cloned().collect();
    let mut expired = Vec::new();
    let mut changed = false;
    for scope in scopes {
        let (job_state, owner, lease, checkpoint) = match state.coordinator.jobs.get(&scope) {
            Some(job) => (
                job.state.clone(),
                job.owner.clone(),
                job.lease_expires_at.clone(),
                job.checkpoint.clone(),
            ),
            None => continue,
        };
        if job_state != "active" {
            continue;
        }
        let (Some(owner), Some(lease)) = (owner, lease) else {
            continue;
        };
        let Ok(deadline) = DateTime::parse_from_rfc3339(&lease) else {
            continue;
        };
        if deadline.with_timezone(&Utc) > now {
            continue;
        }
        let current = claim_index(state, &scope).map(|index| state.claims[index].clone());
        if current.as_ref().is_some_and(|claim| claim.actor == owner) {
            state.claims.retain(|claim| claim.scope != scope);
        }
        remove_scope_metadata(state, &scope);
        expired.push(json!({"scope": scope, "previous_owner": owner, "checkpoint": checkpoint}));
        changed = true;
    }
    (expired, changed)
}

#[derive(Default)]
struct Options {
    operation_id: Option<String>,
    checkpoint: Option<String>,
    lease_seconds: i64,
    limit: usize,
    expected_claim_timestamp: Option<String>,
}

fn parse_snapshot_options(
    args: &[String],
) -> Result<(Option<String>, Option<String>, usize), String> {
    let mut actor = None;
    let mut scope = None;
    let mut limit = 8_i64;
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--actor" => {
                index += 1;
                actor = Some(args.get(index).ok_or("--actor requires a value")?.clone());
            }
            "--scope" => {
                index += 1;
                scope = Some(args.get(index).ok_or("--scope requires a value")?.clone());
            }
            "--limit" => {
                index += 1;
                limit = args
                    .get(index)
                    .ok_or("--limit requires a value")?
                    .parse::<i64>()
                    .map_err(|_| "invalid --limit")?;
            }
            other => return Err(format!("unknown option: {other}")),
        }
        index += 1;
    }
    Ok((actor, scope, limit.clamp(1, 32) as usize))
}

fn parse_options(
    args: &[String],
    allow_lease: bool,
    allow_checkpoint: bool,
    allow_recovery: bool,
) -> Result<Options, String> {
    let mut options = Options {
        lease_seconds: DEFAULT_LEASE_SECONDS,
        ..Options::default()
    };
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--operation-id" => {
                index += 1;
                options.operation_id = Some(
                    args.get(index)
                        .ok_or("--operation-id requires a value")?
                        .clone(),
                );
            }
            "--checkpoint" if allow_checkpoint => {
                index += 1;
                options.checkpoint = Some(
                    args.get(index)
                        .ok_or("--checkpoint requires a value")?
                        .clone(),
                );
            }
            "--lease-seconds" if allow_lease => {
                index += 1;
                options.lease_seconds = args
                    .get(index)
                    .ok_or("--lease-seconds requires a value")?
                    .parse::<i64>()
                    .map_err(|_| "invalid --lease-seconds")?;
                if options.lease_seconds <= 0 {
                    return Err("--lease-seconds must be positive".into());
                }
            }
            "--expected-claim-timestamp" if allow_recovery => {
                index += 1;
                options.expected_claim_timestamp = Some(
                    args.get(index)
                        .ok_or("--expected-claim-timestamp requires a value")?
                        .clone(),
                );
            }
            other => return Err(format!("unknown option: {other}")),
        }
        index += 1;
    }
    if allow_lease {
        options.lease_seconds = capped_lease_seconds(options.lease_seconds);
    }
    Ok(options)
}

fn signature(command: &str, actor: Option<&str>, scope: &str, options: &Options) -> Value {
    let mut map = Map::new();
    map.insert("command".into(), json!(command));
    if let Some(actor) = actor {
        map.insert("actor".into(), json!(actor));
    }
    map.insert("scope".into(), json!(scope));
    if matches!(command, "claim" | "heartbeat") {
        map.insert("lease_seconds".into(), json!(options.lease_seconds));
    }
    if let Some(checkpoint) = &options.checkpoint {
        map.insert("checkpoint".into(), json!(checkpoint));
    }
    Value::Object(map)
}

fn operate(
    store: &Path,
    command: &str,
    actor: Option<&str>,
    raw_scope: Option<&str>,
    options: &Options,
) -> Result<Value, String> {
    let _lock = StoreLock::acquire(store).map_err(|e| e.to_string())?;
    let mut state = load(store)?;
    let normalized = normalize_jobs(&mut state)?;
    let (swept, sweep_changed) = sweep_expired(&mut state);
    let state_changed = normalized || sweep_changed;

    if command == "list" {
        if state_changed {
            persist(store, &state)?;
        }
        state.claims.sort_by(|a, b| a.scope.cmp(&b.scope));
        return Ok(json!({"claims": state.claims}));
    }
    if command == "snapshot" {
        if state_changed {
            persist(store, &state)?;
        }
        return snapshot_state(&state, actor, raw_scope, options.limit, &swept);
    }
    if command == "sweep" {
        let temp_sweep = sweep_stale_temp_files(store);
        if state_changed {
            persist(store, &state)?;
        }
        return Ok(json!({
            "ok": true,
            "expired": swept,
            "removed_temp_count": temp_sweep["removed_temp_count"],
            "removed_temp_files": temp_sweep["removed_temp_files"],
        }));
    }

    let scope = canonical_scope(raw_scope.ok_or("scope required")?)?;
    if command == "recover" {
        let expected_owner = actor.ok_or("expected owner required")?;
        let expected_timestamp = options
            .expected_claim_timestamp
            .as_ref()
            .ok_or("--expected-claim-timestamp required")?;
        let sig = json!({
            "command": command,
            "expected_owner": expected_owner,
            "scope": scope,
            "expected_claim_timestamp": expected_timestamp,
        });
        if let Some(replay) = idempotent(&state, options.operation_id.as_deref(), &sig) {
            if state_changed {
                persist(store, &state)?;
            }
            return Ok(replay);
        }
        let current = claim_index(&state, &scope).map(|index| state.claims[index].clone());
        let result = match current {
            None => json!({"ok": false, "reason": "scope_not_claimed"}),
            Some(claim)
                if claim.actor != expected_owner || claim.timestamp != *expected_timestamp =>
            {
                json!({"ok": false, "reason": "claim_changed", "claim": claim})
            }
            Some(claim) => {
                state.claims.retain(|item| item.scope != scope);
                let checkpoint = state
                    .coordinator
                    .jobs
                    .get(&scope)
                    .and_then(|job| job.checkpoint.clone());
                remove_scope_metadata(&mut state, &scope);
                let mut value = json!({"ok": true, "recovered": claim});
                if let (Some(checkpoint), Some(map)) = (checkpoint, value.as_object_mut()) {
                    map.insert("checkpoint".into(), json!(checkpoint));
                }
                value
            }
        };
        let result = remember(&mut state, options.operation_id.as_deref(), sig, result);
        persist(store, &state)?;
        return Ok(result);
    }

    if command == "inspect" {
        if state_changed {
            persist(store, &state)?;
        }
        let claim = claim_index(&state, &scope).map(|index| state.claims[index].clone());
        return Ok(json!({"ok": true, "job": state.coordinator.jobs.get(&scope), "claim": claim}));
    }

    let actor = actor.ok_or("actor required")?;
    let actor = if matches!(command, "claim" | "heartbeat") {
        validate_claim_actor(actor)?
    } else {
        actor
    };
    let sig = signature(command, Some(actor), &scope, options);
    if let Some(replay) = idempotent(&state, options.operation_id.as_deref(), &sig) {
        if state_changed {
            persist(store, &state)?;
        }
        return Ok(replay);
    }
    let current = claim_index(&state, &scope).map(|index| state.claims[index].clone());
    let existing = state.coordinator.jobs.get(&scope).cloned();
    let result = match command {
        "claim" => {
            if current.is_none()
                && ambiguous_relative_path_scope(raw_scope.ok_or("scope required")?)
            {
                json!({
                    "ok": false,
                    "reason": "ambiguous_relative_path_scope",
                    "scope": scope,
                    "guidance": "use an absolute filesystem path or a namespaced logical scope such as <repo>:file:<path>"
                })
            } else if let Some(claim) = current.as_ref().filter(|claim| claim.actor != actor) {
                json!({"ok": false, "reason": "scope_already_claimed", "claim": claim})
            } else {
                let timestamp = now_iso();
                let claim = Claim {
                    actor: actor.into(),
                    scope: scope.clone(),
                    timestamp: timestamp.clone(),
                };
                state.claims.retain(|item| item.scope != scope);
                state.claims.push(claim.clone());
                let deadline = Utc::now() + ChronoDuration::seconds(options.lease_seconds);
                let checkpoint = options
                    .checkpoint
                    .clone()
                    .or_else(|| existing.as_ref().and_then(|job| job.checkpoint.clone()));
                state.coordinator.jobs.insert(
                    scope.clone(),
                    Job {
                        job_id: scope.clone(),
                        scope: scope.clone(),
                        state: "active".into(),
                        owner: Some(actor.into()),
                        lease_expires_at: Some(
                            deadline.to_rfc3339_opts(SecondsFormat::Millis, true),
                        ),
                        claim_timestamp: Some(timestamp.clone()),
                        checkpoint,
                        updated_at: timestamp,
                        extra: BTreeMap::new(),
                    },
                );
                json!({"ok": true, "claim": claim})
            }
        }
        "heartbeat" => match current {
            None => json!({"ok": false, "reason": "scope_not_claimed"}),
            Some(claim) if claim.actor != actor => {
                json!({"ok": false, "reason": "claim_belongs_to_another_actor", "claim": claim})
            }
            Some(mut claim) => {
                let timestamp = now_iso();
                claim.timestamp = timestamp.clone();
                if let Some(index) = claim_index(&state, &scope) {
                    state.claims[index] = claim.clone();
                }
                let deadline = Utc::now() + ChronoDuration::seconds(options.lease_seconds);
                let checkpoint = options
                    .checkpoint
                    .clone()
                    .or_else(|| existing.as_ref().and_then(|job| job.checkpoint.clone()));
                state.coordinator.jobs.insert(
                    scope.clone(),
                    Job {
                        job_id: scope.clone(),
                        scope: scope.clone(),
                        state: "active".into(),
                        owner: Some(actor.into()),
                        lease_expires_at: Some(
                            deadline.to_rfc3339_opts(SecondsFormat::Millis, true),
                        ),
                        claim_timestamp: Some(timestamp.clone()),
                        checkpoint,
                        updated_at: timestamp,
                        extra: BTreeMap::new(),
                    },
                );
                json!({"ok": true, "claim": claim})
            }
        },
        "release" => match current {
            None => json!({"ok": false, "reason": "scope_not_claimed"}),
            Some(claim) if claim.actor != actor => {
                json!({"ok": false, "reason": "claim_belongs_to_another_actor", "claim": claim})
            }
            Some(claim) => {
                state.claims.retain(|item| item.scope != scope);
                remove_scope_metadata(&mut state, &scope);
                let mut value = json!({"ok": true, "released": claim});
                if let (Some(checkpoint), Some(map)) = (
                    options.checkpoint.clone().filter(|value| !value.is_empty()),
                    value.as_object_mut(),
                ) {
                    map.insert("checkpoint".into(), json!(checkpoint));
                }
                value
            }
        },
        _ => return Err(format!("unknown command: {command}")),
    };
    let result = remember(&mut state, options.operation_id.as_deref(), sig, result);
    persist(store, &state)?;
    Ok(result)
}

fn print_json(value: &Value) -> Result<(), String> {
    println!(
        "{}",
        serde_json::to_string(value).map_err(|e| e.to_string())?
    );
    Ok(())
}

fn run() -> Result<(), String> {
    let mut raw: Vec<String> = env::args().skip(1).collect();
    let store = if raw.first().is_some_and(|arg| arg == "--store") {
        if raw.len() < 3 {
            return Err("usage: busy-rs [--store PATH] <command> ...".into());
        }
        let path = PathBuf::from(raw[1].clone());
        raw.drain(0..2);
        path
    } else {
        default_store()
    };
    let command = raw.first().ok_or("usage: busy-rs [--store PATH] <list|sweep|snapshot|recover|inspect|claim|heartbeat|release> ...")?.clone();
    raw.remove(0);
    if command == "snapshot" {
        let (actor, scope, limit) = parse_snapshot_options(&raw)?;
        let options = Options {
            limit,
            ..Options::default()
        };
        return print_json(&operate(
            &store,
            &command,
            actor.as_deref(),
            scope.as_deref(),
            &options,
        )?);
    }
    if matches!(command.as_str(), "list" | "sweep") {
        if !raw.is_empty() {
            return Err(format!("usage: busy-rs {command}"));
        }
        return print_json(&operate(&store, &command, None, None, &Options::default())?);
    }
    if command == "recover" {
        if raw.len() < 2 {
            return Err("usage: busy-rs recover <expected-owner> <scope> --expected-claim-timestamp TIMESTAMP [--operation-id ID]".into());
        }
        let actor = raw.remove(0);
        let scope = raw.remove(0);
        let options = parse_options(&raw, false, false, true)?;
        if options.expected_claim_timestamp.is_none() {
            return Err("--expected-claim-timestamp required".into());
        }
        return print_json(&operate(
            &store,
            &command,
            Some(&actor),
            Some(&scope),
            &options,
        )?);
    }
    if command == "inspect" {
        if raw.is_empty() {
            return Err("usage: busy-rs inspect <scope> [--operation-id ID]".into());
        }
        let first = raw.remove(0);
        let scope = if !raw.is_empty() && !raw[0].starts_with("--") {
            raw.remove(0)
        } else {
            first
        };
        let options = parse_options(&raw, false, false, false)?;
        return print_json(&operate(&store, &command, None, Some(&scope), &options)?);
    }
    if !matches!(command.as_str(), "claim" | "heartbeat" | "release") {
        return Err(format!("unknown command: {command}"));
    }
    if raw.len() < 2 {
        return Err(format!(
            "usage: busy-rs {command} <actor> <scope> [options]"
        ));
    }
    let actor = raw.remove(0);
    let scope = raw.remove(0);
    let options = parse_options(
        &raw,
        matches!(command.as_str(), "claim" | "heartbeat"),
        true,
        false,
    )?;
    print_json(&operate(
        &store,
        &command,
        Some(&actor),
        Some(&scope),
        &options,
    )?)
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            if error.contains("locked by another writer") {
                eprintln!(
                    "{}",
                    json!({"ok": false, "reason": "store_locked", "error": error})
                );
                ExitCode::from(75)
            } else {
                eprintln!("{error}");
                ExitCode::from(1)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn canonical_scope_is_stable_and_trimmed() {
        assert_eq!(canonical_scope("  repo#125:job  ").unwrap(), "repo#125:job");
        assert!(canonical_scope("   ").is_err());
    }

    #[test]
    fn canonical_scope_collides_known_repository_aliases() {
        assert_eq!(
            canonical_scope("regression-research:git-ref:refs/heads/topic").unwrap(),
            canonical_scope("organicoverlords/regression-research:git-ref:refs/heads/topic")
                .unwrap(),
        );
        assert_eq!(
            canonical_scope("agents:file:RULES.md").unwrap(),
            canonical_scope("organicoverlords/agents:file:RULES.md").unwrap(),
        );
        assert_eq!(
            canonical_scope("other/repo:file:x").unwrap(),
            "other/repo:file:x"
        );
    }

    #[test]
    fn ambiguous_relative_path_scope_requires_namespace_or_absolute_path() {
        assert!(ambiguous_relative_path_scope("scripts/ci/job.py"));
        assert!(ambiguous_relative_path_scope(r"scripts\ci\job.py"));
        assert!(!ambiguous_relative_path_scope("p3:file:scripts/ci/job.py"));
        assert!(!ambiguous_relative_path_scope(r"C:\Repo\scripts\ci\job.py"));
        assert!(!ambiguous_relative_path_scope("p3:runtime:omen:lane1"));
    }

    #[test]
    fn canonical_scope_collides_absolute_windows_path_aliases() {
        let plain = r"C:\Temp\BusyAlias\scope.txt";
        let dotted = r"C:\Temp\BusyAlias\.\scope.txt";
        let slash_case = r"c:/temp/busyalias/scope.txt";
        assert_eq!(
            canonical_scope(plain).unwrap(),
            canonical_scope(dotted).unwrap()
        );
        assert_eq!(
            canonical_scope(plain).unwrap(),
            canonical_scope(slash_case).unwrap()
        );
    }

    #[test]
    fn claim_actor_requires_harness_and_suffix() {
        for actor in [
            "ChatGPT-task-1",
            "Codex:session-a",
            "Claude/run-7",
            "OpenCode-x",
            "CommandCode-y",
            "Traycer-z",
        ] {
            assert_eq!(validate_claim_actor(actor).unwrap(), actor);
        }
        for actor in [
            "Harbor", "Ember", "ChatGPT", "Claude", "worker-a", "ChatGPT-",
        ] {
            assert!(
                validate_claim_actor(actor).is_err(),
                "unexpected actor accepted: {actor}"
            );
        }
    }

    #[test]
    fn option_parser_rejects_unsupported_or_invalid_values() {
        let lease = vec!["--lease-seconds".to_string(), "60".to_string()];
        assert_eq!(
            parse_options(&lease, true, false, false)
                .unwrap()
                .lease_seconds,
            60
        );
        assert!(parse_options(&lease, false, false, false).is_err());
        let oversized = vec!["--lease-seconds".to_string(), "3600".to_string()];
        assert_eq!(
            parse_options(&oversized, true, false, false)
                .unwrap()
                .lease_seconds,
            MAX_LEASE_SECONDS
        );
        let zero = vec!["--lease-seconds".to_string(), "0".to_string()];
        assert!(parse_options(&zero, true, false, false).is_err());
    }
}
