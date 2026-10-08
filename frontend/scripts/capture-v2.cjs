// Isolated Chrome DevTools screenshot and viewport-overflow QA for Dashboard V2.
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { spawn } = require("node:child_process");
const [route = "/opportunities", widthArg = "390", heightArg = "850", output = "v2-qa.png"] = process.argv.slice(2);
const width = Number(widthArg), height = Number(heightArg);
const port = Number(process.env.V2_CDP_PORT || 9237);
const base = process.env.V2_PREVIEW_URL || "http://127.0.0.1:3008";
const chrome = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const profile = path.join(os.tmpdir(), "dashboard-v2-cdp-qa-" + process.pid);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function main() {
  if (!Number.isInteger(width) || width < 320 || !Number.isInteger(height)) throw new Error("Invalid viewport");
  spawn(chrome, [
    "--headless=new", "--disable-gpu", "--no-first-run",
    "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=" + port,
    "--user-data-dir=" + profile, "--window-size=1200,900", base + route
  ], { stdio: "ignore" });
  let pages;
  for (let i = 0; i < 60; i++) {
    try {
      const response = await fetch("http://127.0.0.1:" + port + "/json/list");
      pages = await response.json();
      if (pages.some(p => p.type === "page" && p.webSocketDebuggerUrl)) break;
    } catch {}
    await sleep(250);
  }
  const page = pages?.find(p => p.type === "page" && p.url.includes(route));
  if (!page) throw new Error("CDP page not available");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });
  let seq = 0;
  const pending = new Map();
  ws.addEventListener("message", event => {
    const message = JSON.parse(event.data);
    if (!pending.has(message.id)) return;
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message));
    else resolve(message.result);
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++seq;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width, height, deviceScaleFactor: 1, mobile: width <= 700,
    screenWidth: width, screenHeight: height
  });
  await send("Page.reload", { ignoreCache: true });
  await sleep(1300);
  const measurement = await send("Runtime.evaluate", {
    expression: "JSON.stringify({innerWidth:innerWidth,documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,mainWidth:document.querySelector('main')?.getBoundingClientRect().width})",
    returnByValue: true
  });
  const dimensions = JSON.parse(measurement.result.value);
  const capture = await send("Page.captureScreenshot", {
    format: "png", captureBeyondViewport: false, fromSurface: true
  });
  fs.mkdirSync(path.dirname(path.resolve(output)), { recursive: true });
  fs.writeFileSync(path.resolve(output), Buffer.from(capture.data, "base64"));
  console.log(JSON.stringify({ route, viewport: width + "x" + height, ...dimensions, output }));
  await send("Browser.close").catch(() => {});
  ws.close();
  if (dimensions.documentWidth > width || dimensions.bodyWidth > width) {
    console.error("GLOBAL_HORIZONTAL_OVERFLOW");
    process.exitCode = 2;
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
