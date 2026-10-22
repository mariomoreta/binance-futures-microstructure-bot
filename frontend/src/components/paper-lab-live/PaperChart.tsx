"use client";
// Fachada de compatibilidad: el componente se generalizó a
// `@/components/chart/PriceChart` para reutilizarlo con el contrato
// `market-chart/v1` (explorador de mercado) sin duplicar el cableado de
// Lightweight Charts. Paper Lab conserva el nombre y los testids
// (`paper-chart*`) porque `PriceChart` deriva la identidad del contrato.
export {PriceChart as PaperChart} from "@/components/chart/PriceChart";
