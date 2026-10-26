""" Probe interactivo: arranca el stack local y prueba el crosshair. """
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from market_stream_local_acceptance import (  # noqa: E402
    FakeKlineServer, prepare_shadow, seed_cache, STEP_MS)
from indicators_v1_public_demo import (  # noqa: E402
    BADGE, CHART, CURSOR, DASHBOARD_URL, SERVICE_PORT, free_port,
    http_json, seed_with_gap, wait_until, process_name, git_sha)


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="indicators_probe_"))
    cache_db = workdir / "market_cache.db"
    seed_with_gap(cache_db)
    shadow = prepare_shadow(workdir)

    fake_port = free_port()
    fake = FakeKlineServer(fake_port, Path(shadow["fake_log"]))
    fake.start()

    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(ROOT / "src"),
        "MICROPROBE_MARKET_CACHE_DB": str(cache_db),
        "MICROPROBE_STREAM_URL": f"http://127.0.0.1:{SERVICE_PORT}",
    })
    service = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "market_stream_service.py"),
         "--port", str(SERVICE_PORT), "--transport", "local",
         "--base-url", f"ws://127.0.0.1:{fake_port}",
         "--max-seconds", "1200"],
        cwd=str(ROOT), env=env,
        stdout=open(workdir / "service.log", "w", encoding="utf-8"),
        stderr=subprocess.STDOUT)

    darius_env = env.copy()
    darius_env.update({
        "MARKET_EXPLORER_ROOT": shadow["root"],
        "MICROPROBE_TEST_CANON_SRC": shadow["canon_src"],
        "MICROPROBE_TEST_CANON_SCRIPT": shadow["canon_script"],
        "MICROPROBE_TEST_CONN_LOG": shadow["conn_log"],
    })
    import urllib.request
    def dashboard_up():
        try:
            with urllib.request.urlopen(DASHBOARD_URL, timeout=2) as r:
                return r.status == 200
        except Exception:
            return False
    dashboard = subprocess.Popen(
        ["cmd", "/c", "npm", "run", "start"], cwd=str(ROOT / "frontend"),
        env=darius_env,
        stdout=open(workdir / "dashboard.log", "w", encoding="utf-8"),
        stderr=subprocess.STDOUT)
    wait_until(dashboard_up, 90, 0.5, "dashboard")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1280, "height": 960},
                                   locale="es-ES").new_page()
        urls: list[str] = []
        served: list[str] = []
        failed: list[str] = []
        page.on("request", lambda req: urls.append(req.url)
                if "/api/v1/market-" in req.url else None)
        page.on("response", lambda res: served.append(
            f"{res.status} {res.url}"[:130])
            if "/api/v1/market-" in res.url else None)
        page.on("requestfailed", lambda req: failed.append(
            f"{req.failure} {req.url}"[:130])
            if "/api/v1/market-" in req.url else None)
        page.goto(f"{DASHBOARD_URL}/market-lab", wait_until="domcontentloaded")
        page.fill('[data-testid="explorer-query"]', "BTCUSDT")
        page.click('[data-testid="explorer-search"]')
        page.wait_for_selector('[data-testid="explorer-open-BTCUSDT"]')
        page.click('[data-testid="explorer-open-BTCUSDT"]')
        page.wait_for_selector(CHART, timeout=60_000)
        time.sleep(2.0)
        first_canvas = page.locator(f"{CHART} canvas").first
        first_canvas.scroll_into_view_if_needed()
        box = first_canvas.bounding_box()
        print("pane canvas box:", box)
        cx = box["x"] + box["width"] * 0.5
        cy = box["y"] + box["height"] * 0.5
        page.mouse.move(cx, cy)
        # Reproduce demo: evaluate fetch del payload 1h antes del switch 1m.
        first_url = next((u for u in urls if "market-series?" in u
                          and "interval=1h" in u), None)
        print("1h series url found:", bool(first_url), "| urls:", len(urls))
        got = page.evaluate(
            "url => fetch(url).then(r => r.text())", first_url)
        print("evaluate fetch 1h:", str(got)[:180])
        t0 = time.monotonic()
        base = len(served)
        page.select_option('[data-testid="explorer-interval"]', "1m")
        print("select_option OK")
        # Compara: el mismo CLI invocado fuera de Node (mismos args 1m).
        import threading
        def cli_probe():
            import subprocess
            import urllib.request
            base_url = first_url.split("?")[0]
            query = (first_url.split("?")[1]
                     .replace("interval=1h", "interval=1m"))
            url = f"{base_url}?{query}"
            t = time.monotonic()
            try:
                with urllib.request.urlopen(url, timeout=60) as resp:
                    body = resp.read()
                print(f"[cli-probe?] via BFF fuera del navegador: "
                      f"{len(body)} bytes en {round(time.monotonic()-t,1)}s")
            except Exception as exc:
                print("[cli-probe?] BFF fetch fallo:", repr(exc)[:120],
                      f"tras {round(time.monotonic()-t,1)}s")
        for step_wait in range(12):
            time.sleep(1.0)
            new = served[base:]
            hits = [u[:110] for u in new if "interval=1m" in u]
            page.mouse.move(cx, cy)
            cur = page.locator(CURSOR).inner_text()
            print(f"t+{step_wait+1}s cursor:", repr(cur[:46]),
                  "| new req:", [u[:66] for u in urls if "interval=1m" in u][-1:],
                  "| new responses:", len(new))
            if hits:
                break
        cli_probe()
        time.sleep(1)
        browser.close()
    service.terminate()
    dashboard.terminate()
    fake.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
