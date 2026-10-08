"use client";
import type {MoversFiltersState} from "@/lib/movers-domain";
import s from "./MoversQuickFilters.module.css";
type Tab={label:string;direction?:MoversFiltersState["direction"];coverage?:MoversFiltersState["coverage"];interest?:MoversFiltersState["interest"]};
export const tabs:Tab[]=[{label:"All"},{label:"Hot",coverage:"HOT"},{label:"Gainers",direction:"GAINERS"},{label:"Losers",direction:"LOSERS"},{label:"Positive Flow",interest:"ACCELERATING_UP"},{label:"Negative Flow",interest:"ACCELERATING_DOWN"},{label:"Volume",interest:"HIGH_VOLUME"},{label:"Exhaustion research",interest:"EXTREME_GAINERS"}];
export function MoversQuickFilters({active,onSelect}:{active:string;onSelect:(tab:Tab)=>void}){return <nav className={s.tabs} aria-label="Quick mover filters">{tabs.map(tab=><button key={tab.label} type="button" onClick={()=>onSelect(tab)} className={active===tab.label?s.active:s.tab} aria-pressed={active===tab.label}>{tab.label}</button>)}</nav>}
