import {spawn} from "node:child_process";
import {mkdtemp, readFile, mkdir, writeFile, rm} from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const chrome = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const root = process.cwd();
const guardAudit=process.argv[2]==="system-51";
const integrationAudit=process.argv[2]==="system-52";
const watcherAudit=process.argv[2]==="system-50"||guardAudit||integrationAudit;
const round = process.env.QA_ROUND || "v2-56";
const base = process.env.QA_BASE_URL || "http://127.0.0.1:3020";
const out = path.join(root,"design/qa",round,process.argv[2]==="before"?"before":"after");
await mkdir(out, {recursive:true});
const profile = await mkdtemp(path.join(os.tmpdir(), "dashboard-v2-49-"));
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
  const waiting = new Map(), errors=[], unavailable=[];
  ws.addEventListener("message", e=>{
    const x=JSON.parse(e.data);
    if(x.id){const p=waiting.get(x.id);waiting.delete(x.id);x.error?p.reject(Error(JSON.stringify(x.error))):p.resolve(x.result);}
    if(x.method==="Runtime.exceptionThrown")errors.push(x.params.exceptionDetails.text);
    if(x.method==="Log.entryAdded"&&x.params.entry.level==="error"){const e=x.params.entry;const known=["live-movers","opportunities","price-series/BTCUSDT","price-series/ETHUSDT","price-series/SOLUSDT","price-series/ORCAUSDT"].some(p=>e.url===base+"/api/v1/"+p);if(e.text.includes("503")&&known)unavailable.push({url:e.url,text:e.text});else errors.push({url:e.url,text:e.text});}
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

  const routes=process.env.QA_ROUTES?process.env.QA_ROUTES.split(","):watcherAudit?["system","overview"]:["overview","movers","movers/verified","opportunities","opportunities/observations","opportunities/prospective","symbol/BTCUSDT","historical-research","market-archive","market-lab","system","backtest","paper-lab"];
  const results=[];
  for(const width of (process.env.QA_WIDTHS?process.env.QA_WIDTHS.split(",").map(Number):process.argv[2]==="full"?[1672]:[1672,1366,390])){
    await call("Emulation.setDeviceMetricsOverride",{width,height:941,deviceScaleFactor:1,mobile:false});
    for(const route of routes){
      await call("Page.navigate",{url:base+"/"+route});
      await delay(1800);
      if(watcherAudit&&route==="system"){for(let n=0;n<50;n++){if(!await evaluate('document.querySelector("[aria-label=\\\"Bot Control Center\\\"]")?.innerText.includes("LOADING")'))break;await delay(100);}}
      const x=await evaluate('({title:document.querySelector("h1")?.textContent,width:innerWidth,scroll:document.documentElement.scrollWidth,mains:document.querySelectorAll("main").length,loading:document.body.innerText.includes("LOADING"),active:[...document.querySelectorAll("#terminal-navigation a[aria-current=page]")].map(a=>a.getAttribute("href")),height:document.documentElement.scrollHeight,alerts:[...document.querySelectorAll("[role=alert]")].map(a=>a.textContent),scrollTables:[...document.querySelectorAll("table")].filter(t=>t.getBoundingClientRect().width>innerWidth).length})');
      if(!x.title && process.argv[2]!=="before")throw Error("Missing page title "+route);
      if(width===390 && await evaluate('!!document.querySelector("[aria-controls=terminal-navigation]")')){
        await evaluate('document.querySelector("[aria-controls=terminal-navigation]").click()');
        if(!await evaluate('document.querySelector("[aria-controls=terminal-navigation]").getAttribute("aria-expanded")==="true"'))throw Error("Mobile menu failed");
        if(route==="overview"){const menuShot=await call("Page.captureScreenshot",{format:"png"});await writeFile(path.join(out,"mobile-navigation.png"),Buffer.from(menuShot.data,"base64"));await call("Input.dispatchKeyEvent",{type:"keyDown",key:"Escape",code:"Escape",windowsVirtualKeyCode:27});await call("Input.dispatchKeyEvent",{type:"keyUp",key:"Escape",code:"Escape",windowsVirtualKeyCode:27});if(await evaluate('document.querySelector("[aria-controls=terminal-navigation]").getAttribute("aria-expanded")==="true"'))throw Error("Escape did not close menu");}else await evaluate('document.querySelector("[aria-controls=terminal-navigation]").click()');
      }
      if(process.argv[2]!=="before"&&route==="movers"&&width>=1366){
        const layout=await evaluate('(()=>{const t=document.querySelector("[data-testid=movers-table]");const w=[...document.querySelectorAll("section")].find(e=>e.getAttribute("aria-label")==="Market table and research rankings");const g=[...w.querySelectorAll("aside div")].find(e=>getComputedStyle(e).display==="grid");return {tableFits:t.parentElement.scrollWidth<=t.parentElement.clientWidth,rows:t.tBodies[0].rows.length,rankingColumns:getComputedStyle(g).gridTemplateColumns.split(" ").length}})()');
        if(!layout.tableFits||layout.rows!==8||layout.rankingColumns!==4)throw Error("Movers reference layout failed "+JSON.stringify(layout));
        x.visualLayout=layout;
      }
      if(process.env.QA_ROUND==="v2-58"&&process.argv[2]!=="before"&&route.startsWith("symbol/")){
        const token=await evaluate("(()=>{const s=document.querySelector('[aria-label=\"Market State Intelligence\"]');const flow=s.querySelector('[aria-label=\"Possible research states, not a mandatory progression\"]');const metrics=[...document.querySelectorAll('section')].find(e=>e.innerText.includes('Microstructure Snapshot'));const grid=[...metrics.children].find(e=>getComputedStyle(e).display==='grid');return {categories:flow.children.length,unknown:s.innerText.includes('UNKNOWN'),fixture:document.querySelector('[aria-label=\"Token dataset provenance\"]').innerText,metricColumns:getComputedStyle(grid).gridTemplateColumns.split(' ').length,metrics:grid.children.length}})()");
        if(token.categories!==5||!token.unknown||!token.fixture.includes("NOT LIVE")||token.metricColumns!==(width>1350?6:width>700?3:2))throw Error("Token visual/source contract failed "+JSON.stringify(token));
        if(route.includes("ORCA")&&!token.fixture.includes("NO SYMBOL FIXTURE"))throw Error("Unknown symbol inherited fixture");
        x.tokenLayout=token;
      }
      if(process.env.QA_ROUND==="v2-60"&&process.argv[2]!=="before"){
        if(width===390&&["historical-research","market-archive","market-lab","opportunities/prospective"].includes(route)){
          await call("Input.dispatchKeyEvent",{type:"keyDown",key:"Tab",code:"Tab",windowsVirtualKeyCode:9});
          await call("Input.dispatchKeyEvent",{type:"keyUp",key:"Tab",code:"Tab",windowsVirtualKeyCode:9});
          const keyboard=await evaluate("(()=>{const regions=[...document.querySelectorAll('[role=\"region\"][tabindex=\"0\"]')].filter(e=>e.scrollWidth>e.clientWidth);regions.forEach(e=>e.scrollLeft=0);const e=regions[0];if(e)e.focus();return {regions:regions.map(e=>e.getAttribute('aria-label')),focused:!!e&&document.activeElement===e,outline:e?getComputedStyle(e).outlineStyle:null}})()");
          if(!keyboard.focused||keyboard.outline!=="solid")throw Error("Record table focus failed "+route+JSON.stringify(keyboard));
          await call("Input.dispatchKeyEvent",{type:"keyDown",key:"ArrowRight",code:"ArrowRight",windowsVirtualKeyCode:39});
          await call("Input.dispatchKeyEvent",{type:"keyUp",key:"ArrowRight",code:"ArrowRight",windowsVirtualKeyCode:39});await delay(200);
          const scroll=await evaluate("(()=>{const e=document.activeElement;return {moved:e.scrollLeft>0,left:e.scrollLeft}})()");if(!scroll.moved)throw Error("Keyboard table scroll failed "+route);
          x.keyboardTable={...keyboard,...scroll};
          await evaluate('document.activeElement.scrollLeft=0;document.activeElement.blur();window.scrollTo(0,0)');await delay(80);
        }
        if(["backtest","paper-lab"].includes(route)){
          const future=await evaluate("(()=>{const root=document.querySelector('[data-kind]');const unavailable=root.querySelector('[aria-label=\"Unavailable measurements\"]');return {measurements:unavailable.children.length,allUnavailable:[...unavailable.children].every(e=>e.innerText.includes('NOT AVAILABLE')),enabledControls:[...root.querySelectorAll('button,input,textarea,select')].filter(e=>!e.matches(':disabled')).length}})()");
          if(!future.allUnavailable||future.enabledControls!==0||future.measurements!==(route==="backtest"?6:4))throw Error("Future state contract failed "+JSON.stringify(future));x.unavailableWorkspace=future;
        }
        if(route==="system"){
          const system=await evaluate("({recorded:document.body.innerText.includes('Recorded process'),startDisabled:[...document.querySelectorAll('button')].find(e=>e.textContent.includes('Start monitor'))?.disabled})");if(!system.recorded||!system.startDisabled)throw Error("System source/control contract failed "+JSON.stringify(system));x.systemSemantics=system;
        }
      }
      const shot=await call("Page.captureScreenshot",{format:"png"});
      const name=route.replaceAll("/","-")+"-"+width;
      await writeFile(path.join(out,name+".png"),Buffer.from(shot.data,"base64"));
      if(process.argv[2]==="full"||process.env.QA_FULL==="1"){const dimensions=await call("Page.getLayoutMetrics");const bounds=dimensions.cssContentSize;const fullShot=await call("Page.captureScreenshot",{format:"png",captureBeyondViewport:true,clip:{x:0,y:0,width:bounds.width,height:bounds.height,scale:1}});await writeFile(path.join(out,route.replaceAll("/","-")+"-"+width+"-full.png"),Buffer.from(fullShot.data,"base64"));}
      results.push({route,...x});console.log(name,JSON.stringify(x));
      if(route==="system"&&(width===1672||watcherAudit)){
        await evaluate('document.querySelector("summary").click()');
        const dimensions=await call("Page.getLayoutMetrics");const b=dimensions.cssContentSize;
        const s=await call("Page.captureScreenshot",{format:"png",captureBeyondViewport:true,clip:{x:0,y:0,width:b.width,height:b.height,scale:1}});
        await writeFile(path.join(out,watcherAudit?"system-expanded-"+width+".png":"system-expanded.png"),Buffer.from(s.data,"base64"));
        if(watcherAudit){
          const ui=await evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth,sentinel:!!document.querySelector("[aria-label=\\\"sentinel evidence\\\"]"),startDisabled:[...document.querySelectorAll("button")].find(b=>b.textContent.includes("Start monitor"))?.disabled,alerts:[...document.querySelectorAll("[role=alert]")].map(a=>a.textContent)})');
          if(ui.scroll>ui.width||!ui.sentinel||!ui.startDisabled||(guardAudit ? ui.alerts.length!==1||!ui.alerts[0].includes("Runtime observation is paused") : ui.alerts.length>0))throw Error("Watcher UI check failed "+JSON.stringify(ui));
          results.at(-1).watcherUI=ui;
          const dto=await evaluate('fetch("/api/v1/runtime",{cache:"no-store"}).then(r=>r.json())');
          if(integrationAudit&&!await evaluate('document.body.innerText.includes("Recorded process") && document.body.innerText.includes("current process liveness is not reported")'))throw Error("Recorded process semantics missing");
          if(!dto.sentinel||!dto.supervisor||!dto.observed_at||(guardAudit ? dto.error!=="READ_ONLY_STATUS_REQUIRED"||dto.state!=="UNKNOWN" : !!dto.error))throw Error("Watcher API evidence unavailable");
          await writeFile(path.join(out,"runtime-"+width+".json"),JSON.stringify(dto,null,2));
        }
      }
    }
  }
  await writeFile(path.join(out,process.env.QA_RESULT_NAME || (process.argv[2]==="full"?"full-results.json":"results.json")),JSON.stringify({results,errors,unavailable},null,2));
  console.log("Route captures",results.length,"browser errors",JSON.stringify(errors),"unavailable sources",unavailable.length);
  if(process.argv[2]!=="before" && (errors.length || results.some(x=>x.scroll>x.width||x.mains!==1||x.active.length!==1)))throw Error("Route validation failed; inspect results.json");

} finally {
  ws?.close();child.kill();
  await new Promise(resolve=>child.exitCode!==null?resolve():child.once("exit",resolve));
  await rm(profile,{recursive:true,force:true}).catch(()=>{});
}