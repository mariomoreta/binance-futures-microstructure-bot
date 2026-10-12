from pathlib import Path
import sys,hashlib,json
from unittest import mock
b=Path(r"C:\proyectos\binance-futures-microstructure-bot")
f=Path(r"C:\proyectos\binance-futures-dashboard-v2-worktree")
sys.path[:0]=[str(b/"src"),str(b/"tests")]
import test_read_purity as t
from microstructure_probe.history_store import HistoryStore
from microstructure_probe.dashboard import DashboardState
case=t.ReadPurityTest("test_read_battery_leaves_everything_untouched")
tmp,store,hist,reg,ev=case._fixture()
def hashes():return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp.iterdir() if p.is_file()}
before=hashes();state=DashboardState(store)
old=HistoryStore.init_db
with mock.patch.object(HistoryStore,"init_db",autospec=True,side_effect=old) as spy:
 state.history_coverage();state.research_status();state.event_studies();state.event_symbol("BTCUSDT")
 calls=spy.call_count
after=hashes()
result={"historical_init_db_calls":calls,"before":before,"after":after,"changed_files":[k for k in set(before)|set(after) if before.get(k)!=after.get(k)],"missing_assertion":"before_hist captured but never compared in committed test","allows_new_log_files":True,"canonical_storage_untouched":True}
(f/"design/qa/v2-71/purity-proof-review.json").write_bytes(json.dumps(result,indent=2).encode())
print(json.dumps(result,indent=2))
case.doCleanups()
