"""Exercise the exact V2 pure-status bridge against a temporary registry."""
import hashlib,json,os,re,subprocess,sys,tempfile
from pathlib import Path
from microstructure_probe import control
root=Path(__file__).resolve().parents[1]
source=(root/"frontend/src/lib/runtime-control.ts").read_text(encoding="utf-8")
code=json.loads(re.search(r'const pureStatusCode=("(?:[^"\\]|\\.)*");',source).group(1))+"print(json.dumps(s))"
canonical=control.registry_path()
canonical_before=hashlib.sha256(canonical.read_bytes()).hexdigest() if canonical.exists() else None
with tempfile.TemporaryDirectory(prefix="v2-readonly-") as folder:
 path=Path(folder)/"runtime.json"
 path.write_text(json.dumps({"state":"RUNNING","pid":424243,"create_time":"INVALID"}))
 before=path.read_bytes()
 env={**os.environ,"MICROPROBE_RUNTIME_FILE":str(path)}
 result=subprocess.run([sys.executable,"-c",code],env=env,capture_output=True,text=True,check=True)
 value=json.loads(result.stdout)
 assert value=={"error":"READ_ONLY_STATUS_REQUIRED"},value
 assert path.read_bytes()==before,"Unexpected bridge registry write"
canonical_after=hashlib.sha256(canonical.read_bytes()).hexdigest() if canonical.exists() else None
assert canonical_after==canonical_before,"Canonical registry changed"
print(json.dumps({"response":value,"temporary_registry_unchanged":True,"canonical_registry_sha256_before":canonical_before,"canonical_registry_sha256_after":canonical_after},indent=2))
