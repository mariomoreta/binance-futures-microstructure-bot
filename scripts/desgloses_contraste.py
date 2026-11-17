# -*- coding: utf-8 -*-
"""Desgloses del contraste flujo/profundidad: por rol, direccion, ciclo y
concentracion de simbolos. Reutiliza contraste_filas.jsonl generado por
contraste_flujo_profundidad.py. No modifica fuentes.
"""
import json
import io
from collections import Counter, defaultdict
from pathlib import Path

DERIVED = Path(
    r"C:\proyectos\binance-futures-data\exp-v2-ventana-4-20261116a-contraste-flujo-profundidad-20261116"
)
filas = []
with io.open(DERIVED / "contraste_filas.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            filas.append(json.loads(line))

print(f"total filas: {len(filas)}")

def grupo_ratio(f):
    ra = f.get("ratio_alineado")
    if ra is None:
        return "insuficiente"
    if ra > 0:
        return "flujo_a_favor"
    if ra < 0:
        return "flujo_contrario"
    return "insuficiente"

def resumen_grupo(sub):
    n = len(sub)
    cont = sum(1 for f in sub if f.get("resultado") == "continuacion")
    rev = sum(1 for f in sub if f.get("resultado") == "reversion")
    neu = sum(1 for f in sub if f.get("resultado") == "neutral")
    rets = [f["retorno_alineado"] for f in sub if f.get("retorno_alineado") is not None]
    ordenados = sorted(rets)
    media = sum(rets)/len(rets) if rets else None
    mediana = ordenados[len(ordenados)//2] if ordenados else None
    return {
        "n": n,
        "continuacion": cont,
        "reversion": rev,
        "neutral": neu,
        "prov_continuacion": round(cont/n, 6) if n else None,
        "retorno_alineado_media": round(media, 8) if media is not None else None,
        "retorno_alineado_mediana": round(mediana, 8) if mediana is not None else None,
    }

print("\n=== POR ROL ===")
por_rol = defaultdict(list)
for f in filas:
    if f.get("reconstruido"):
        por_rol[f.get("role")].append(f)
for rol, sub in sorted(por_rol.items()):
    print(f"{rol}: {resumen_grupo(sub)}")

print("\n=== POR DIRECCION (side_selector / signo move_24h) ===")
por_dir = defaultdict(list)
for f in filas:
    if f.get("reconstruido"):
        mv = f.get("move_24h_pct")
        dir_ = "LONG" if (mv or 0) > 0 else "SHORT"
        por_dir[dir_].append(f)
for d, sub in sorted(por_dir.items()):
    print(f"{d}: {resumen_grupo(sub)}")

print("\n=== POR CICLO (grupo_ratio x continuacion) ===")
por_ciclo = defaultdict(lambda: defaultdict(list))
for f in filas:
    if f.get("reconstruido"):
        por_ciclo[f.get("ciclo")][grupo_ratio(f)].append(f)
for c in sorted(por_ciclo):
    fila = []
    for g in ("flujo_a_favor", "flujo_contrario"):
        sub = por_ciclo[c].get(g, [])
        r = resumen_grupo(sub)
        fila.append(f"{g}: n={r['n']} cont={r['prov_continuacion']}")
    print(f"ciclo{c:02d}: " + " | ".join(fila))

print("\n=== CONCENTRACION DE SIMBOLOS (repeticiones) ===")
sym = Counter(f["symbol"] for f in filas if f.get("reconstruido"))
rep = {s: c for s, c in sym.items() if c >= 2}
print(f"simbolos unicos: {len(sym)}, con repeticion (>=2): {len(rep)}")
print("top repeticiones:", sorted(rep.items(), key=lambda x: -x[1])[:15])
# distribucion de continuacion por simbolo repetido
print("\ncontinuacion por simbolo repetido (n, prov_cont):")
for s, c in sorted(rep.items(), key=lambda x: -x[1])[:15]:
    sub = [f for f in filas if f.get("reconstruido") and f["symbol"] == s]
    cont = sum(1 for f in sub if f.get("resultado") == "continuacion")
    print(f"  {s}: n={c}, continuacion={cont} ({round(cont/c,4) if c else None})")

print("\n=== MAPA CAMPO -> FUENTE -> UNIDAD -> DISPONIBILIDAD ===")
mapa = [
    ("move_24h_pct", "observaciones.seleccion", "puntos porcentuales", "siempre (en aptas)"),
    ("buy_notional", "observaciones.flujo", "USDT (notional compras agresoras, 60s)", "siempre (en aptas)"),
    ("sell_notional", "observaciones.flujo", "USDT (notional ventas agresoras, 60s)", "siempre (en aptas)"),
    ("bid_notional_top20", "observaciones.libro", "USDT (notional pujas top20)", "siempre (en aptas)"),
    ("ask_notional_top20", "observaciones.libro", "USDT (notional ofertas top20)", "siempre (en aptas)"),
    ("decision_ms", "observaciones", "ms epoch UTC (reloj piloto)", "siempre"),
    ("ref_close (precio inicial)", "consultas_klines (close ultima vela <= T)", "precio", "siempre"),
    ("precio_final 60m", "consultas_klines (close ultima vela <= T+60m)", "precio", "siempre (161/161 resoluble)"),
    ("window_ms flujo", "observaciones.flujo.window_ms", "ms (60000 = 60s)", "siempre"),
    ("disponibilidad (flujo_ms/libro_ms/max_ms)", "observaciones.disponibilidad", "ms", "siempre"),
    ("cobertura", "observaciones.cobertura", "booleano", "siempre"),
    ("role", "observaciones.role", "candidate/comparator", "siempre"),
    ("symbol", "observaciones.symbol", "ticker", "siempre"),
]
for campo, fuente, unidad, disp in mapa:
    print(f"  {campo:45} | {fuente:45} | {unidad:40} | {disp}")
print("\nTodos los datos son del exchange público (WS/REST USD-M), no on-chain.")
print("No se inventaron campos, cobertura ni disponibilidad temporal.")
