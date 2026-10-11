"""Audit 0786617 only; synthetic registries and mocked process termination."""
import copy,json,os,subprocess,tempfile
from pathlib import Path
from unittest.mock import patch
from microstructure_probe import control as pc
from test_enforce_abort_fencing import _run_record,_owned_lease,_decision
expected="07866176559954818dfccf880106bdf22feab40d"
actual=subprocess.check_output(["git","rev-parse","HEAD"],cwd=Path(pc.__file__).resolve().parents[2],text=True).strip()
if actual!=expected:raise SystemExit("Different backend SHA: "+actual)
out={"backend_sha":actual}
with tempfile.TemporaryDirectory(prefix="v2-51-") as folder:
 os.environ["MICROPROBE_RUNTIME_FILE"]=str(Path(folder)/"registry.json")
 for kind in ("supervisor","sentinel"):
  rec=_run_record();rec[kind]=_owned_lease(kind);pc._write_registry(rec)
  original=pc.update_registry;calls=[0]
  def swap_after_claim(transform):
   result=original(transform);calls[0]+=1
   if calls[0]==1 and result[0]:
    def swap(live):
     live[kind]["pid"]=999999
     return live,True
    original(swap)
   return result
  with patch.object(pc,"is_canonical_pid",return_value=True),patch.object(pc,"update_registry",side_effect=swap_after_claim),patch.object(pc,"_terminate_verified_pid") as term,patch("microstructure_probe.dashboard.pid_is_ours",return_value=False):
   result=pc.enforce_abort(_decision(),owner_kind=kind)
  out[kind+"_after_claim_takeover"]={"terminate_called":term.called,"result":result,"lease_owner":pc.read_registry()[kind]["pid"]}
  rec=_run_record();rec[kind]=_owned_lease(kind,watched=999999);pc._write_registry(rec)
  with patch.object(pc,"is_canonical_pid",return_value=True),patch.object(pc,"_terminate_verified_pid") as term,patch("microstructure_probe.dashboard.pid_is_ours",return_value=False):
   result=pc.enforce_abort(_decision(),owner_kind=kind)
  out[kind+"_wrong_run_lease"]={"terminate_called":term.called,"result":result}
 old=_run_record();old["supervisor"]=_owned_lease("supervisor")
 new=copy.deepcopy(old);new["state"]="ABORTED";new["abort_reason"]="preserve-me"
 pc._write_registry(new)
 with patch.object(pc,"read_registry",return_value=old),patch.object(pc,"is_canonical_pid",return_value=False):
  result=pc.status()
 final=json.loads(Path(os.environ["MICROPROBE_RUNTIME_FILE"]).read_text())
 out["status_overwrites_terminal"]={"output_state":result["state"],"stored_state":final["state"],"abort_reason":final.get("abort_reason")}
 os.environ.pop("MICROPROBE_RUNTIME_FILE",None)
print(json.dumps(out,indent=2))
