use chrono::{DateTime, Duration as ChronoDuration, SecondsFormat, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use std::collections::BTreeMap;
use std::env;
use std::ffi::OsStr;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::os::windows::ffi::OsStrExt;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::thread;
use std::time::{Duration, Instant, SystemTime};
use windows_sys::Win32::Storage::FileSystem::{
    MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH, MoveFileExW,
};

const LOCK_TIMEOUT: Duration = Duration::from_secs(2);
const LOCK_STALE: Duration = Duration::from_secs(15);
const LOCK_RETRY: Duration = Duration::from_millis(10);
const DEFAULT_LEASE_SECONDS: i64 = 3600;
const MAX_OPERATIONS: usize = 512;
const MAX_HANDOFF_SOURCE_CHARS: usize = 2048;
const MAX_HANDOFF_SUMMARY_CHARS: usize = 8192;

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
struct Claim {
    actor: String,
    scope: String,
    timestamp: String,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
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
    fs::write(&tmp, bytes).map_err(|e| e.to_string())?;
    let src = wide_null(tmp.as_os_str());
    let dst = wide_null(store.as_os_str());
    let ok = unsafe {
        MoveFileExW(
            src.as_ptr(),
            dst.as_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    };
    if ok == 0 {
        let error = io::Error::last_os_error();
        let _ = fs::remove_file(&tmp);
        return Err(format!("cannot replace BUSY store: {error}"));
    }
    Ok(())
}

fn now_iso() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true)
}

fn canonical_scope(raw: &str) -> Result<String, String> {
    let scope = raw.trim().to_string();
    if scope.is_empty() {
        Err("scope must not be empty".into())
    } else {
        Ok(scope)
    }
}

fn claim_index(state: &StoreFile, scope: &str) -> Option<usize> {
    state.claims.iter().position(|claim| claim.scope == scope)
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

fn sweep_expired(state: &mut StoreFile) -> (Vec<Value>, bool) {
    let now = Utc::now();
    let scopes: Vec<String> = state.coordinator.jobs.keys().cloned().collect();
    let mut expired = Vec::new();
    let mut changed = false;
    for scope in scopes {
        let (job_state, owner, lease, expected_timestamp, checkpoint) =
            match state.coordinator.jobs.get(&scope) {
                Some(job) => (
                    job.state.clone(),
                    job.owner.clone(),
                    job.lease_expires_at.clone(),
                    job.claim_timestamp.clone(),
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
        if let Some(claim) = current.as_ref().filter(|claim| claim.actor == owner) {
            if expected_timestamp
                .as_deref()
                .is_some_and(|expected| expected != claim.timestamp)
            {
                if let Some(job) = state.coordinator.jobs.get_mut(&scope) {
                    job.claim_timestamp = Some(claim.timestamp.clone());
                    job.lease_expires_at = None;
                    job.updated_at = claim.timestamp.clone();
                    changed = true;
                }
                continue;
            }
            state.claims.retain(|claim| claim.scope != scope);
        }
        if let Some(job) = state.coordinator.jobs.get_mut(&scope) {
            job.state = "ready".into();
            job.owner = None;
            job.lease_expires_at = None;
            job.updated_at = now_iso();
        }
        expired.push(json!({"scope": scope, "previous_owner": owner, "checkpoint": checkpoint}));
        changed = true;
    }
    (expired, changed)
}

#[derive(Default)]
struct Options {
    operation_id: Option<String>,
    checkpoint: Option<String>,
    finding_id: Option<String>,
    source: Option<String>,
    summary: Option<String>,
    lease_seconds: i64,
}

fn parse_options(
    args: &[String],
    allow_lease: bool,
    allow_checkpoint: bool,
    allow_handoff: bool,
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
            "--finding-id" if allow_handoff => {
                index += 1;
                options.finding_id = Some(
                    args.get(index)
                        .ok_or("--finding-id requires a value")?
                        .clone(),
                );
            }
            "--source" if allow_handoff => {
                index += 1;
                options.source = Some(args.get(index).ok_or("--source requires a value")?.clone());
            }
            "--summary" if allow_handoff => {
                index += 1;
                options.summary =
                    Some(args.get(index).ok_or("--summary requires a value")?.clone());
            }
            other => return Err(format!("unknown option: {other}")),
        }
        index += 1;
    }
    Ok(options)
}

fn signature(
    command: &str,
    actor: Option<&str>,
    scope: &str,
    options: &Options,
    include_lease: bool,
    include_checkpoint: bool,
) -> Value {
    let mut map = Map::new();
    map.insert("command".into(), json!(command));
    if let Some(actor) = actor {
        map.insert("actor".into(), json!(actor));
    }
    map.insert("scope".into(), json!(scope));
    if include_checkpoint {
        if let Some(checkpoint) = &options.checkpoint {
            map.insert("checkpoint".into(), json!(checkpoint));
        }
    }
    if include_lease {
        map.insert("lease_seconds".into(), json!(options.lease_seconds));
    }
    if let Some(finding_id) = &options.finding_id {
        map.insert("finding_id".into(), json!(finding_id));
    }
    if let Some(source) = &options.source {
        map.insert("source".into(), json!(source));
    }
    if let Some(summary) = &options.summary {
        map.insert("summary".into(), json!(summary));
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
    let (swept, sweep_changed) = sweep_expired(&mut state);

    if command == "list" {
        if sweep_changed {
            persist(store, &state)?;
        }
        state.claims.sort_by(|a, b| a.scope.cmp(&b.scope));
        return Ok(json!({"claims": state.claims}));
    }
    if command == "sweep" {
        if sweep_changed {
            persist(store, &state)?;
        }
        return Ok(json!({"ok": true, "expired": swept}));
    }

    if command == "next" {
        let actor = actor.ok_or("actor required")?;
        let mut sig_map = Map::new();
        sig_map.insert("command".into(), json!(command));
        sig_map.insert("actor".into(), json!(actor));
        sig_map.insert("lease_seconds".into(), json!(options.lease_seconds));
        let sig = Value::Object(sig_map);
        if let Some(replay) = idempotent(&state, options.operation_id.as_deref(), &sig) {
            if sweep_changed {
                persist(store, &state)?;
            }
            return Ok(replay);
        }
        let mut result = json!({"ok": false, "reason": "no_actionable_job", "expired": swept});
        let ready_scope = state.coordinator.jobs.iter().find_map(|(scope, job)| {
            (job.state == "ready" && claim_index(&state, scope).is_none()).then(|| scope.clone())
        });
        if let Some(scope) = ready_scope {
            let timestamp = now_iso();
            let claim = Claim {
                actor: actor.into(),
                scope: scope.clone(),
                timestamp: timestamp.clone(),
            };
            state.claims.push(claim.clone());
            let deadline = Utc::now() + ChronoDuration::seconds(options.lease_seconds);
            if let Some(job) = state.coordinator.jobs.get_mut(&scope) {
                job.state = "active".into();
                job.owner = Some(actor.into());
                job.lease_expires_at = Some(deadline.to_rfc3339_opts(SecondsFormat::Millis, true));
                job.claim_timestamp = Some(timestamp.clone());
                job.updated_at = timestamp;
                result = json!({"ok": true, "claim": claim, "job": job, "expired": swept});
            }
        }
        let result = remember(&mut state, options.operation_id.as_deref(), sig, result);
        persist(store, &state)?;
        return Ok(result);
    }

    let scope = canonical_scope(raw_scope.ok_or("scope required")?)?;
    let include_lease = matches!(command, "claim" | "heartbeat");
    let include_checkpoint = matches!(
        command,
        "enqueue" | "ready" | "claim" | "heartbeat" | "block" | "complete"
    );
    let sig = signature(
        command,
        actor,
        &scope,
        options,
        include_lease,
        include_checkpoint,
    );
    if let Some(replay) = idempotent(&state, options.operation_id.as_deref(), &sig) {
        if sweep_changed {
            persist(store, &state)?;
        }
        return Ok(replay);
    }

    if command == "handoff" {
        let actor = actor.ok_or("actor required")?;
        let finding = canonical_scope(
            options
                .finding_id
                .as_deref()
                .ok_or("--finding-id is required")?,
        )?;
        let source = options.source.as_deref().unwrap_or("").trim();
        let summary = options.summary.as_deref().unwrap_or("").trim();
        if source.is_empty() {
            return Err("source must not be empty".into());
        }
        if summary.is_empty() {
            return Err("summary must not be empty".into());
        }
        if source.chars().count() > MAX_HANDOFF_SOURCE_CHARS {
            return Err(format!("source exceeds {MAX_HANDOFF_SOURCE_CHARS} characters"));
        }
        if summary.chars().count() > MAX_HANDOFF_SUMMARY_CHARS {
            return Err(format!("summary exceeds {MAX_HANDOFF_SUMMARY_CHARS} characters"));
        }
        let follow_scope = format!("{scope}::handoff:{finding}");
        let result = if let Some(job) = state.coordinator.jobs.get(&follow_scope) {
            json!({"ok": false, "reason": "finding_id_conflict", "job": job})
        } else {
            let timestamp = now_iso();
            let handoff = json!({
                "parent_scope": scope,
                "finding_id": finding,
                "reported_by": actor,
                "source": source,
                "summary": summary,
                "reported_at": timestamp,
            });
            let mut job = Job {
                job_id: follow_scope.clone(),
                scope: follow_scope.clone(),
                state: "ready".into(),
                owner: None,
                lease_expires_at: None,
                claim_timestamp: None,
                checkpoint: Some(summary.into()),
                updated_at: timestamp,
                ..Job::default()
            };
            job.extra.insert("handoff".into(), handoff.clone());
            state.coordinator.jobs.insert(follow_scope.clone(), job);
            json!({"ok": true, "job": state.coordinator.jobs.get(&follow_scope), "handoff": handoff})
        };
        let result = remember(&mut state, options.operation_id.as_deref(), sig, result);
        persist(store, &state)?;
        return Ok(result);
    }

    if matches!(command, "enqueue" | "ready") {
        let job = state
            .coordinator
            .jobs
            .entry(scope.clone())
            .or_insert_with(|| Job {
                job_id: scope.clone(),
                scope: scope.clone(),
                ..Job::default()
            });
        let result = if job.state == "completed" {
            json!({"ok": false, "reason": "job_completed", "job": job})
        } else if job.state == "active" {
            json!({"ok": false, "reason": "job_active", "job": job})
        } else {
            job.state = "ready".into();
            job.owner = None;
            job.lease_expires_at = None;
            job.updated_at = now_iso();
            if options.checkpoint.is_some() {
                job.checkpoint = options.checkpoint.clone();
            }
            json!({"ok": true, "job": job})
        };
        let result = remember(&mut state, options.operation_id.as_deref(), sig, result);
        persist(store, &state)?;
        return Ok(result);
    }

    let actor = actor.ok_or("actor required")?;

    let current = claim_index(&state, &scope).map(|index| state.claims[index].clone());
    let existing_job = state.coordinator.jobs.get(&scope).cloned();
    let result = match command {
        "claim" => {
            if let Some(claim) = current.as_ref().filter(|claim| claim.actor != actor) {
                json!({"ok": false, "reason": "scope_already_claimed", "claim": claim})
            } else {
                let timestamp = now_iso();
                let claim = Claim {
                    actor: actor.into(),
                    scope: scope.clone(),
                    timestamp: timestamp.clone(),
                };
                state.claims.retain(|claim| claim.scope != scope);
                state.claims.push(claim.clone());
                let deadline = Utc::now() + ChronoDuration::seconds(options.lease_seconds);
                let checkpoint = options
                    .checkpoint
                    .clone()
                    .or_else(|| existing_job.as_ref().and_then(|job| job.checkpoint.clone()));
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
                let job = state
                    .coordinator
                    .jobs
                    .entry(scope.clone())
                    .or_insert_with(|| Job {
                        job_id: scope.clone(),
                        scope: scope.clone(),
                        ..Job::default()
                    });
                job.state = "active".into();
                job.owner = Some(actor.into());
                job.lease_expires_at = Some(deadline.to_rfc3339_opts(SecondsFormat::Millis, true));
                job.claim_timestamp = Some(timestamp.clone());
                job.updated_at = timestamp;
                if options.checkpoint.is_some() {
                    job.checkpoint = options.checkpoint.clone();
                }
                json!({"ok": true, "claim": claim})
            }
        },
        "release" | "block" | "complete" => match current {
            None => json!({"ok": false, "reason": "scope_not_claimed"}),
            Some(claim) if claim.actor != actor => {
                json!({"ok": false, "reason": "claim_belongs_to_another_actor", "claim": claim})
            }
            Some(claim) => {
                state.claims.retain(|item| item.scope != scope);
                if command != "release" || existing_job.is_some() {
                    let job = state
                        .coordinator
                        .jobs
                        .entry(scope.clone())
                        .or_insert_with(|| Job {
                            job_id: scope.clone(),
                            scope: scope.clone(),
                            ..Job::default()
                        });
                    job.state = match command {
                        "release" => "ready",
                        "block" => "blocked",
                        _ => "completed",
                    }
                    .into();
                    job.owner = None;
                    job.lease_expires_at = None;
                    job.updated_at = now_iso();
                    if options.checkpoint.is_some() {
                        job.checkpoint = options.checkpoint.clone();
                    }
                }
                match command {
                    "release" => json!({"ok": true, "released": claim}),
                    "block" => json!({"ok": true, "block": claim}),
                    _ => json!({"ok": true, "complete": claim}),
                }
            }
        },
        "inspect" => {
            json!({"ok": true, "job": state.coordinator.jobs.get(&scope), "claim": current})
        }
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
    let command = raw.first().ok_or("usage: busy-rs [--store PATH] <list|sweep|enqueue|ready|handoff|next|claim|heartbeat|release|block|complete|inspect> ...")?.clone();
    raw.remove(0);
    if matches!(command.as_str(), "list" | "sweep") {
        if !raw.is_empty() {
            return Err(format!("usage: busy-rs {command}"));
        }
        return print_json(&operate(&store, &command, None, None, &Options::default())?);
    }
    if command == "next" {
        if raw.is_empty() {
            return Err("usage: busy-rs next <actor> [options]".into());
        }
        let actor = raw.remove(0);
        let options = parse_options(&raw, true, false, false)?;
        return print_json(&operate(&store, &command, Some(&actor), None, &options)?);
    }
    if command == "handoff" {
        if raw.len() < 2 {
            return Err("usage: busy-rs handoff <actor> <scope> --finding-id ID --source SOURCE --summary SUMMARY [--operation-id ID]".into());
        }
        let actor = raw.remove(0);
        let scope = raw.remove(0);
        let options = parse_options(&raw, false, false, true)?;
        return print_json(&operate(
            &store,
            &command,
            Some(&actor),
            Some(&scope),
            &options,
        )?);
    }
    if matches!(command.as_str(), "enqueue" | "ready") {
        if raw.is_empty() {
            return Err(format!("usage: busy-rs {command} <scope> [options]"));
        }
        let scope = raw.remove(0);
        let options = parse_options(&raw, false, true, false)?;
        return print_json(&operate(&store, &command, None, Some(&scope), &options)?);
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
        matches!(
            command.as_str(),
            "claim" | "heartbeat" | "block" | "complete"
        ),
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
    fn option_parser_rejects_unsupported_or_invalid_values() {
        let lease = vec!["--lease-seconds".to_string(), "60".to_string()];
        assert_eq!(
            parse_options(&lease, true, false, false)
                .unwrap()
                .lease_seconds,
            60
        );
        assert!(parse_options(&lease, false, false, false).is_err());
        let zero = vec!["--lease-seconds".to_string(), "0".to_string()];
        assert!(parse_options(&zero, true, false, false).is_err());
    }
}
