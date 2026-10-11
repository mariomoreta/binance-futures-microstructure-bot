from pathlib import Path
import subprocess
root=Path(r"C:\proyectos\binance-futures-dashboard-v2-worktree")
subprocess.run(["node","scripts/qa-dashboard-diagnostics-v70.mjs"],cwd=root,check=True)
subprocess.run(["python",str(Path(__file__).with_name("diagnostic-audit.py"))],check=True)
