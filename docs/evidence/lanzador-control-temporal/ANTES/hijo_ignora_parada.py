import signal, sys, time
# Hijo local: ignora SIGINT y SIGTERM; solo termina por su cuenta
try:
    signal.signal(signal.SIGINT, signal.SIG_IGN)
except Exception:
    pass
try:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
except Exception:
    pass
print("hijo: trabajando 6 s (ignora parada)", flush=True)
time.sleep(6)
print("hijo: terminado por su cuenta", flush=True)
