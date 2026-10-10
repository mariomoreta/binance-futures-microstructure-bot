# DASH-V2-48 browser evidence

Actual Chrome from canonical http://127.0.0.1:3020.

- system-before.png: pre-change 1672x941.
- system-desktop.png: final 1672x941.
- system-mobile.png: final 390x941.
- system-controls.png: expanded disclosure after explicit Refresh.
- overview-regression.png: 390x941 compact diagnostics regression.

Reference inspected: design/references/v2-approved/system.png.
Comparison PARTIAL: shared top navigation and source availability deliberately
differ. No synthetic uptime graphs, successful checks or event rows.

Reproduce on the authorized Windows device from repo root:
node scripts/qa-dashboard-system.mjs

Script opens/cleans its own Chrome profile, checks overflow and browser errors,
and clicks only disclosure and Refresh. No runtime mutation is sent.
