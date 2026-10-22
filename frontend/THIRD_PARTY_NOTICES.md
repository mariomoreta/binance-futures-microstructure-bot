# Third-party notices — frontend

Este directorio conserva las licencias de las dependencias de terceros que se
distribuyen en el bundle del dashboard. Las versiones están fijadas en
`frontend/package.json` y `frontend/package-lock.json`.

## lightweight-charts 5.2.1

- Autor: TradingView, Inc.
- Licencia: Apache License 2.0
- Origen: https://github.com/tradingview/lightweight-charts
- Uso: gráfico financiero interactivo de `/paper-lab-live` (solo cliente).
- Texto completo: `lightweight-charts-5.2.1-Apache-2.0.txt`.
- El paquete npm incluye su propio `LICENSE`; se conserva aquí porque
  `node_modules/` no se versiona.

## fancy-canvas 2.1.0

- Autor (metadatos del paquete): smakarov@tradingview.com
- Licencia declarada: MIT
- Origen: dependencia transitiva de lightweight-charts.
- El paquete publicado **no incluye** archivo `LICENSE` ni línea de copyright;
  se declara esa ausencia como UNKNOWN y se reproduce el texto MIT estándar en
  `fancy-canvas-2.1.0-MIT.txt` sin inventar un titular.

No se incorporan dependencias de Phinvio ni código copiado de su aplicación.
