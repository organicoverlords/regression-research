#!/usr/bin/env python3
# Shared sticky machine-admission cohort for the ChatGPT swarm.
from __future__ import annotations
import argparse, contextlib, ctypes, datetime as dt, json, os, platform
from pathlib import Path
import re, shlex, shutil, subprocess, sys, tempfile, time, uuid

SCHEMA = "swarm.routing.cohort.v1"
KINDS = ("lowvram", "windows-only", "portable", "portable-light", "heavy", "p3-runtime")
DEFAULT_TTL_SECONDS = 1800
PROBE_TTL_SECONDS = 45
POLICY_EPOCH = 2
WORK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#@+-]{0,191}$")
OMEN_HOST = "192.168.0.128"
OMEN_HOST_KEY_ALIAS = "192.168.0.128"
OMEN_USER = "aatuska"
VPS_RUNNER_LABEL = "p3-vps-light"
NODE_TOPOLOGY_PATH = Path(__file__).resolve().parents[1] / "04 Operating Contracts" / "execution-node-topology.json"
NODE_IDENTITY_SCHEMA = "swarm.execution-node-identity.v1"

def _load_node_topology():
    data=json.loads(NODE_TOPOLOGY_PATH.read_text(encoding="utf-8-sig"))
    if data.get("schema")!="swarm.execution-node-topology.v1" or not isinstance(data.get("nodes"),dict):
        raise ValueError("SWARM_NODE_TOPOLOGY_INVALID")
    return data

def _declared_node(route):
    matches=[(node_id,node) for node_id,node in _load_node_topology()["nodes"].items() if node.get("route_label")==route]
    if len(matches)!=1: return None
    node_id,node=matches[0]
    return {
        "node_identity_schema":NODE_IDENTITY_SCHEMA,
        "node_id":node_id,
        "node_name":node.get("display_name"),
        "node_alias":node.get("user_alias"),
        "machine_class":node.get("machine_class"),
        "route_label":route,
    }

def _bind_node_identity(route, observed_hostname=None):
    declared=_declared_node(route)
    observed=str(observed_hostname or "").strip()
    if declared is None:
        return {"node_identity_schema":NODE_IDENTITY_SCHEMA,"node_id":None,"expected_node_id":None,"node_name":None,"node_alias":None,"machine_class":None,"route_label":route,"observed_hostname":observed or None,"node_identity_status":"UNRESOLVED_ROUTE"}
    declared_id=declared["node_id"]
    node=_load_node_topology()["nodes"][declared_id]
    hostnames=[str(x).casefold() for x in node.get("hostnames",[]) if str(x).strip()]
    if not hostnames:
        return {**declared,"expected_node_id":declared_id,"observed_hostname":observed or None,"node_identity_status":"ROUTE_BOUND_LOGICAL_NODE"}
    if not observed:
        return {**declared,"node_id":None,"expected_node_id":declared_id,"observed_hostname":None,"node_identity_status":"HOSTNAME_UNOBSERVED"}
    if observed.casefold() not in hostnames:
        return {**declared,"node_id":None,"expected_node_id":declared_id,"observed_hostname":observed,"node_identity_status":"HOSTNAME_MISMATCH"}
    return {**declared,"expected_node_id":declared_id,"observed_hostname":observed,"node_identity_status":"VERIFIED_HOSTNAME"}

def _unavailable_probe(route, reason, **extra):
    return {"available":False,"reason":reason,**_bind_node_identity(route),**extra}

def _identity_from_probe(route, probe):
    bucket=probe.get(route if route!="vps" else "vps",{}) if isinstance(probe,dict) else {}
    if isinstance(bucket,dict) and bucket.get("node_identity_status"):
        return {key:bucket.get(key) for key in ("node_identity_schema","node_id","expected_node_id","node_name","node_alias","machine_class","route_label","observed_hostname","node_identity_status")}
    return _bind_node_identity(route)

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

def _gh_swarm_bin():
    found=shutil.which("gh-swarm")
    if found: return found
    local=Path.home()/".local"/"bin"/("gh-swarm.exe" if os.name=="nt" else "gh-swarm")
    return str(local) if local.is_file() else None

def _github_read(args,timeout):
    proxy=_gh_swarm_bin()
    if proxy:
        try:
            cp=_run([proxy,*args],timeout)
        except (OSError,subprocess.TimeoutExpired):
            pass
        else:
            if cp.returncode==0: return cp
    return _run(["gh",*args],timeout)

def probe_windows():
    observed_hostname=platform.node() or os.environ.get("COMPUTERNAME") or None
    out={"available":True,"observed_hostname":observed_hostname}
    out.update(_bind_node_identity("windows",observed_hostname))
    try: out["disk_free_gb"]=round(shutil.disk_usage(Path.home().anchor or "C:\\").free/1024**3,2)
    except OSError: out["disk_free_gb"]=None
    if os.name=="nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_=[("dwLength",ctypes.c_ulong),("dwMemoryLoad",ctypes.c_ulong),("ullTotalPhys",ctypes.c_ulonglong),("ullAvailPhys",ctypes.c_ulonglong),("ullTotalPageFile",ctypes.c_ulonglong),("ullAvailPageFile",ctypes.c_ulonglong),("ullTotalVirtual",ctypes.c_ulonglong),("ullAvailVirtual",ctypes.c_ulonglong),("sullAvailExtendedVirtual",ctypes.c_ulonglong)]
        x=MEMORYSTATUSEX(); x.dwLength=ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(x)):
            out["mem_available_gb"]=round(x.ullAvailPhys/1024**3,2)
            out["commit_headroom_gb"]=round(x.ullAvailPageFile/1024**3,2)
    gpu={}
    try:
        cp=_run(["nvidia-smi","--query-gpu=name,utilization.gpu,memory.used,memory.free,power.draw,temperature.gpu","--format=csv,noheader,nounits"],3)
        if cp.returncode==0:
            a=[x.strip() for x in cp.stdout.strip().split(",")[:6]]
            gpu={"name":a[0],"utilization_pct":int(a[1]),"vram_used_mb":int(a[2]),"vram_free_mb":int(a[3]),"power_draw_w":float(a[4]),"temperature_c":int(a[5])}
    except (OSError,subprocess.TimeoutExpired,ValueError,IndexError): pass
    out["gpu"]=gpu
    return out

def _omen_probe_code():
    return r'''import json,os,shutil,subprocess
m={}
with open("/proc/meminfo",encoding="utf-8") as f:
    for line in f:
        k,v=line.split(":",1); m[k]=v.strip()
def kb(n): return int(m.get(n,"0 kB").split()[0])
def active(u):
    r=subprocess.run(["systemctl","--user","is-active",u],capture_output=True,text=True)
    return r.stdout.strip() in ("active","activating","reloading")
def argv_active(script,lane=None):
    for name in os.listdir("/proc"):
        if not name.isdigit(): continue
        try:
            raw=open(f"/proc/{name}/cmdline","rb").read()
        except (FileNotFoundError,PermissionError,OSError):
            continue
        argv=[x.decode("utf-8",errors="replace") for x in raw.split(b"\0") if x]
        for i,arg in enumerate(argv):
            if not (arg==script or arg.endswith("/"+script)): continue
            if lane is None or (i+1<len(argv) and argv[i+1]==str(lane)): return True
    return False
hot=subprocess.run(["systemctl","--user","list-units","p3-linux-hot-runtime-*.service","--state=active,activating","--no-legend","--plain"],capture_output=True,text=True)
root_disk=shutil.disk_usage("/")
nvme_disk=shutil.disk_usage("/mnt/ue")
gpu={}
try:
    r=subprocess.run(["nvidia-smi","--query-gpu=name,utilization.gpu,memory.used,memory.free","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=3)
    if r.returncode==0:
        a=[x.strip() for x in r.stdout.strip().split(",")[:4]]
        gpu={"name":a[0],"utilization_pct":int(a[1]),"vram_used_mb":int(a[2]),"vram_free_mb":int(a[3])}
except Exception: pass
lane1=active("p3-linux-build.service") or active("p3-linux-lane@1.service") or argv_active("run-p3-linux-lane.sh",1)
lane2=active("p3-linux-lane@2.service") or argv_active("run-p3-linux-lane.sh",2)
lane3=active("p3-linux-light.service") or active("p3-linux-lane@3.service") or argv_active("run-p3-linux-light.sh") or argv_active("run-p3-linux-lane.sh",3)
print(json.dumps({"available":True,"observed_hostname":os.uname().nodename,"mem_available_gb":round(kb("MemAvailable")/1024/1024,2),"swap_free_gb":round(kb("SwapFree")/1024/1024,2),"disk_free_gb":round(nvme_disk.free/1024**3,2),"root_disk_free_gb":round(root_disk.free/1024**3,2),"nvme_disk_free_gb":round(nvme_disk.free/1024**3,2),"load1":round(os.getloadavg()[0],2),"cpu_count":os.cpu_count() or 1,"lane1_build_active":lane1,"lane2_build_active":lane2,"lane3_build_active":lane3,"hot_runtime_count":len([x for x in hot.stdout.splitlines() if x.strip()]),"gpu":gpu},separators=(",",":")))'''

def probe_omen(timeout=7.0):
    key=Path.home()/".ssh"/"chatgpt-linux-aatuska-ed25519"
    if not key.is_file(): return _unavailable_probe("omen","SSH_KEY_MISSING")
    code=_omen_probe_code()
    remote_cmd=f"python3 -c {shlex.quote(code)}"
    args=["ssh","-F","NUL","-4","-i",str(key),"-o","BatchMode=yes","-o","ConnectTimeout=5","-o",f"HostKeyAlias={OMEN_HOST_KEY_ALIAS}",f"{OMEN_USER}@{OMEN_HOST}",remote_cmd]
    try: cp=_run(args,timeout)
    except (OSError,subprocess.TimeoutExpired): return _unavailable_probe("omen","SSH_UNAVAILABLE")
    if cp.returncode!=0: return _unavailable_probe("omen","SSH_PROBE_FAILED",exit_code=cp.returncode)
    try: out=json.loads(cp.stdout.strip())
    except json.JSONDecodeError: return _unavailable_probe("omen","PROBE_OUTPUT_INVALID")
    out["available"]=bool(out.get("available")); out.update(_bind_node_identity("omen",out.get("observed_hostname"))); return out

def probe_vps(timeout=6.0):
    try: cp=_github_read(["api","repos/organicoverlords/p3/actions/runners"],timeout)
    except (OSError,subprocess.TimeoutExpired): return _unavailable_probe("vps","RUNNER_PROBE_UNAVAILABLE")
    if cp.returncode!=0: return _unavailable_probe("vps","RUNNER_PROBE_FAILED")
    try: runners=json.loads(cp.stdout).get("runners",[])
    except json.JSONDecodeError: return _unavailable_probe("vps","RUNNER_PROBE_INVALID")
    for runner in runners:
        labels={x.get("name") for x in runner.get("labels",[])}
        if VPS_RUNNER_LABEL in labels:
            out={"available":runner.get("status")=="online" and not bool(runner.get("busy")),"online":runner.get("status")=="online","busy":bool(runner.get("busy")),"name":runner.get("name"),"route":"github-runner:p3-vps-light"}
            out.update(_bind_node_identity("vps",runner.get("name")))
            return out
    return _unavailable_probe("vps","RUNNER_NOT_REGISTERED")

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
    root_disk=float(omen.get("root_disk_free_gb") if omen.get("root_disk_free_gb") is not None else disk)
    nvme_disk=float(omen.get("nvme_disk_free_gb") if omen.get("nvme_disk_free_gb") is not None else disk)
    cpus=max(int(omen.get("cpu_count") or 1),1); ratio=float(omen.get("load1") or 0)/cpus
    # Assignments are sticky routing hints, not proof that compute is occupied. Repo-owned
    # queues/locks serialize actual heavy/runtime flights, so stale or waiting leases must
    # not make an otherwise idle OMEN look full.
    if kind=="p3-runtime":
        if root_disk<12: return False,"OMEN_RUNTIME_ROOT_DISK_LOW"
        if nvme_disk<12: return False,"OMEN_RUNTIME_NVME_DISK_LOW"
        if mem<2.5: return False,"OMEN_RUNTIME_MEMORY_LOW"
        return True,"OMEN_RUNTIME_READY"
    if kind=="heavy":
        if nvme_disk<16: return False,"OMEN_HEAVY_DISK_LOW"
        if mem<4 or ratio>=.90: return False,"OMEN_HEAVY_HEADROOM_LOW"
        return True,"OMEN_HEAVY_ADMITTED"
    if kind=="portable":
        if nvme_disk<10: return False,"OMEN_PORTABLE_DISK_LOW"
        if mem<2 or ratio>=1.0: return False,"OMEN_PORTABLE_HEADROOM_LOW"
        return True,"OMEN_PORTABLE_ADMITTED"
    if kind=="portable-light":
        if nvme_disk<8: return False,"OMEN_LIGHT_DISK_LOW"
        if mem<1.5 or ratio>=1.15: return False,"OMEN_LIGHT_HEADROOM_LOW"
        return True,"OMEN_LIGHT_ADMITTED"
    return False,"OMEN_KIND_UNSUPPORTED"


def _omen_reclaim_target_gb(kind):
    return {"p3-runtime":18,"heavy":24,"portable":16,"portable-light":12}.get(kind)

def reclaim_omen_scratch(kind,timeout=12.0):
    target=_omen_reclaim_target_gb(kind)
    if target is None: return {"attempted":False,"reason":"KIND_NOT_RECLAIMABLE"}
    key=Path.home()/".ssh"/"chatgpt-linux-aatuska-ed25519"
    if not key.is_file(): return {"attempted":False,"reason":"SSH_KEY_MISSING"}
    args=["ssh","-F","NUL","-4","-i",str(key),"-o","BatchMode=yes","-o","ConnectTimeout=5","-o",f"HostKeyAlias={OMEN_HOST_KEY_ALIAS}",f"{OMEN_USER}@{OMEN_HOST}",f"/home/{OMEN_USER}/ue-work/reclaim-p3-linux-scratch.sh {target}"]
    try: cp=_run(args,timeout)
    except (OSError,subprocess.TimeoutExpired): return {"attempted":True,"ok":False,"reason":"RECLAIM_UNAVAILABLE","target_free_gb":target}
    return {"attempted":True,"ok":cp.returncode==0,"exit_code":cp.returncode,"target_free_gb":target}

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
            current["last_reused_at"]=iso(now)
            identity=_identity_from_probe(current.get("route"),state.get("probe") or {})
            for key,value in identity.items():
                if current.get(key) is None and value is not None: current[key]=value
            migration_pending=current.get("policy_epoch")!=POLICY_EPOCH
            if not migration_pending:
                current["expires_at"]=iso(now+dt.timedelta(seconds=ttl_seconds))
            save_state(state_path,state)
            return {**current,"reused":True,"policy_migration_pending":migration_pending,"cohort_state":str(state_path)}
        probe=state.get("probe")
        if refresh_probe or not probe_is_fresh(probe,now):
            probe=probe_all(); state["probe"]=probe
        route,reason=choose_route(kind,probe,state["assignments"])
        recovery=None
        if route!="omen" and reason.startswith("OMEN_") and "_DISK_LOW" in reason:
            recovery=reclaim_omen_scratch(kind)
            if recovery.get("ok"):
                refreshed=probe_omen()
                probe={**probe,"observed_at":iso(utc_now()),"omen":refreshed}
                state["probe"]=probe
                route,reason=choose_route(kind,probe,state["assignments"])
        identity=_identity_from_probe(route,probe)
        a={"schema":SCHEMA,"policy_epoch":POLICY_EPOCH,"decision_id":str(uuid.uuid4()),"work_id":work_id,"kind":kind,"route":route,"reason":reason,"assigned_at":iso(now),"expires_at":iso(now+dt.timedelta(seconds=ttl_seconds)),"probe_observed_at":probe.get("observed_at"),**identity}
        if recovery is not None: a["capacity_recovery"]=recovery
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
