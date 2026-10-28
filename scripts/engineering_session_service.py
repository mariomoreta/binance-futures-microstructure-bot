"""CLI del servicio de sesiones de ingeniería (solo loopback).

Arranque/parada explícitos; no se lanza solo porque alguien abra una página.

Uso (desde la raíz del repo):

  python scripts/engineering_session_service.py --port 8797
  python scripts/engineering_session_service.py --port 8797 --sessions-dir C:\\...aislado...
  python scripts/engineering_session_service.py --port 8797 --cadence-ms 200
  python scripts/engineering_session_service.py --port 8797 --stop

Sin sesión abierta el servicio no conduce nada: el avance solo ocurre cuando
una sesión recibe ``control start`` y el transporte local emite eventos.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from microstructure_probe.engineering_session_service import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
