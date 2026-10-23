"""Local-only legacy-suite preparation. Never publishes private historical test source."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parents[1]
historical, target = (Path(p).resolve() for p in sys.argv[1:3])
if target.exists() or target == root or not (historical/'tests'/'support.py').is_file():
    raise SystemExit('EXISTING_SYNTHETIC_SOURCE_AND_NEW_TARGET_REQUIRED')
target.mkdir()
source = target/'source'
(source/'tests').mkdir(parents=True)
adaptations = []
pins = {}
approved = {'test_open_finance_sync.py','test_open_finance_migration.py','test_oauth_stage1.py','test_oauth_stage2.py','test_oauth_refresh.py','test_open_finance_unicode_http.py'}


class Schema10(ast.NodeTransformer):
    def visit_FunctionDef(self, node):
        if self.filename == 'test_open_finance_unicode_http.py' and node.name == 'test_packaging_contains_all_unicode_assets_and_exact_mirrors':
            # The public add-on has ONE source tree, not the private monorepo's
            # two mirrors or a Python wheel. Preserve all byte/hash checks and
            # check the actual Docker COPY/distribution contract instead.
            replacement = '''def check(self):
    root=Path(__file__).resolve().parents[1]
    assets=('unicode13_f06.py','unicode13_primitives.json','UNICODE13_NOTICES.md','PYTHON_REFERENCE_LICENSE.txt','unicode13_manifest.json','UNICODE_DATA_LICENSE_2020.txt','UNICODE_LICENSE_V3.txt')
    for name in assets:
        self.assertEqual((root/'src/finance_v2'/name).read_bytes(),(root/'finance-v17/src/finance_v2'/name).read_bytes())
    manifest=json.loads((root/'src/finance_v2/unicode13_manifest.json').read_bytes())
    for name,pin in manifest['artifacts'].items():
        raw=(root/'src/finance_v2'/name).read_bytes()
        self.assertEqual((len(raw),sha256(raw).hexdigest().upper()),(pin['bytes'],pin['sha256']))
    self.assertIn('COPY --chown=financev2:financev2 src ./src',(root/'finance-v17/Dockerfile').read_text())
    self.assertTrue((root/'finance-v17/src/finance_v2/pluggy_coverage_contracts.json').is_file())
'''
            node.body = ast.parse(replacement).body[0].body
            adaptations.append({'file':self.filename,'line':node.lineno,'method':node.name,'change':'Public single-add-on layout replaces private mirrors/wheel contract; seven Unicode asset equalities, manifest lengths/SHA256 and Docker COPY retained.'})
            return node
        return self.generic_visit(node)

    def visit_Call(self, node):
        self.generic_visit(node)
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'assertEqual' and len(node.args) >= 2:
            subject = ast.unparse(node.args[0])
            expected = node.args[1]
            if 'migrate(' in subject and isinstance(expected, ast.List):
                values = [child.value if isinstance(child, ast.Constant) else None for child in expected.elts]
                if values in ([9], [7,8,9], [8,9]):
                    expected.elts.append(ast.Constant(value=10))
                    adaptations.append({'file': self.filename, 'line': node.lineno, 'subject': subject, 'before': values, 'after': values+[10]})
            elif 'PRAGMA user_version' in subject and isinstance(expected, ast.Constant) and expected.value == 9:
                expected.value = 10
                adaptations.append({'file': self.filename, 'line': node.lineno, 'subject': subject, 'before': 9, 'after': 10})
            elif self.filename == 'test_oauth_refresh.py' and subject == '[r[0] for r in history]' and ast.unparse(expected) == 'list(range(1, 10))':
                node.args[1] = ast.parse('list(range(1, 11))', mode='eval').body
                adaptations.append({'file': self.filename, 'line': node.lineno, 'subject': subject, 'before': 'list(range(1, 10))', 'after': 'list(range(1, 11))'})
            elif self.filename == 'test_open_finance_sync.py' and subject == 'set(paths)' and isinstance(expected,ast.SetComp):
                seq=expected.generators[0].iter
                before=[v.value for v in seq.elts]
                if before != ['connections','sync','sync-all','sync-runs','sync-run','transactions','catalogs']:
                    raise RuntimeError('UNEXPECTED_LEGACY_ROUTE_EXPECTATION')
                seq.elts.extend(ast.Constant(value=p) for p in ('resources','coverage','coverage-sync'))
                adaptations.append({'file':self.filename,'line':node.lineno,'subject':subject,'before':before,'after':before+['resources','coverage','coverage-sync']})
        return node


for original in (historical/'tests').glob('*.py'):
    raw = original.read_bytes()
    pins[original.name] = {'original_sha256': hashlib.sha256(raw).hexdigest().upper()}
    if original.name in approved:
        transformer = Schema10()
        transformer.filename = original.name
        raw = (ast.unparse(ast.fix_missing_locations(transformer.visit(ast.parse(raw.decode('utf-8-sig')))))+'\n').encode()
    (source/'tests'/original.name).write_bytes(raw)
    pins[original.name]['executed_sha256'] = hashlib.sha256(raw).hexdigest().upper()
shutil.copytree(root/'finance-v17'/'src',source/'src',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copytree(root/'finance-v17'/'migrations',source/'migrations')
shutil.copytree(root/'finance-v17',source/'finance-v17',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copy2(root/'tests'/'run_historical_financial.py',target/'run_historical_financial.py')
(target/'SCHEMA10_EXPECTATION_ADAPTATIONS.json').write_text(json.dumps({'schema':10,'adaptations':adaptations,'sources':pins,'historical_sources_modified':False},indent=2)+'\n',encoding='utf-8')
print(json.dumps({'adaptations':len(adaptations),'historical_sources_modified':False,'target':str(target)}))
