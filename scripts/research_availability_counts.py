"""Conteo reproducible de disponibilidad publicada (`as_of_ms`) por fuente.

Responde, por separado para libro y flujo: cuántas filas tienen `as_of_ms`
NULL, cuántas lo tienen presente en/antes del cierre del bucket y cuántas lo
tienen posterior al cierre. NULL = procedencia desconocida: no se rellena ni se
sustituye por `last_event_ms`.

Solo lectura (`mode=ro`) sobre `data/historical/historical.db`. Sin red.

Salida: docs/evidence/research/universe_liquidity_v1/disponibilidad_as_of.json
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "data" / "historical" / "historical.db"
OUT = (
    ROOT / "docs" / "evidence" / "research" / "universe_liquidity_v1"
    / "disponibilidad_as_of.json"
)

SQL = """SELECT
  COUNT(*) AS total,
  SUM(CASE WHEN as_of_ms IS NULL THEN 1 ELSE 0 END) AS as_of_null,
  SUM(CASE WHEN as_of_ms IS NOT NULL AND as_of_ms <= bucket_end
           THEN 1 ELSE 0 END) AS as_of_presente_en_o_antes_del_bucket,
  SUM(CASE WHEN as_of_ms IS NOT NULL AND as_of_ms > bucket_end
           THEN 1 ELSE 0 END) AS as_of_posterior_al_bucket,
  MIN(as_of_ms) AS as_of_min,
  MAX(as_of_ms) AS as_of_max
FROM {tabla}"""

SQL_POR_SIMBOLO = """SELECT
  symbol,
  COUNT(*) AS total,
  SUM(CASE WHEN as_of_ms IS NULL THEN 1 ELSE 0 END) AS as_of_null,
  SUM(CASE WHEN as_of_ms IS NOT NULL AND as_of_ms <= bucket_end
           THEN 1 ELSE 0 END) AS as_of_presente_en_o_antes_del_bucket,
  SUM(CASE WHEN as_of_ms IS NOT NULL AND as_of_ms > bucket_end
           THEN 1 ELSE 0 END) AS as_of_posterior_al_bucket
FROM {tabla}
GROUP BY symbol
ORDER BY symbol"""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    sha_antes = _sha256(HIST)
    con = sqlite3.connect(f"file:{HIST.as_posix()}?mode=ro", uri=True)
    try:
        resultado = {}
        for tabla in ("research_book_1m", "research_flow_1m"):
            cur = con.execute(SQL.format(tabla=tabla))
            cols = [d[0] for d in cur.description]
            fila = dict(zip(cols, cur.fetchone()))
            por_simbolo = [
                dict(zip(cols, r))
                for r in con.execute(SQL_POR_SIMBOLO.format(tabla=tabla))
            ]
            resultado[tabla] = {"total": fila, "por_simbolo": por_simbolo}
    finally:
        con.close()
    sha_despues = _sha256(HIST)

    artefacto = {
        "fuente": "data/historical/historical.db",
        "modo": "read-only (mode=ro)",
        "db_sha256_antes": sha_antes,
        "db_sha256_despues": sha_despues,
        "db_sin_cambios": sha_antes == sha_despues,
        "semantica": {
            "as_of_ms": "marca de tiempo de persistencia en el flush; no prueba "
                        "por sí sola cuándo estuvo disponible el dato",
            "as_of_null": "procedencia desconocida (filas previas al linkage v3, "
                          "nunca rellenadas)",
            "as_of_presente_en_o_antes_del_bucket": "as_of_ms <= bucket_end",
            "as_of_posterior_al_bucket": "as_of_ms > bucket_end",
        },
        "sql": {
            "research_book_1m": SQL.format(tabla="research_book_1m"),
            "research_flow_1m": SQL.format(tabla="research_flow_1m"),
        },
        "resultados": resultado,
    }
    OUT.write_text(json.dumps(artefacto, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"DB sin cambios: {artefacto['db_sin_cambios']}")
    for tabla, datos in resultado.items():
        t = datos["total"]
        print(
            f"{tabla}: total={t['total']} null={t['as_of_null']} "
            f"presente={t['as_of_presente_en_o_antes_del_bucket']} "
            f"posterior={t['as_of_posterior_al_bucket']}"
        )
    print(f"Escrito: {OUT}")
    return 0 if artefacto["db_sin_cambios"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
