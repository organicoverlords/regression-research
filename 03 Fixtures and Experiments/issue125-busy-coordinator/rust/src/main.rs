use chrono::{SecondsFormat, Utc};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::env;
use std::ffi::OsStr;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::os::windows::ffi::OsStrExt;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::thread;
use std::time::{Duration, Instant, SystemTime};
use windows_sys::Win32::Storage::FileSystem::{MoveFileExW, MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH};

const LOCK_TIMEOUT: Duration = Duration::from_secs(2);
const LOCK_STALE: Duration = Duration::from_secs(15);
const LOCK_RETRY: Duration = Duration::from_millis(10);

#[derive(Clone, Debug, Deserialize, Serialize)]
struct Claim { actor: String, scope: String, timestamp: String }

#[derive(Default, Deserialize, Serialize)]
struct StoreFile { claims: Vec<Claim> }

struct StoreLock { path: PathBuf, file: Option<File> }

impl StoreLock {
    fn acquire(store: &Path) -> io::Result<Self> {
        let path = PathBuf::from(format!("{}.lock", store.display()));
        if let Some(parent) = path.parent() { fs::create_dir_all(parent)?; }
        let deadline = Instant::now() + LOCK_TIMEOUT;
        loop {
            match OpenOptions::new().write(true).create_new(true).open(&path) {
                Ok(mut file) => {
                    writeln!(file, "{}", std::process::id())?;
                    return Ok(Self { path, file: Some(file) });
                }
                Err(error) if matches!(error.kind(), io::ErrorKind::AlreadyExists | io::ErrorKind::PermissionDenied) => {
                    let stale = fs::metadata(&path).and_then(|m| m.modified()).ok()
                        .and_then(|m| SystemTime::now().duration_since(m).ok())
                        .is_some_and(|age| age > LOCK_STALE);
                    if stale { let _ = fs::remove_file(&path); continue; }
                    if Instant::now() >= deadline { return Err(io::Error::new(io::ErrorKind::WouldBlock, "busy store locked by another writer")); }
                    thread::sleep(LOCK_RETRY);
                }
                Err(error) => return Err(error),
            }
        }
    }
}

impl Drop for StoreLock {
    fn drop(&mut self) { self.file.take(); let _ = fs::remove_file(&self.path); }
}

fn default_store() -> PathBuf {
    if let Ok(path) = env::var("BUSY_STORE_PATH") { return PathBuf::from(path); }
    if let Ok(path) = env::var("MCP_BUSY_STORE_PATH") { return PathBuf::from(path); }
    let base = env::var_os("LOCALAPPDATA").map(PathBuf::from).unwrap_or_else(env::temp_dir);
    base.join("ChatGPTMcpClean").join(".state").join("busy-claims.json")
}

fn load(store: &Path) -> Result<StoreFile, String> {
    match fs::read_to_string(store) {
        Ok(raw) => serde_json::from_str::<StoreFile>(&raw).map_err(|e| format!("cannot safely read BUSY store: {e}")),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(StoreFile::default()),
        Err(e) => Err(format!("cannot safely read BUSY store: {e}")),
    }
}

fn wide_null(value: &OsStr) -> Vec<u16> { value.encode_wide().chain(std::iter::once(0)).collect() }

fn persist(store: &Path, state: &StoreFile) -> Result<(), String> {
    if let Some(parent) = store.parent() { fs::create_dir_all(parent).map_err(|e| e.to_string())?; }
    let tmp = PathBuf::from(format!("{}.{}.tmp", store.display(), std::process::id()));
    let mut bytes = serde_json::to_vec_pretty(state).map_err(|e| e.to_string())?;
    bytes.push(b'\n'); fs::write(&tmp, bytes).map_err(|e| e.to_string())?;
    let src = wide_null(tmp.as_os_str()); let dst = wide_null(store.as_os_str());
    let ok = unsafe { MoveFileExW(src.as_ptr(), dst.as_ptr(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) };
    if ok == 0 { let e = io::Error::last_os_error(); let _ = fs::remove_file(&tmp); return Err(format!("cannot replace BUSY store: {e}")); }
    Ok(())
}

fn print_json(value: serde_json::Value) -> Result<(), String> { println!("{}", serde_json::to_string(&value).map_err(|e| e.to_string())?); Ok(()) }

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let command = args.next().ok_or_else(|| "usage: busy-rs <list|claim|release> [actor] [scope]".to_string())?;
    let store = default_store(); let _lock = StoreLock::acquire(&store).map_err(|e| e.to_string())?; let mut state = load(&store)?;
    match command.as_str() {
        "list" => { if args.next().is_some() { return Err("usage: busy-rs list".into()); } state.claims.sort_by(|a,b| a.scope.cmp(&b.scope)); print_json(json!({"claims": state.claims})) }
        "claim" => {
            let actor=args.next().ok_or_else(||"usage: busy-rs claim <actor> <scope>".to_string())?;
            let scope=args.next().ok_or_else(||"usage: busy-rs claim <actor> <scope>".to_string())?;
            if args.next().is_some(){return Err("usage: busy-rs claim <actor> <scope>".into());}
            if let Some(current)=state.claims.iter().find(|c|c.scope==scope && c.actor!=actor).cloned(){return print_json(json!({"ok":false,"reason":"scope_already_claimed","claim":current}));}
            let new=Claim{actor:actor.clone(),scope:scope.clone(),timestamp:Utc::now().to_rfc3339_opts(SecondsFormat::Millis,true)};
            state.claims.retain(|c|c.scope!=scope); state.claims.push(new.clone()); persist(&store,&state)?; print_json(json!({"ok":true,"claim":new}))
        }
        "release" => {
            let actor=args.next().ok_or_else(||"usage: busy-rs release <actor> <scope>".to_string())?;
            let scope=args.next().ok_or_else(||"usage: busy-rs release <actor> <scope>".to_string())?;
            if args.next().is_some(){return Err("usage: busy-rs release <actor> <scope>".into());}
            let current=state.claims.iter().find(|c|c.scope==scope).cloned();
            match current {
                None=>print_json(json!({"ok":false,"reason":"scope_not_claimed"})),
                Some(c) if c.actor!=actor=>print_json(json!({"ok":false,"reason":"claim_belongs_to_another_actor","claim":c})),
                Some(c)=>{state.claims.retain(|x|x.scope!=scope); persist(&store,&state)?; print_json(json!({"ok":true,"released":c}))}
            }
        }
        _=>Err("usage: busy-rs <list|claim|release> [actor] [scope]".into()),
    }
}

fn main() -> ExitCode { match run(){Ok(())=>ExitCode::SUCCESS,Err(e)=>{eprintln!("{}",e);ExitCode::from(if e.contains("locked") {75}else{1})}} }
