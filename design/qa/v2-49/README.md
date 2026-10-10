# DASH-V2-49 — actual browser evidence

Before: original V2 frame, 13 routes at 1672/390 (26 captures).
After: final shared frame, 13 routes at 1672/1366/390 (39 viewport captures).
Additional 13 full-page desktop captures inspect lower content; expanded System
and open mobile navigation captured separately. Contact sheets summarize views.

After/results.json: all 39 geometry/landmark/active-route checks PASS;
zero unexpected browser errors and 18 handled source-unavailable HTTP 503s.
After/full-results.json: 13 full-page runs PASS; six handled provider 503s.
Providers: live-movers, opportunities, price-series. Python HTTP source was
stopped; SQLite sources remained readable. Error/empty states are intentional
and do not establish working live integration.

Reference contents compared and corrected per
../../references/v2-approved/ASSET_AUDIT_STATUS.md (relative from this folder:
../../references/v2-approved/). See docs/DASHBOARD_V2_49_VISUAL_VALIDATION.md
for per-screen PARTIAL/MISSING/no-dedicated-reference verdicts.

Reproduce from repository root on the authorized Windows device:
node scripts/qa-dashboard-all.mjs
node scripts/qa-dashboard-all.mjs full

The script checks the running V2 only, creates/removes its own Chrome profile,
opens/closes menu and System disclosure, and sends no runtime mutation.
Reproducing the historical before captures requires the original baseline HEAD;
'before' mode is permissive evidence capture, not a parity or availability PASS.
