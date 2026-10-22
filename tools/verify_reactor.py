"""Measure real verification work. No fixed latency or security-count claims."""
import ast
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

root=Path(__file__).resolve().parents[1]
started=time.perf_counter()
modules=sorted((root/'reactor').glob('*.py'))
for path in modules:
    ast.parse(path.read_text(),filename=str(path))
parse_ms=(time.perf_counter()-started)*1000
result=subprocess.run([sys.executable,'-m','pytest','-q'],cwd=root,capture_output=True,text=True)
print(result.stdout)
if result.stderr:print(result.stderr,file=sys.stderr)
print(json.dumps({'reactor_python_modules':len(modules),'syntax_parse_ms':round(parse_ms,3),
    'full_test_run_ms':round((time.perf_counter()-started)*1000,3),'tests_exit_code':result.returncode,
    'source_digest':hashlib.sha256(b''.join(p.read_bytes() for p in modules)).hexdigest(),
    'scope':'Local syntax plus actual full regression suite. Does not replace CI, security review or market validation.'},indent=2))
sys.exit(result.returncode)
