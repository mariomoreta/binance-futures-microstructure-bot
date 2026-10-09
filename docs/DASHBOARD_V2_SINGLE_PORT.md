# DASH-V2 single canonical port
Dashboard V2: http://127.0.0.1:3020. All Next.js views share this origin. The Python bot dashboard remains http://127.0.0.1:8091 and is NOT controlled here.

## Commands
```powershell
Set-Location 'C:\proyectos\binance-futures-dashboard-v2-worktree\frontend'
npm run build
Set-Location ..
.\scripts\dashboard-v2.ps1 start
.\scripts\dashboard-v2.ps1 status
# after future builds:
.\scripts\dashboard-v2.ps1 restart
```
Only manage the listener registered in `.dashboard-v2-runtime.json` on port 3020, and never terminate another PID if identity is uncertain. Do not stop Python or the agent's processes. Legacy preview ports are obsolete; they have not been shut down without verified ownership.

QA pages: /overview, /movers, /movers/verified, /symbol/BTCUSDT, /opportunities, /opportunities/observations, /opportunities/prospective, /system, /backtest, /paper-lab. BFF read endpoints can return 503 while Python 8091 is stopped, which is NOT integrated-data PASS. All screenshots must be real browser captures on 3020, not illustrative images. Missing values UNKNOWN, not 0; DEMO source isolated.
