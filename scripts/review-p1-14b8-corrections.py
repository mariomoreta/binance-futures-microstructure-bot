"""Read-only backend review; synthetic registries and mocked termination only."""
import json, os, subprocess, tempfile, threading
from pathlib import Path
from unittest.mock import patch
from microstructure_probe import control as pc
from test_supervision_contract import _run_record, _sup_lease, _sen_lease
expected="8648366ec5ea82a46e4573cf81a53546f666d8d6"
actual=subprocess.check_output(["git","rev-parse","HEAD"],cwd=Path(pc.__file__).resolve().parents[2],text=True).strip()
if actual!=expected:
    raise SystemExit("Refusing review against a different backend SHA: "+actual)
results={"backend_sha":actual}
with tempfile.TemporaryDirectory(prefix="v2-review-") as folder:
    os.environ["MICROPROBE_RUNTIME_FILE"]=str(Path(folder)/"registry.json")
    rec=_run_record(); rec["supervisor"]=_sup_lease(age_s=200); rec["sentinel"]=_sen_lease(age_s=200)
    pc._write_registry(rec)
    original_bytes=Path(os.environ["MICROPROBE_RUNTIME_FILE"]).read_bytes()
    threads=[threading.Thread(target=pc._heartbeat_lease) for _ in range(2)]+[threading.Thread(target=pc._heartbeat_sentinel) for _ in range(2)]
    for t in threads:t.start()
    for t in threads:t.join(20)
    results["published_heartbeat_fixture"]={"owners":[rec["supervisor"]["pid"],rec["sentinel"]["pid"]],"self_pid":os.getpid(),"byte_equivalent_record":Path(os.environ["MICROPROBE_RUNTIME_FILE"]).read_bytes()==original_bytes}
    rec=_run_record(); rec["supervisor"]=_sup_lease(age_s=200,pid=os.getpid()); rec["sentinel"]=_sen_lease(age_s=200,pid=os.getpid())
    pc._write_registry(rec)
    threads=[threading.Thread(target=lambda:[pc._heartbeat_lease(consecutive_failures=11) for _ in range(25)]) for _ in range(2)]+[threading.Thread(target=lambda:[pc._heartbeat_sentinel(failures=22) for _ in range(25)]) for _ in range(2)]
    for t in threads:t.start()
    for t in threads:t.join(20)
    final=pc.read_registry()
    results["owned_heartbeat_writes"]={"supervisor_advanced":final["supervisor"]["last_check_at"]!=rec["supervisor"]["last_check_at"],"sentinel_advanced":final["sentinel"]["last_check_at"]!=rec["sentinel"]["last_check_at"],"failures":[final["supervisor"]["consecutive_failures"],final["sentinel"]["consecutive_failures"]],"run_preserved":final["state"]=="RUNNING" and final["pid"]==424243}
    rec=_run_record(); rec["supervisor"]=_sup_lease(pid=999999)
    pc._write_registry(rec)
    with patch.object(pc,"is_canonical_pid",return_value=True),patch.object(pc,"_terminate_verified_pid") as term,patch("microstructure_probe.dashboard.pid_is_ours",return_value=False):
        out=pc.enforce_abort({"rule":"review","reason":"mock only"},owner_kind="supervisor")
    results["foreign_owner_enforce"]={"terminate_called":term.called,"result":out,"registry_state":pc.read_registry()["state"]}
    rec=_run_record(); rec["supervisor"]=_sup_lease(pid=os.getpid()); pc._write_registry(rec)
    def race(_):
        def transform(live):
            live["state"]="COMPLETED";live["supervisor"]["pid"]=999999
            return live,True
        pc.update_registry(transform)
        return True
    with patch.object(pc,"is_canonical_pid",side_effect=race),patch.object(pc,"_terminate_verified_pid") as term,patch("microstructure_probe.dashboard.pid_is_ours",return_value=False):
        out=pc.enforce_abort({"rule":"review","reason":"mock only"},owner_kind="supervisor")
    results["terminal_takeover_race"]={"terminate_called":term.called,"result":out,"registry_state":pc.read_registry()["state"],"lease_owner":pc.read_registry()["supervisor"]["pid"]}
    rec=_run_record(); rec["supervisor"]=_sup_lease(pid=os.getpid()); pc._write_registry(rec)
    with patch.object(pc,"is_canonical_pid",return_value=True),patch.object(pc,"_write_registry",side_effect=OSError("synthetic failure")),patch.object(pc,"_terminate_verified_pid") as term,patch("microstructure_probe.dashboard.pid_is_ours",return_value=False):
        out=pc.enforce_abort({"rule":"review","reason":"mock only"},owner_kind="supervisor")
    results["stopping_write_failed"]={"terminate_called":term.called,"result":out}
    os.environ.pop("MICROPROBE_RUNTIME_FILE",None)
print(json.dumps(results,indent=2))
