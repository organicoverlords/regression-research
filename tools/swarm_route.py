#!/usr/bin/env python3
# Shared sticky machine-admission cohort for the ChatGPT swarm.
from __future__ import annotations
import argparse, contextlib, ctypes, datetime as dt, json, os
from pathlib import Path
import re, shlex, shutil, subprocess, sys, tempfile, time, uuid

SCHEMA = "swarm.routing.cohort.v1"
KINDS = ("lowvram", "windows-only", "portable", "portable-light", "heavy", "p3-runtime")
DEFAULT_TTL_SECONDS = 1800
PROBE_TTL_SECONDS = 45
WORK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#@+-]{0,191}$")
OMEN_HOST = "192.168.0.128"
OMEN_HOST_KEY_ALIAS = "192.168.0.128"
OMEN_USER = "aatuska"
VPS_RUNNER_LABEL = "p3-vps-light"

def utc_now(): return dt.datetime.now(dt.timezone.utc)
def iso(t): return t.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
def parse_time(value): return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))

def default_state_path():
    root = os.environ.get("LOCALAPPDATA") or str(Path.home()/".local"/"state")
    return Path(root)/"SwarmRouting"/"cohort-v1.json"

def empty_state(): return {"schema": SCHEMA, "assignments": {}, "probe": None}

def load_state(path):
    try: data=json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError,OSError,json.JSONDecodeError): return empty_state()
    if data.get("schema")!=SCHEMA or not isinstance(data.get("assignments"),dict): return empty_state()
    return data

def save_state(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=str(path.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as fh:
            json.dump(data,fh,indent=2,sort_keys=True); fh.write("\n"); fh.flush(); os.fsync(fh.fileno())
        os.replace(name,path)
    finally:
        with contextlib.suppress(FileNotFoundError): os.unlink(name)

@contextlib.contextmanager
def state_lock(path,timeout_seconds=8.0):
    lock_path=path.with_suffix(path.suffix+".lock"); lock_path.parent.mkdir(parents=True,exist_ok=True)
    fh=open(lock_path,"a+b")
    try:
        fh.seek(0,os.SEEK_END)
        if fh.tell()==0: fh.write(b"\0"); fh.flush()
        fh.seek(0); deadline=time.monotonic()+timeout_seconds
        if os.name=="nt":
            import msvcrt
            while True:
                try: msvcrt.locking(fh.fileno(),msvcrt.LK_NBLCK,1); break
                except OSError:
                    if time.monotonic()>=deadline: raise TimeoutError("SWARM_ROUTE_LOCK_TIMEOUT")
                    time.sleep(.05)
            try: yield
            finally: fh.seek(0); msvcrt.locking(fh.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            while True:
                try: fcntl.flock(fh.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB); break
                except BlockingIOError:
                    if time.monotonic()>=deadline: raise TimeoutError("SWARM_ROUTE_LOCK_TIMEOUT")
                    time.sleep(.05)
            try: yield
            finally: fcntl.flock(fh.fileno(),fcntl.LOCK_UN)
    finally: fh.close()

def _run(args,timeout): return subprocess.run(args,capture_output=True,text=True,timeout=timeout,check=False)

def probe_windows():
    out={"available":True}
    try: out["disk_free_gb"]=round(shutil.disk_usage(Path.home().anchor or "C:\\").free/1024**3,2)
    except OSError: out["disk_free_gb"]=None
    if os.name=="nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_=[("dwLength",ctypes.c_ulong),("dwMemoryLoad",ctypes.c_ulong),("ullTotalPhys",ctypes.c_ulonglong),("ullAvailPhys",ctypes.c_ulonglong),("ullTotalPageFile",ctypes.c_ulonglong),("ullAvailPageFile",ctypes.c_ulonglong),("ullTotalVirtual",ctypes.c_ulonglong),("ullAvailVirtual",ctypes.c_ulonglong),("sullAvailExtendedVirtual",ctypes.c_ulonglong)]
        x=MEMORYSTATUSEX(); x.dwLength=ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(x)):
            out["mem_available_gb"]=round(x.ullAvailPhys/1024**3,2)
            out["commit_headroom_gb"]=round(x.ullAvailPageFile/1024**3,2)
    return out

def probe_omen(timeout=7.0):
    key=Path.home()/".ssh"/"chatgpt-linux-aatuska-ed25519"
    if not key.is_file(): return {"available":False,"reason":"SSH_KEY_MISSING"}
    code=r'''import json,os,shutil,subprocess
m={}
with open("/proc/meminfo",encoding="utf-8") as f:
    for line in f:
        k,v=line.split(":",1); m[k]=v.strip()
def kb(n): return int(m.get(n,"0 kB").split()[0])
def active(u):
    r=subprocess.run(["systemctl","--user","is-active",u],capture_output=True,text=True)
    return r.stdout.strip() in ("active","activating","reloading")
hot=subprocess.run(["systemctl","--user","list-units","p3-linux-hot-runtime-*.service","--state=active,activating","--no-legend","--plain"],capture_output=True,text=True)
disk=shutil.disk_usage("/mnt/ue")
gpu={}
try:
    r=subprocess.run(["nvidia-smi","--query-gpu=utilization.gpu,memory.used,memory.free","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=3)
    if r.returncode==0:
        a=[int(x.strip()) for x in r.stdout.strip().split(",")[:3]]
        gpu={"utilization_pct":a[0],"vram_used_mb":a[1],"vram_free_mb":a[2]}
except Exception: pass
print(json.dumps({"available":True,"mem_available_gb":round(kb("MemAvailable")/1024/1024,2),"swap_free_gb":round(kb("SwapFree")/1024/1024,2),"disk_free_gb":round(disk.free/1024**3,2),"load1":round(os.getloadavg()[0],2),"cpu_count":os.cpu_count() or 1,"lane1_build_active":active("p3-linux-build.service"),"lane2_build_active":active("p3-linux-lane@2.service"),"lane3_build_active":active("p3-linux-light.service"),"hot_runtime_count":len([x for x in hot.stdout.splitlines() if x.strip()]),"gpu":gpu},separators=(",",":")))'''
    remote_cmd=f"python3 -c {shlex.quote(code)}"
    args=["ssh","-F","NUL","-4","-i",str(key),"-o","BatchMode=yes","-o","ConnectTimeout=5","-o",f"HostKeyAlias={OMEN_HOST_KEY_ALIAS}",f"{OMEN_USER}@{OMEN_HOST}",remote_cmd]
    try: cp=_run(args,timeout)
    except (OSError,subprocess.TimeoutExpired): return {"available":False,"reason":"SSH_UNAVAILABLE"}
    if cp.returncode!=0: return {"available":False,"reason":"SSH_PROBE_FAILED","exit_code":cp.returncode}
    try: out=json.loads(cp.stdout.strip())
    except json.JSONDecodeError: return {"available":False,"reason":"PROBE_OUTPUT_INVALID"}
    out["available"]=bool(out.get("available")); return out

def probe_vps(timeout=6.0):
    try: cp=_run(["gh","api","repos/organicoverlords/p3/actions/runners"],timeout)
    except (OSError,subprocess.TimeoutExpired): return {"available":False,"reason":"RUNNER_PROBE_UNAVAILABLE"}
    if cp.returncode!=0: return {"available":False,"reason":"RUNNER_PROBE_FAILED"}
    try: runners=json.loads(cp.stdout).get("runners",[])
    except json.JSONDecodeError: return {"available":False,"reason":"RUNNER_PROBE_INVALID"}
    for runner in runners:
        labels={x.get("name") for x in runner.get("labels",[])}
        if VPS_RUNNER_LABEL in labels:
            return {"available":runner.get("status")=="online" and not bool(runner.get("busy")),"online":runner.get("status")=="online","busy":bool(runner.get("busy")),"name":runner.get("name"),"route":"github-runner:p3-vps-light"}
    return {"available":False,"reason":"RUNNER_NOT_REGISTERED"}

def probe_all():
    return {"observed_at":iso(utc_now()),"omen":probe_omen(),"windows":probe_windows(),"vps":probe_vps()}

def prune_assignments(state,now):
    keep={}
    for work_id,a in state.get("assignments",{}).items():
        try:
            if parse_time(a["expires_at"])>now: keep[work_id]=a
        except (KeyError,TypeError,ValueError): pass
    state["assignments"]=keep

def probe_is_fresh(probe,now):
    if not probe: return False
    try: return (now-parse_time(probe["observed_at"])).total_seconds()<=PROBE_TTL_SECONDS
    except (KeyError,TypeError,ValueError): return False

def omen_load(assignments):
    kinds=[a.get("kind") for a in assignments.values() if a.get("route")=="omen"]
    return {"total":len(kinds),"heavy":sum(k in ("heavy","p3-runtime") for k in kinds),"portable":sum(k=="portable" for k in kinds),"light":sum(k=="portable-light" for k in kinds)}

def omen_admissible(kind,omen,assignments):
    if not omen.get("available"): return False,"OMEN_UNAVAILABLE"
    mem=float(omen.get("mem_available_gb") or 0); disk=float(omen.get("disk_free_gb") or 0)
    cpus=max(int(omen.get("cpu_count") or 1),1); ratio=float(omen.get("load1") or 0)/cpus
    leased=omen_load(assignments)
    if kind=="p3-runtime":
        if omen.get("lane1_build_active"): return False,"OMEN_LANE1_REFRESH_ACTIVE"
        if mem<3 or disk<25: return False,"OMEN_RUNTIME_HEADROOM_LOW"
        return True,"OMEN_RUNTIME_READY"
    if kind=="heavy":
        if omen.get("lane2_build_active") or leased["heavy"]>=1: return False,"OMEN_HEAVY_CAPACITY_FULL"
        if mem<5 or disk<30 or ratio>=.85: return False,"OMEN_HEAVY_HEADROOM_LOW"
        return True,"OMEN_HEAVY_ADMITTED"
    if kind=="portable":
        if leased["total"]>=5 or mem<3 or disk<20 or ratio>=.95: return False,"OMEN_PORTABLE_CAPACITY_FULL"
        return True,"OMEN_PORTABLE_ADMITTED"
    if kind=="portable-light":
        if leased["total"]>=6 or mem<2 or disk<15 or ratio>=1.0: return False,"OMEN_LIGHT_CAPACITY_FULL"
        return True,"OMEN_LIGHT_ADMITTED"
    return False,"OMEN_KIND_UNSUPPORTED"

def choose_route(kind,facts,assignments):
    if kind=="lowvram": return "windows","LOWVRAM_PINNED_WINDOWS"
    if kind=="windows-only": return "windows","WINDOWS_ONLY"
    ok,reason=omen_admissible(kind,facts.get("omen",{}),assignments)
    if ok: return "omen",reason
    if kind=="portable-light" and facts.get("vps",{}).get("available"): return "vps",reason+"_VPS_LIGHT_OVERFLOW"
    return "windows",reason+"_WINDOWS_FALLBACK"

def route_work(state_path,work_id,kind,ttl_seconds,refresh_probe=False):
    if kind not in KINDS: raise ValueError("SWARM_ROUTE_BAD_KIND")
    if not WORK_ID_RE.fullmatch(work_id): raise ValueError("SWARM_ROUTE_BAD_WORK_ID")
    now=utc_now()
    with state_lock(state_path):
        state=load_state(state_path); prune_assignments(state,now)
        current=state["assignments"].get(work_id)
        if current:
            current["expires_at"]=iso(now+dt.timedelta(seconds=ttl_seconds)); current["last_reused_at"]=iso(now)
            save_state(state_path,state); return {**current,"reused":True,"cohort_state":str(state_path)}
        probe=state.get("probe")
        if refresh_probe or not probe_is_fresh(probe,now):
            probe=probe_all(); state["probe"]=probe
        route,reason=choose_route(kind,probe,state["assignments"])
        a={"schema":SCHEMA,"decision_id":str(uuid.uuid4()),"work_id":work_id,"kind":kind,"route":route,"reason":reason,"assigned_at":iso(now),"expires_at":iso(now+dt.timedelta(seconds=ttl_seconds)),"probe_observed_at":probe.get("observed_at")}
        state["assignments"][work_id]=a; save_state(state_path,state)
        return {**a,"reused":False,"facts":probe,"cohort_state":str(state_path)}

def release_work(state_path,work_id):
    with state_lock(state_path):
        state=load_state(state_path); existed=state.get("assignments",{}).pop(work_id,None); save_state(state_path,state)
    return {"released":bool(existed),"work_id":work_id,"cohort_state":str(state_path)}

def status(state_path,refresh_probe=False):
    now=utc_now()
    with state_lock(state_path):
        state=load_state(state_path); prune_assignments(state,now)
        if refresh_probe or not probe_is_fresh(state.get("probe"),now): state["probe"]=probe_all()
        save_state(state_path,state)
        return {"schema":SCHEMA,"observed_at":iso(now),"assignments":state["assignments"],"probe":state.get("probe"),"omen_load":omen_load(state["assignments"]),"cohort_state":str(state_path)}

def build_parser():
    p=argparse.ArgumentParser(description="Shared OMEN-first swarm machine routing cohort")
    p.add_argument("--state",type=Path,default=default_state_path())
    sub=p.add_subparsers(dest="command",required=True)
    r=sub.add_parser("route"); r.add_argument("--work-id",required=True); r.add_argument("--kind",required=True,choices=KINDS); r.add_argument("--ttl-seconds",type=int,default=DEFAULT_TTL_SECONDS); r.add_argument("--refresh-probe",action="store_true")
    rel=sub.add_parser("release"); rel.add_argument("--work-id",required=True)
    st=sub.add_parser("status"); st.add_argument("--refresh-probe",action="store_true")
    sub.add_parser("probe"); return p

def main(argv=None):
    args=build_parser().parse_args(argv)
    try:
        if args.command=="route":
            if not 60<=args.ttl_seconds<=7200: raise ValueError("SWARM_ROUTE_BAD_TTL")
            out=route_work(args.state,args.work_id,args.kind,args.ttl_seconds,args.refresh_probe)
        elif args.command=="release": out=release_work(args.state,args.work_id)
        elif args.command=="status": out=status(args.state,args.refresh_probe)
        else: out=probe_all()
        print(json.dumps(out,indent=2,sort_keys=True)); return 0
    except (ValueError,TimeoutError) as exc:
        print(json.dumps({"error":str(exc)}),file=sys.stderr); return 64

if __name__=="__main__": raise SystemExit(main())
