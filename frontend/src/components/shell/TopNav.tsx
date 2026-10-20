"use client";
import Link from "next/link";
import {SymbolSearch} from "./SymbolSearch";
import {usePathname} from "next/navigation";
import {useEffect,useState} from "react";
const MAIN=[
 {href:"/overview",label:"Overview",icon:"◉"},
 {href:"/movers",label:"Movers",icon:"▦"},
 {href:"/search",label:"Search",icon:"⌕"},
 {href:"/opportunities",label:"Opportunities",icon:"◈"},
 {href:"/system",label:"System",icon:"⚙"},
];
const RESEARCH=[
 {href:"/historical-research",label:"Evidence",icon:"▤"},
 {href:"/market-archive",label:"Market Archive",icon:"▥"},
 {href:"/market-lab",label:"Market Lab",icon:"⌁"},
];
const FUTURE=[{href:"/backtest",label:"Backtest",icon:"◐"},{href:"/paper-lab",label:"Paper Lab",icon:"◑"}];
export function TopNav(){
 const pathname=usePathname();const [open,setOpen]=useState(false);
 useEffect(()=>{if(!open)return;const close=(event:KeyboardEvent)=>{if(event.key==="Escape"){setOpen(false);document.querySelector<HTMLButtonElement>(".v2-menu-button")?.focus()}};document.addEventListener("keydown",close);return()=>document.removeEventListener("keydown",close)},[open]);
 const current=(href:string)=>pathname===href||pathname.startsWith(href+"/")||(href==="/movers"&&pathname.startsWith("/symbol/"));
 const links=(items:typeof MAIN)=>items.map(item=><Link key={item.href} href={item.href} aria-current={current(item.href)?"page":undefined} onClick={()=>setOpen(false)}><span className="v2-nav-icon" aria-hidden="true">{item.icon}</span>{item.label}</Link>);
 return <><header className="v2-terminal-header"><button className="v2-menu-button" type="button" aria-label={open?"Close navigation":"Open navigation"} aria-controls="terminal-navigation" aria-expanded={open} onClick={()=>setOpen(!open)} onKeyDown={e=>{if(e.key==="Escape")setOpen(false)}}>☰</button><Link className="v2-brand" href="/overview" onClick={()=>setOpen(false)}>◆ BINANCE FUTURES</Link><span className="v2-header-context">Dashboard V2 / Market intelligence</span><SymbolSearch/><span className="v2-header-mode">RESEARCH ONLY</span></header>
 <nav id="terminal-navigation" className="v2-nav" aria-label="Primary navigation" data-open={open} onKeyDown={e=>{if(e.key==="Escape"){setOpen(false);document.querySelector<HTMLButtonElement>(".v2-menu-button")?.focus()}}}><div className="v2-nav-group">Terminal</div>{links(MAIN)}<div className="v2-nav-group">Research archive</div>{links(RESEARCH)}<div className="v2-nav-group">Future workspace</div>{links(FUTURE)}<div className="v2-nav-footer"><strong>OBSERVE & RESEARCH</strong>Each panel labels its source.<br/>No execution enabled.</div></nav></>;
}
