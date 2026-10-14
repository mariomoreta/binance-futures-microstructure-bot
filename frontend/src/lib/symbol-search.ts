export function searchQuery(raw:string){const query=raw.trim().toUpperCase();return {query,valid:query.length<=32&&/^[A-Z0-9]*$/.test(query)}}
export function searchSymbols(symbols:string[],query:string,limit=50){
 const unique=[...new Set(symbols)].filter(s=>/^[A-Z0-9]{2,32}$/.test(s)&&s.includes(query));
 unique.sort((a,b)=>Number(b===query)-Number(a===query)||Number(b.startsWith(query))-Number(a.startsWith(query))||a.localeCompare(b));
 return {symbols:unique.slice(0,limit),truncated:unique.length>limit};
}
