"""V2-54 exact published-source audit; no probe/native process operations."""
import argparse, ctypes, hashlib, json, os, re, subprocess, sys, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from datetime import datetime
SHA="b801ab094d64b6b45caabfc7fed22276abb0c0b6"
p=argparse.ArgumentParser()
p.add_argument("--source-root",type=Path,required=True)
p.add_argument("--output",type=Path,required=True)
args=p.parse_args()
root=Path(__file__).resolve().parents[1]
expected=subprocess.check_output(["git","show",SHA+":src/microstructure_probe/control.py"],cwd=root)
actual=(args.source_root/"src/microstructure_probe/control.py").read_bytes()
assert expected.replace(b"\r\n",b"\n")==actual.replace(b"\r\n",b"\n"), "Wrong source snapshot"
assert os.name=="nt"
sys.path.insert(0,str(args.source_root/"src"))
from microstructure_probe import control as pc, dashboard as db
out={"backend_sha":SHA,"control_sha256":hashlib.sha256(actual).hexdigest()}
class Native:
    def __init__(self,callback):
        self.callback=callback; self.argtypes=None; self.restype=None; self.calls=[]
    def __call__(self,*a):
        self.calls.append(a); return self.callback(*a)
stamp="2026-10-11T00:00:00+00:00"
ticks=int(datetime.fromisoformat(stamp).timestamp()*10000000)+116444736000000000
def times(handle,created,*unused):
    created._obj.dwLowDateTime=ticks&0xffffffff
    created._obj.dwHighDateTime=ticks>>32
    return 1
def kernel(term):
    return SimpleNamespace(OpenProcess=Native(lambda *a:0x100000123),
        GetProcessTimes=Native(times),TerminateProcess=term,
        CloseHandle=Native(lambda *a:1),GetLastError=Native(lambda *a:5))
checks=[]
for n in (0,1):
    k=kernel(Native(lambda *a,n=n:n))
    with mock.patch.object(ctypes,"windll",SimpleNamespace(kernel32=k)):
        result=pc._terminate_verified_pid(424243,stamp)
    assert result is bool(n) and len(k.CloseHandle.calls)==1
    checks.append({"native_return":n,"helper_return":result,"closed":True,
       "handle":hex(k.TerminateProcess.calls[0][0]),"return_width":ctypes.sizeof(k.TerminateProcess.restype)})
out["original_refusal_fixed"]=checks
# A native ABI callback exercises ctypes marshalling, unlike the Python fake.
cb=ctypes.WINFUNCTYPE(ctypes.c_int,ctypes.c_void_p,ctypes.c_uint)(lambda *a:256)
address=ctypes.cast(cb,ctypes.c_void_p).value
entry=ctypes.WINFUNCTYPE(ctypes.c_int,ctypes.c_void_p,ctypes.c_uint)(address)
k=kernel(entry)
with mock.patch.object(ctypes,"windll",SimpleNamespace(kernel32=k)):
    result=pc._terminate_verified_pid(424243,stamp)
assert result is False
out["bool_width"]={"synthetic_native_nonzero":256,"helper_return":result,
    "configured_width":ctypes.sizeof(entry.restype),"windows_BOOL_width":ctypes.sizeof(ctypes.c_int),
    "scope":"ABI callback only; no actual Windows process API called"}
with tempfile.TemporaryDirectory(prefix="v2-54-") as folder:
    folder=Path(folder); registry=folder/"runtime.json"
    with mock.patch.dict(os.environ,{"MICROPROBE_RUNTIME_FILE":str(registry)}):
        child=mock.Mock(pid=424243); before=[]
        def spawn_first(*a,**kw):
            with mock.patch.object(pc.os,"getpid",return_value=child.pid):
                reg=pc.try_register(duration_seconds=60,launcher="agent")
            assert reg["registered"]
            before.append(registry.read_bytes())
            return child
        with mock.patch.object(db,"repo_root",return_value=folder), mock.patch.object(pc,"is_canonical_pid",return_value=True), mock.patch.object(pc,"own_creation_time",return_value="CHILD"), mock.patch.object(pc.subprocess,"Popen",side_effect=spawn_first):
            result=pc.start_probe(duration_seconds=60,evidence_dir=folder/"evidence")
        assert result["started"] and child.kill.call_count==0
        assert registry.read_bytes()==before[0]
        assert result["evidence"] is None and pc.read_registry()["evidence"] is None
        logs=list((folder/"evidence").glob("*.log"))
        assert len(logs)==1
        out["actual_child_first_registration"]={"result":result,"kill_calls":0,
            "registry_byte_preserved":True,"created_log_exists":True,
            "registered_log_path":None,"scope":"actual try_register, mocked child/identity"}
        out["missing_log_snapshot"] = pc.collect_supervision_snapshot(pc.read_registry())
        pc._close_log_handles(child.pid)
        source=(root/"frontend/src/lib/runtime-control.ts").read_text(encoding="utf-8")
        bridge=json.loads(re.search(r'const pureStatusCode=("(?:[^"\\]|\\.)*");',source).group(1))+"print(json.dumps(s))"
        pure=[]
        for state in ("RUNNING","STOPPING","ABORTED","COMPLETED"):
            registry.write_text(json.dumps({"state":state,"pid":424243,"create_time":"INVALID","launcher":"dashboard"}))
            raw=registry.read_bytes()
            response=json.loads(subprocess.check_output([sys.executable,"-c",bridge],cwd=args.source_root,env={**os.environ,"PYTHONPATH":str(args.source_root/"src")},text=True))
            assert registry.read_bytes()==raw and response["state"]==state
            pure.append({"state":state,"bytes_preserved":True})
        registry.unlink()
        response=json.loads(subprocess.check_output([sys.executable,"-c",bridge],cwd=args.source_root,env={**os.environ,"PYTHONPATH":str(args.source_root/"src")},text=True))
        assert not registry.exists() and response["state"]=="STOPPED"
        pure.append({"state":"ABSENT","file_not_created":True})
        out["pure_bridge"]=pure
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(out,indent=2),encoding="utf-8")
print(json.dumps(out,indent=2))
