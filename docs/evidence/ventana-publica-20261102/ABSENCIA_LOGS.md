Archivos ausentes (declarados):
- stdout del servicio de mercado (market-stream-service): NO EXISTE. El orquestador captura stdout/stderr vía subprocess.PIPE pero no los escribe a disco. No hay archivo de log persistido.
- stderr del servicio de mercado (market-stream-service): NO EXISTE (mismo motivo).
- stdout del servicio de ingeniería (engineering-session-service): NO EXISTE. El orquestador captura stdout/stderr vía subprocess.PIPE pero no los escribe a disco. No hay archivo de log persistido.
- stderr del servicio de ingeniería (engineering-session-service): NO EXISTE (mismo motivo).
- Archivo de sesión (session_id): NO SE CREÓ. La sesión nunca se creó porque el fallo ocurrió en engineering_start_wait, antes de _create_session.
- Archivo de configuración (config_hash): NO SE CREÓ (mismo motivo).
- Ledger rows para run_id eng-run-public-20261102: 0 filas (consultado en data/market-cache/market_cache.db, tabla market_fetch_ledger).

Archivos presentes:
- docs/evidence/ventana-publica-20261102/evidence.json (evidencia del orquestador)
- docs/evidence/ventana-publica-20261102/run-id.json (run_id persistido por el servicio de ingeniería antes del fallo)
- docs/evidence/ventana-publica-20261102/LEDGER_CONSULTA.json (consulta del ledger)
