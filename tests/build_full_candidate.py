"""Build exact local candidate for both declared architectures, without publishing."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
target = Path(sys.argv[1]).resolve()
if target.exists():
    raise SystemExit('NEW_EVIDENCE_DIRECTORY_REQUIRED')
target.mkdir()
rows = []
for arch in ('amd64', 'arm64'):
    tag = 'finance-v17-full-coverage:0.1.23-open-finance.1-' + arch
    argv = ['docker', 'build', '--platform', 'linux/' + arch, '--tag', tag,
            '--label', 'finance.validation=full-coverage-20261023', '-f', 'finance-v17/Dockerfile', 'finance-v17']
    started = time.monotonic()
    result = subprocess.run(argv, cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600)
    (target / (arch+'.stdout.log')).write_text(result.stdout, encoding='utf-8')
    (target / (arch+'.stderr.log')).write_text(result.stderr, encoding='utf-8')
    row = {'architecture': arch, 'command': argv, 'exit_code': result.returncode, 'seconds': round(time.monotonic()-started,3)}
    rows.append(row)
    if result.returncode == 0:
        inspected = subprocess.run(['docker','image','inspect',tag,'--format','{{json .}}'],capture_output=True,text=True,encoding='utf-8',timeout=15,check=True)
        image = json.loads(inspected.stdout)
        row.update(image_id=image['Id'],image_architecture=image['Architecture'],version=image['Config']['Labels']['io.hass.version'])
    (target / 'RESULTS.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(row),flush=True)
    if result.returncode:
        break
(target/'EVIDENCE_MANIFEST.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest().upper() for p in target.iterdir() if p.is_file()},indent=2)+'\n',encoding='utf-8')
raise SystemExit(0 if len(rows)==2 and all(r['exit_code']==0 and r['architecture']==r['image_architecture'] for r in rows) else 1)
