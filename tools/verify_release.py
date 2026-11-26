"""제출 기준 자동 검사. 실제 Gemini는 호출하지 않는다."""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--ui', action='store_true', help='설치된 Edge로 UI 검사도 실행')
args = parser.parse_args()
steps = []
for script in ['db_test.py', 'cms_test.py', 'decision_test.py', 'play_test.py', 'report_test.py',
               'safety_test.py', 'gemini_test.py', 'content_test.py', 'report_ai_test.py', 'reliability_test.py', 'dialogue_test.py', 'assessment_test.py']:
    steps.append((script, [sys.executable, '-X', 'utf8', script], ROOT / 'backend'))
steps.append(('frontend build', ['npm.cmd', 'run', 'build'], ROOT / 'frontend'))
if args.ui:
    steps.append(('ui_check.py', [sys.executable, '-X', 'utf8', 'ui_check.py'], ROOT / 'backend'))
results = []
for label, command, cwd in steps:
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
        output = result.stdout + result.stderr
        ok = result.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as error:
        output, ok = str(type(error).__name__), False
    summaries = [line for line in output.splitlines() if line.startswith(('Ran ', 'PASS:', '통과 ', 'OK'))]
    results.append({'step': label, 'passed': ok, 'summary': summaries, 'failure': output[-3000:] if not ok else ''})
    print(('PASS ' if ok else 'FAIL ') + label, flush=True)
    if not ok:
        print(output[-3000:], flush=True)
        break
qa = ROOT / '.qa'
qa.mkdir(exist_ok=True)
report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'live_ai': False,
          'passed': len(results) == len(steps) and all(x['passed'] for x in results), 'results': results}
(qa / 'release-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('Result: ' + ('PASS' if report['passed'] else 'FAIL'), flush=True)
sys.exit(not report['passed'])
