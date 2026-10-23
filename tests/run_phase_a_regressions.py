"""Re-run unchanged historical JS assertions, without importing DB fixtures."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

TARGET = Path(sys.argv[1])
if not TARGET.is_absolute() or TARGET.exists():
    raise RuntimeError('NEW_ABSOLUTE_EVIDENCE_DIRECTORY_REQUIRED')
TARGET.mkdir()
TESTS = Path(r'G:\Codex\Finance_V2\tests')
PRODUCT = Path(__file__).resolve().parents[1] / 'finance-v17'
NODE = r'C:\Users\ilde\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
selections = [
    ('test_ui_v17_completion.py','test_state_actions_svg_and_controller_refresh_payloads',True),
    ('test_ui_v17_corrective.py','test_human_audit_error_and_interface_contracts',True),
    ('test_recurrence_ui_v17.py','test_indicator_computed_layout_and_accessibility_in_browser',False),
]
rows = []
for filename, method, module in selections:
    original = (TESTS / filename).read_bytes()
    tree = ast.parse(original.decode('utf-8-sig'))
    function = next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==method)
    assign = next(n for n in ast.walk(function) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='source' for t in n.targets))
    source = ast.literal_eval(assign.value)
    command = [NODE] + (['--input-type=module'] if module else ['-'])
    result = subprocess.run(command,input=source,text=True,encoding='utf-8',capture_output=True,cwd=PRODUCT,timeout=45,env=os.environ.copy())
    (TARGET / (method+'.stdout.txt')).write_text(result.stdout,encoding='utf-8')
    (TARGET / (method+'.stderr.txt')).write_text(result.stderr,encoding='utf-8')
    rows.append(dict(test=method,status='PASS' if result.returncode==0 else 'FAIL',exit_code=result.returncode,
                     original_sha256=hashlib.sha256(original).hexdigest().upper(),executed_js_sha256=hashlib.sha256(source.encode()).hexdigest().upper(),assertions_changed=False))
    if result.returncode:
        break
report = dict(pass_count=sum(r['status']=='PASS' for r in rows),fail_count=sum(r['status']=='FAIL' for r in rows),tests=rows,database_access=False,migrations_executed=False)
(TARGET / 'RESULTS.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['pass_count']==3 and not report['fail_count'] else 1)
