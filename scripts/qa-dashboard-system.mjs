import {spawn} from "node:child_process";
import {mkdtemp, readFile, mkdir, writeFile, rm} from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const chrome = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const root = process.cwd();
const out = path.join(root, "design/qa/v2-48");
await mkdir(out, {recursive:true});
const profile = await mkdtemp(path.join(os.tmpdir(), "dashboard-v2-48-"));
const child = spawn(chrome, ["--headless=new", "--disable-gpu", "--no-first-run",
  "--remote-debugging-port=0", "--user-data-dir="+profile, "about:blank"], {stdio:"ignore"});
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let ws;
try {
  let port;
  for (let n=0;n<100;n++) {
    try {port = Number((await readFile(path.join(profile,"DevToolsActivePort"),"utf8")).split("\n")[0]);break;} catch {await delay(100);}
  }
  if (!port) throw Error("No DevTools port");
  const targets = await (await fetch("http://127.0.0.1:"+port+"/json/list")).json();
  ws = new WebSocket(targets.find(t=>t.type==="page").webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.addEventListener("open",resolve,{once:true});ws.addEventListener("error",reject,{once:true});});
  let id=0;
  const waiting = new Map(), errors=[];
  ws.addEventListener("message", e=>{
    const x=JSON.parse(e.data);
    if(x.id){const p=waiting.get(x.id);waiting.delete(x.id);x.error?p.reject(Error(JSON.stringify(x.error))):p.resolve(x.result);}
    if(x.method==="Runtime.exceptionThrown")errors.push(x.params.exceptionDetails.text);
    if(x.method==="Log.entryAdded"&&x.params.entry.level==="error")errors.push(x.params.entry.text);
  });
  const call=(method,params={})=>new Promise((resolve,reject)=>{
    const number=++id;waiting.set(number,{resolve,reject});ws.send(JSON.stringify({id:number,method,params}));
  });
  const evaluate=async expression=>{
    const result=await call("Runtime.evaluate",{expression,returnByValue:true,awaitPromise:true});
    if(result.exceptionDetails)throw Error(result.exceptionDetails.text);
    return result.result.value;
  };
  await call("Page.enable");await call("Runtime.enable");await call("Log.enable");
  const capture=async(name,width)=>{
    await call("Emulation.setDeviceMetricsOverride",{width,height:941,deviceScaleFactor:1,mobile:false});
    await call("Page.navigate",{url:"http://127.0.0.1:3020/system"});
    for(let n=0;n<100;n++){
      if(await evaluate('document.querySelector("[data-testid=system-v2]") && !document.body.innerText.includes("LOADING")'))break;
      if(n===99)throw Error("System never settled");
      await delay(100);
    }
    await delay(300);
    const layout=await evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth,headline:document.querySelector("h1").textContent,disclosure:!!document.querySelector("details"),open:document.querySelector("details").open})');
    if(layout.scroll>layout.width)throw Error("Page overflow: "+JSON.stringify(layout));
    if(layout.headline!=="System"||layout.open)throw Error("Unexpected default composition");
    const screenshot=await call("Page.captureScreenshot",{format:"png"});
    await writeFile(path.join(out,name+".png"),Buffer.from(screenshot.data,"base64"));
    console.log(name,JSON.stringify(layout));
  };
  await capture("system-desktop",1672);
  await evaluate('document.querySelector("summary").click()');
  if(!await evaluate('document.querySelector("details").open && document.body.innerText.includes("Persistent supervisor")'))throw Error("Disclosure failed");
  await evaluate('Array.from(document.querySelectorAll("button")).find(b=>b.textContent==="Refresh status").click()');
  await delay(600);
  const expanded=await call("Page.captureScreenshot",{format:"png"});
  await writeFile(path.join(out,"system-controls.png"),Buffer.from(expanded.data,"base64"));
  console.log("Disclosure + refresh PASS");
  await capture("system-mobile",390);
  await call("Page.navigate",{url:"http://127.0.0.1:3020/overview"});
  await delay(2000);
  if(!await evaluate('document.querySelector("main")!==null'))throw Error("Overview unavailable");
  const overview=await call("Page.captureScreenshot",{format:"png"});
  await writeFile(path.join(out,"overview-regression.png"),Buffer.from(overview.data,"base64"));
  if(errors.length)throw Error("Browser errors: "+errors.join("; "));
  console.log("Browser console/errors: 0");
} finally {
  ws?.close();child.kill();
  await new Promise(resolve=>child.exitCode!==null?resolve():child.once("exit",resolve));
  await rm(profile,{recursive:true,force:true}).catch(()=>{});
}
