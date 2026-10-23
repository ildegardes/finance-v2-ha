"""Reproducible evidence runner; new evidence directory, synthetic tests only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
target = Path(sys.argv[1])
if not target.is_absolute() or target.exists():
    raise SystemExit('NEW_ABSOLUTE_EVIDENCE_DIRECTORY_REQUIRED')
target.mkdir()
node = Path(os.environ['FINANCE_NODE_EXECUTABLE'])
commands = [
    ('coverage', [sys.executable, '-B', 'tests/test_full_coverage.py']),
    ('mcp', [sys.executable, '-B', 'tests/release_mcp.py']),
    ('browser', [str(node), '--test', '--test-reporter=tap', 'tests/phase_a_ui.cjs']),
]
rows = []
for name, argv in commands:
    start = time.monotonic()
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
    (target / (name+'.stdout.txt')).write_text(result.stdout, encoding='utf-8')
    (target / (name+'.stderr.txt')).write_text(result.stderr, encoding='utf-8')
    rows.append({'group':name,'command':argv,'exit_code':result.returncode,'seconds':round(time.monotonic()-start,3)})
    print(json.dumps(rows[-1]),flush=True)
(target/'RESULTS.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest().upper() for p in target.iterdir() if p.is_file()}
(target/'EVIDENCE_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
raise SystemExit(0 if all(row['exit_code']==0 for row in rows) else 1)
