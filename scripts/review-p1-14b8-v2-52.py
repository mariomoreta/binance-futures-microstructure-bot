"""V2-52 exact-SHA review. Temp registries and mocked OS calls only."""
import ctypes, hashlib, json, os, re, subprocess, sys, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
BACKEND=Path(r"C:\proyectos\binance-futures-microstructure-bot")
sys.path.insert(0,str(BACKEND/"src"))
from microstructure_probe import control as pc
from microstructure_probe import dashboard as db
assert os.name=="nt", "This native-boundary audit requires Windows; no fallback OS actions"
SHA="55efaa2b171c83701f6736ab6e6374869a733af1"
assert subprocess.check_output(["git","rev-parse","HEAD"],cwd=BACKEND,text=True).strip()==SHA
canonical=pc.registry_path()
digest=lambda: hashlib.sha256(canonical.read_bytes()).hexdigest() if canonical.exists() else None
before=digest()
root=Path(__file__).resolve().parents[1]
source=(root/"frontend/src/lib/runtime-control.ts").read_text(encoding="utf-8")
bridge=json.loads(re.search(r'const pureStatusCode=("(?:[^"\\]|\\.)*");',source).group(1))+"print(json.dumps(s))"
out={"backend_sha":SHA}
with tempfile.TemporaryDirectory(prefix="v2-52-audit-") as folder:
    folder=Path(folder); registry=folder/"runtime.json"
    with mock.patch.dict(os.environ,{"MICROPROBE_RUNTIME_FILE":str(registry)}):
        registry.write_text(json.dumps({"state":"RUNNING","pid":424243,"create_time":"INVALID","launcher":"dashboard"}))
        original=registry.read_bytes()
        response=json.loads(subprocess.check_output([sys.executable,"-c",bridge],cwd=BACKEND,env={**os.environ,"PYTHONPATH":str(BACKEND/"src")},text=True))
        assert registry.read_bytes()==original
        assert response["state"]=="RUNNING" and response["running"] is True
        out["pure_bridge"]={"response":response,"temporary_registry_unchanged":True,"stored_state_not_os_liveness":True}

        registry.unlink()
        fake_child=mock.Mock(pid=424243)
        def child_registers_first(*args,**kwargs):
            pc.update_registry(lambda _:({"state":"RUNNING","pid":424243,"create_time":"CHILD","launcher":"agent"},True))
            return fake_child
        with mock.patch.object(db,"repo_root",return_value=folder), mock.patch.object(pc,"is_canonical_pid",return_value=True), mock.patch.object(pc,"own_creation_time",return_value="CHILD"), mock.patch.object(pc.subprocess,"Popen",side_effect=child_registers_first):
            started=pc.start_probe(duration_seconds=60,evidence_dir=folder/"evidence")
        assert not started["started"] and fake_child.kill.call_count==1
        out["same_child_registration_race"]={"result":started,"mock_child_kill_calls":fake_child.kill.call_count,"registry_after":pc.read_registry()}

class Native:
    def __init__(self,callback):
        self.callback=callback
        self.argtypes=None
        self.restype=None
        self.calls=[]
    def __call__(self,*args):
        self.calls.append(args)
        return self.callback(*args)
stamp="2026-10-11T00:00:00+00:00"
from datetime import datetime
ticks=int(datetime.fromisoformat(stamp).timestamp()*10000000)+116444736000000000
def times(handle,created,*unused):
    created._obj.dwLowDateTime=ticks&0xffffffff
    created._obj.dwHighDateTime=ticks>>32
    return 1
k=SimpleNamespace(OpenProcess=Native(lambda *a:0x100000123),GetProcessTimes=Native(times),TerminateProcess=Native(lambda *a:0),CloseHandle=Native(lambda *a:1))
with mock.patch.object(ctypes,"windll",SimpleNamespace(kernel32=k)):
    result=pc._terminate_verified_pid(424243,stamp)
assert result is True and len(k.TerminateProcess.calls)==1
out["native_api_failure"]={"os_api_result":0,"helper_returned":result,"terminate_argtypes_configured":k.TerminateProcess.argtypes is not None,"close_argtypes_configured":k.CloseHandle.argtypes is not None,"mock_handle":hex(k.TerminateProcess.calls[0][0]),"real_os_calls":False}
assert digest()==before
out["canonical_registry_sha256_before"]=before
out["canonical_registry_sha256_after"]=digest()
print(json.dumps(out,indent=2,default=str))
