"""검증한 소스·빌드·증빙만 포함하고 키·DB·개인 서류를 제외한 제출 ZIP 생성."""
import hashlib
import json
from pathlib import Path
import zipfile
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
report_path = ROOT / '.qa/release-check.json'
if not report_path.exists() or not json.loads(report_path.read_text(encoding='utf-8')).get('passed'):
    raise SystemExit('tools/verify_release.py --ui 성공 후 패키징하세요.')
secret_values = [v for k, v in dotenv_values(ROOT / '.env').items()
                 if ('KEY' in k or 'TOKEN' in k) and v and len(v) >= 8]
skip_dirs = {'.venv', 'venv', 'node_modules', '__pycache__', '.git', '.vite'}
skip_suffixes = {'.db', '.db-shm', '.db-wal', '.sqlite3', '.pyc', '.log', '.hwp', '.hwpx'}
paths = []
for directory in ('backend', 'frontend', 'data', 'docs'):
    for path in (ROOT / directory).rglob('*'):
        if not path.is_file() or any(p in skip_dirs for p in path.relative_to(ROOT).parts):
            continue
        if path.suffix in skip_suffixes or '.db-' in path.name or path.name.endswith('.env'):
            continue
        if path.name.startswith('.'):
            continue
        paths.append((path, str(Path('SafeTurn') / path.relative_to(ROOT)).replace('\\', '/')))
for name in ('README.md', 'AGENTS.md', 'CLAUDE.md', '.env.example', '.gitignore', 'SUBMISSION.txt', 'start-local.cmd'):
    paths.append((ROOT / name, f'SafeTurn/{name}'))
for name in ('build_scene_assets.py', 'verify_release.py', 'package_submission.py'):
    paths.append((ROOT / 'tools' / name, f'SafeTurn/tools/{name}'))
paths.append((report_path, 'SafeTurn/evidence/release-check.json'))
for path in (ROOT / '.qa').glob('*-*-play.png'):
    paths.append((path, f'SafeTurn/evidence/{path.name}'))
for path in (ROOT / '.qa').glob('*-*-report.png'):
    paths.append((path, f'SafeTurn/evidence/{path.name}'))
if (ROOT / '.qa/cms-editor.png').exists():
    paths.append((ROOT / '.qa/cms-editor.png', 'SafeTurn/evidence/cms-editor.png'))

for path, archive_name in paths:
    if path.suffix in ('.png', '.jpg', '.jpeg'):
        continue
    content = path.read_bytes()
    if any(value.encode('utf-8') in content for value in secret_values):
        raise SystemExit('비밀값 포함으로 패키징 중단: ' + archive_name)

out = ROOT / 'outputs/submission'
out.mkdir(parents=True, exist_ok=True)
target = out / 'SafeTurn_final_20261126.zip'
with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for path, name in sorted(paths, key=lambda entry: entry[1]):
        archive.write(path, name)
with zipfile.ZipFile(target) as archive:
    assert archive.testzip() is None
    assert 'SafeTurn/.env' not in archive.namelist()
    assert 'SafeTurn/frontend/dist/index.html' in archive.namelist()
    assert 'SafeTurn/data/scenarios/earthquake_school.json' in archive.namelist()
    assert not any(name.endswith(('.hwp', '.db')) for name in archive.namelist())
digest = hashlib.sha256(target.read_bytes()).hexdigest()
(out / 'SHA256.txt').write_text(f'{digest}  {target.name}\n', encoding='ascii')
print(f'PASS: {len(paths)} files, {target.stat().st_size:,} bytes, secret scan and ZIP integrity')
print(target)
