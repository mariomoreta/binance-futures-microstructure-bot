from pathlib import Path
import subprocess,hashlib,json,time,os
b=Path(r"C:\proyectos\binance-futures-microstructure-bot")
o=Path(r"C:\proyectos\binance-futures-dashboard-v2-worktree\design\qa\v2-71")
paths=[b/"data/microprobe.db",b/"data/historical/historical.db",b/"logs/probe_runtime.json"]
def hashes():return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
before=hashes();t=time.monotonic()
with (o/"backend-isolated-final.txt").open("wb") as log:r=subprocess.run(["python","run_tests.py"],cwd=b,stdout=log,stderr=subprocess.STDOUT)
after=hashes()
result={"exit":r.returncode,"elapsed_s":round(time.monotonic()-t,3),"hashes_before":before,"hashes_after":after,"canonical_bytes_unchanged":before==after}
(o/"backend-isolated-final.json").write_bytes(json.dumps(result,indent=2).encode())
print(json.dumps(result))
assert r.returncode==0 and before==after
