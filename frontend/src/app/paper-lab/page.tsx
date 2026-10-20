import {Suspense} from "react";
import PaperLabSource from "@/components/paper-lab/PaperLabSource";
export default function PaperLabPage(){
  // useSearchParams exige un limite de Suspense para el prerender; el replay
  // fijo versionado no depende de parametros, pero el enlace de Backtest si.
  return <Suspense fallback={<div/>}><PaperLabSource/></Suspense>;
}
