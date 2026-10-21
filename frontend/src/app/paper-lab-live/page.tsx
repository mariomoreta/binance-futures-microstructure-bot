import {Suspense} from "react";
import PaperLabLive from "@/components/paper-lab-live/PaperLabLive";

// Pagina del Paper Lab en caliente (ingenieria): simulacion paper sobre
// fixtures, sin Binance en vivo, sin ordenes reales. Desktop-first.
export default function PaperLabLivePage(){
  return <Suspense fallback={<div/>}><PaperLabLive/></Suspense>;
}
