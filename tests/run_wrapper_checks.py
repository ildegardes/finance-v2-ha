"""Execute the previously qualified lifecycle harness with explicit disposable paths."""
import hashlib
import json
from pathlib import Path
import runpy
import sys

ROOT=Path(__file__).resolve().parents[1]
harness,target=(Path(p).resolve() for p in sys.argv[1:3])
if target.exists() or not harness.is_file():
    raise SystemExit('EXISTING_SYNTHETIC_HARNESS_AND_NEW_TARGET_REQUIRED')
namespace=runpy.run_path(str(harness),run_name='qualified_lifecycle_harness')
main=namespace['main']
values=main.__globals__
values['ROOT']=target.parent
values['WRAPPER']=ROOT/'finance-v17'/'run.sh'
values['RUN']=target
status=main()
(target/'HARNESS_IDENTITY.json').write_text(json.dumps({'source_sha256':hashlib.sha256(harness.read_bytes()).hexdigest().upper(),
    'wrapper_sha256':hashlib.sha256(values['WRAPPER'].read_bytes()).hexdigest().upper(),
    'source_harness_changed':False,'path_overrides_only':True},indent=2)+'\n',encoding='utf-8')
raise SystemExit(status)
