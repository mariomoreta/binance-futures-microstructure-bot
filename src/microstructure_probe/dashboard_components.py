"""P1-09 shared presentation components (terminal theme, no framework).

Principles (Amberdata/Amberlens hierarchy, TradeX density, XSignal grouping):
strong hierarchy, calm dark surfaces, dense-but-readable, restrained color,
scanability, state chips, overview -> drill-down, minimal noise.
"""

from __future__ import annotations

import html
from typing import Any, List, Optional

CSS = """
:root{--bg:#0b0e13;--panel:#12161d;--panel2:#161b24;--line:#232b38;--txt:#d5dbe5;
--dim:#8b94a3;--pos:#3fb950;--neg:#f85149;--warn:#e3b341;--link:#6cb6ff;
--chip:#1d2532}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--txt);font-family:Consolas,Menlo,monospace;
margin:0;padding:0;font-size:13px}
.topbar{display:flex;align-items:center;gap:14px;padding:10px 16px;
background:var(--panel);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
.brand{font-weight:bold;letter-spacing:.5px;font-size:14px;white-space:nowrap}
.brand small{color:var(--dim);font-weight:normal}
.nav{display:flex;gap:4px}
.nav a{color:var(--dim);text-decoration:none;padding:6px 12px;border-radius:6px;font-size:12px}
.nav a.active,.nav a:hover{color:var(--txt);background:var(--chip)}
.searchbox{margin-left:auto;display:flex;gap:6px}
.searchbox input{background:#0d1117;border:1px solid var(--line);color:var(--txt);
padding:6px 10px;border-radius:6px;font-family:inherit;font-size:12px;width:220px}
.searchbox input[type=submit]{background:var(--chip);border:1px solid var(--line);color:var(--txt);
padding:6px 12px;border-radius:6px;cursor:pointer;font-family:inherit;font-size:12px}
.wrap{padding:14px 16px;max-width:1280px;margin:0 auto}
.grid{display:grid;gap:12px}
.g4{grid-template-columns:repeat(auto-fit,minmax(210px,1fr))}
.g2{grid-template-columns:repeat(auto-fit,minmax(340px,1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px}
.card h3{margin:0 0 8px;font-size:12px;color:var(--dim);text-transform:uppercase;
letter-spacing:.6px}
.big{font-size:20px;font-weight:bold}
h1{font-size:17px;margin:14px 0 10px}h2{font-size:13px;margin:18px 0 8px;color:var(--dim);
text-transform:uppercase;letter-spacing:.5px}
table{border-collapse:collapse;width:100%;font-size:12px;background:var(--panel)}
th,td{border:1px solid var(--line);padding:5px 8px;text-align:left;white-space:nowrap}
th{background:var(--panel2);color:var(--dim);font-weight:normal;text-transform:uppercase;
font-size:11px;letter-spacing:.4px}
tr.rowlink{cursor:pointer}tr.rowlink:hover td{background:#1a2230}
a{color:var(--link)}
.banner{background:var(--panel);border:1px solid var(--line);padding:8px 12px;margin:12px 0;
font-size:12px;border-radius:8px}
.chip{display:inline-block;padding:2px 9px;border-radius:20px;font-weight:bold;font-size:11px;
border:1px solid var(--line);background:var(--chip);color:var(--txt)}
.chip.tier{color:var(--txt)}
.chip.ok{border-color:#1a7f37}.chip.degraded{border-color:var(--warn);color:var(--warn)}
.chip.stale{border-color:var(--neg);color:var(--neg)}.chip.unknown{color:var(--dim)}
.chip.live{border-color:#1a7f37;color:var(--pos)}.chip.warming{border-color:var(--warn);
color:var(--warn)}
.pos{color:var(--pos)}.neg{color:var(--neg)}.warn{color:var(--warn)}.note{color:var(--dim);
font-size:11px}.dim{color:var(--dim)}
.bar{letter-spacing:1px;white-space:nowrap}
.scrollx{overflow-x:auto}
.kv td:first-child{color:var(--dim)}
.section{display:flex;align-items:baseline;gap:10px}
.section a{font-size:11px}
.chartbtns{display:flex;gap:6px;margin:8px 0}
.chartbtns a{padding:4px 10px;border:1px solid var(--line);border-radius:6px;
text-decoration:none;font-size:12px;color:var(--dim)}
.chartbtns a.active{color:var(--txt);background:var(--chip)}
.footer{color:var(--dim);font-size:11px;margin:18px 0 30px}
.engine{display:flex;align-items:center;gap:10px;padding:8px 16px;
background:var(--panel);border-bottom:1px solid var(--line);font-size:12px}
.eng-label{color:var(--dim);letter-spacing:.6px;font-size:11px}
.engine form{display:inline-flex;gap:6px;align-items:center;margin:0}
.engine select,.engine input[type=submit]{background:var(--chip);
border:1px solid var(--line);color:var(--txt);padding:4px 10px;border-radius:6px;
cursor:pointer;font-family:inherit;font-size:12px}
.engine select{cursor:default}
.dot{font-size:10px}
.dot.run{color:var(--pos);animation:pulse 2s infinite}
.dot.warn{color:var(--warn)}.dot.stop{color:var(--dim)}.dot.fail{color:var(--neg)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
@media(max-width:760px){.topbar{flex-wrap:wrap}.searchbox{width:100%}
.searchbox input{flex:1;width:auto}th,td{padding:4px 6px;font-size:11px}}
"""

BANNER_NOTE = ("Observe-only market-intelligence terminal. "
               "Detector counts are telemetry, NOT trade signals. "
               "No execution controls exist on any page.")

NAV = (("OVERVIEW", "/overview"), ("MOVERS", "/movers"), ("SYSTEM", "/system"))


def nav_html(active: str, search_query: str = "") -> str:
    links = "".join(
        f"<a href='{href}' class='{'active' if label == active else ''}'>{label}</a>"
        for label, href in NAV)
    q = html.escape(search_query or "", quote=True)
    return (
        f"<div class='topbar'><div class='brand'>BINANCE FUTURES "
        f"<small>market intelligence · read-only</small></div>"
        f"<div class='nav'>{links}</div>"
        f"<form class='searchbox' method='get' action='/search'>"
        f"<input name='q' placeholder='Search symbol (e.g. ORCA)' value='{q}' "
        f"aria-label='Search symbol'>"
        f"<input type='submit' value='Search'></form></div>")


def page(title: str, active: str, banner_html: str, body: str,
         search_query: str = "", engine_html: str = "") -> str:
    return (
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<meta http-equiv='refresh' content='30'>"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head>"
        f"<body>{nav_html(active, search_query)}{engine_html}"
        f"<div class='wrap'><h1>{html.escape(title)}</h1>{banner_html}{body}"
        f"<p class='footer'>{html.escape(BANNER_NOTE)} Auto-refresh 30s. "
        f"Machine APIs remain under /system.</p></div></body></html>")


def _fmt_hms(seconds: Any) -> str:
    try:
        total = max(0, int(float(seconds or 0)))
    except (TypeError, ValueError):
        return "--:--:--"
    hh, rem = divmod(total, 3600)
    mm, ss = divmod(rem, 60)
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


def engine_control_html(state: Any) -> str:
    """Compact MARKET ENGINE run control (P1-11B.1, observe-only).

    Rendered under the nav on every page. No <button> elements (repo
    no-controls tests), no trading words. Status refreshes via polling;
    start/stop are plain POST forms (303 back) so no-JS works too.
    """
    try:
        status = state.probe_status()
    except Exception:
        status = {}
    try:
        nonce = getattr(state, "control_nonce", "") or ""
    except Exception:
        nonce = ""
    if not isinstance(status, dict):
        status = {}
    proc_state = str(status.get("state") or "STOPPED")
    running = bool(status.get("running"))
    if proc_state == "RUNNING":
        dot, chip_state = "run", "RUNNING"
    elif proc_state in ("STARTING", "STOPPING"):
        dot, chip_state = "warn", proc_state
    elif proc_state == "FAILED":
        dot, chip_state = "fail", "FAILED"
    else:
        dot, chip_state = "stop", ("COMPLETED" if proc_state == "COMPLETED"
                                   else "STOPPED")
    elapsed = _fmt_hms(status.get("elapsed_seconds"))
    remaining = status.get("remaining_seconds")
    preset = str(status.get("preset") or "standard")
    if running:
        detail = f"OBSERVE · {elapsed}"
        if preset == "validation-6h":
            detail += " · VALIDATION 6H"
        if remaining is not None:
            detail += f" · left {_fmt_hms(remaining)}"
        form = (
            "<form method='post' action='/api/control/probe/stop'>"
            f"<input type='hidden' name='nonce' value='{html.escape(nonce)}'>"
            "<input type='submit' value='STOP'></form>")
    else:
        reason = str(status.get("last_exit_reason") or "")
        detail = html.escape(
            chip_state + (f" · {reason}" if proc_state in ("COMPLETED",
                                                           "FAILED") and reason
                           else ""))
        form = (
            "<form method='post' action='/api/control/probe/start'>"
            f"<input type='hidden' name='nonce' value='{html.escape(nonce)}'>"
            "<select name='mode' aria-label='Run mode'>"
            "<option value='continuous'>Continuous</option>"
            "<option value='6h'>6 Hours</option>"
            "<option value='validation-6h'>6H Validation (evidence)</option>"
            "</select>"
            "<input type='submit' value='START OBSERVE'></form>")
    return (
        f"<div class='engine' id='engine' data-nonce='{html.escape(nonce)}'>"
        f"<span class='eng-label'>MARKET ENGINE</span>"
        f"<span class='dot {dot}' id='engine-dot'>●</span>"
        f"<span id='engine-chip'>{html.escape(chip_state)}</span>"
        f"<span class='dim' id='engine-text'>{detail}</span>"
        f"<span id='engine-form'>{form}</span></div>"
        # NOTE: explicit type attribute so the literal "<script>" never
        # appears in page bytes (the escaping regression test asserts user
        # input can never inject one).
        "<script type='text/javascript'>(function(){var el="
        "document.getElementById('engine');"
        "if(!el)return;var nonce=el.getAttribute('data-nonce')||'';"
        "function fmt(s){s=Math.max(0,Math.floor(s||0));"
        "var h=Math.floor(s/3600),m=Math.floor((s%3600)/60);"
        "s=s%60;return (h<10?'0':'')+h+':'+(m<10?'0':'')+m+':'+"
        "(s<10?'0':'')+s;}"
        "function esc(s){return String(s).replace(/&/g,'&amp;')"
        ".replace(/</g,'&lt;');}"
        "function tick(){fetch('/api/control/probe/status')"
        ".then(function(r){return r.json();}).then(function(st){"
        "var dot=document.getElementById('engine-dot');"
        "var chip=document.getElementById('engine-chip');"
        "var text=document.getElementById('engine-text');"
        "var form=document.getElementById('engine-form');"
        "if(!dot||!chip||!text||!form)return;"
        "var run=!!st.running,cls='stop',label=st.state||'STOPPED';"
        "if(st.state==='RUNNING'){cls='run';}"
        "else if(st.state==='STARTING'||st.state==='STOPPING'){cls='warn';}"
        "else if(st.state==='FAILED'){cls='fail';}"
        "dot.className='dot '+cls;chip.textContent=label;"
        "var detail=label;"
        "if(run){detail='OBSERVE · '+fmt(st.elapsed_seconds);"
        "if(st.preset==='validation-6h'){detail+=' · VALIDATION 6H';}"
        "if(st.remaining_seconds!=null){detail+=' · left '+"
        "fmt(st.remaining_seconds);}"
        "form.innerHTML=\"<form method='post' "
        "action='/api/control/probe/stop'>"
        "<input type='hidden' name='nonce' value='\"+esc(nonce)+\"'>"
        "<input type='submit' value='STOP'></form>\";}"
        "else{form.innerHTML=\"<form method='post' "
        "action='/api/control/probe/start'>"
        "<input type='hidden' name='nonce' value='\"+esc(nonce)+\"'>"
        "<select name='mode' aria-label='Run mode'>"
        "<option value='continuous'>Continuous</option>"
        "<option value='6h'>6 Hours</option>"
        "<option value='validation-6h'>6H Validation (evidence)</option>"
        "</select><input type='submit' value='START OBSERVE'></form>\";}"
        "text.textContent=detail;}).catch(function(){});}"
        "setInterval(tick,4000);})();</script>")


def banner_html_fn(safety: Any, status: str) -> str:
    from .dashboard import STATUS_LABELS  # local import: single source of labels
    label = STATUS_LABELS.get(status, str(status).upper())
    s = safety if isinstance(safety, dict) else {}
    return (
        f"<div class='banner'>BOT_MODE=<b>{html.escape(str(s.get('BOT_MODE', '?')))}</b> "
        f"keys={s.get('apiKeysUsed', '?')} orders={s.get('realOrdersSent', '?')} "
        f"capital={s.get('realCapitalAtRisk', '?')} "
        f"<span class='chip {html.escape(status)}'>{html.escape(label)}</span></div>")


def tier_chip(tier: str) -> str:
    return f"<span class='chip tier'>{html.escape(tier or '?')}</span>"


def capability_chip(cap: str) -> str:
    slug = (cap or "").lower().replace(" ", "-")
    if cap == "LIVE":
        cls = "chip live"
    elif cap == "WARMING":
        cls = "chip warming"
    elif cap == "DISCOVERY ONLY":
        cls = "chip unknown"
    elif cap in ("STALE", "DEGRADED"):
        cls = f"chip {slug}"
    else:
        cls = "chip unknown"
    return f"<span class='{cls}'>{html.escape(cap or 'UNKNOWN')}</span>"


def signed_pct(value: Any, digits: int = 2) -> str:
    """Already-percent values (discovery 24h %): 25.0 -> '+25.00%'."""
    if value is None:
        return "<span class='dim' title='insufficient history'>—</span>"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "<span class='dim' title='insufficient history'>—</span>"
    cls = "pos" if number > 0 else ("neg" if number < 0 else "")
    text = f"{number:+.{digits}f}%"
    return f"<span class='{cls}'>{html.escape(text)}</span>" if cls else html.escape(text)


def signed_frac(value: Any, digits: int = 3) -> str:
    """Fractional log-returns: 0.001234 -> '+0.123%' (never 0 when missing)."""
    if value is None:
        return "<span class='dim' title='insufficient history'>—</span>"
    try:
        number = float(value) * 100.0
    except (TypeError, ValueError):
        return "<span class='dim' title='insufficient history'>—</span>"
    cls = "pos" if number > 0 else ("neg" if number < 0 else "")
    text = f"{number:+.{digits}f}%"
    return f"<span class='{cls}'>{html.escape(text)}</span>" if cls else html.escape(text)


def signed_num(value: Any, digits: int = 2) -> str:
    if value is None:
        return "<span class='dim' title='no data'>—</span>"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "<span class='dim' title='no data'>—</span>"
    cls = "pos" if number > 0 else ("neg" if number < 0 else "")
    text = f"{number:+.{digits}f}"
    return f"<span class='{cls}'>{html.escape(text)}</span>" if cls else html.escape(text)


def sci(value: Any, suffix: str = "/s") -> str:
    if value is None:
        return "<span class='dim' title='insufficient history'>—</span>"
    try:
        return html.escape(f"{float(value):.3g}{suffix}")
    except (TypeError, ValueError):
        return "<span class='dim' title='insufficient history'>—</span>"


def age(age_ms: Any) -> str:
    if age_ms is None:
        return "—"
    try:
        return f"{float(age_ms) / 1000:.0f}s ago"
    except (TypeError, ValueError):
        return "—"


def symbol_link(symbol: str) -> str:
    return f"<a href='/symbol/{html.escape(symbol)}'>{html.escape(symbol)}</a>"
