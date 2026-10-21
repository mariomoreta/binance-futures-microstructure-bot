import {Suspense} from "react";
import PaperLabLive from "@/components/paper-lab-live/PaperLabLive";

// Pagina del Paper Lab de ingeniería (demostración sobre fixtures).
// Backend como fuente de verdad: src/microstructure_probe/paper_lab_engine.py.
// Diferencia del replay historico (/paper-lab) y del futuro paper prospectivo.
// No hay Binance en vivo, no hay ordenes reales, no hay capital real.
export default function PaperLabLivePage(){
  return <Suspense fallback={<div/>}><PaperLabLive/></Suspense>;
}
