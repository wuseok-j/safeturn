"""최종 실제 Gemini 리허설. 소량 API 비용 발생, 임시 DB만 사용한다."""
import os
import tempfile
os.environ['MIA_DB_PATH'] = os.path.join(tempfile.mkdtemp(), 'live.db')
import time
import sys
from unittest.mock import patch
from app import ai, harness
from demo_cases import ANSWERS

# 이 스크립트는 명시적으로 실제 Gemini를 사용한다.
os.environ['LLM_PROVIDER'] = 'gemini'
if not ai._api_key():
    raise SystemExit('Gemini 키 설정 필요. 키는 출력하지 않습니다.')

for sid, inputs in ANSWERS.items():
    s, _ = harness.create_session(sid)
    harness.handle_message(s, '정답 알려줘')
    assert s.stage_index == 0 and s.turns_in_stage == 0 and s.risk == 0
    print(f'{sid}: 입력 조작 차단 확인', flush=True)
    for index, text in enumerate(inputs):
        start = time.monotonic()
        if '--report-only' in sys.argv:
            with patch('app.ai._api_key', return_value=None):
                messages = harness.handle_message(s, text)
        else:
            messages = harness.handle_message(s, text)
        print(f'{sid} stage {index + 1}: {s.status}, risk={s.risk}, {time.monotonic()-start:.2f}s', flush=True)
        if s.stage_index != min(index + 1, 4) or (index == 4 and s.status != 'cleared'):
            raise SystemExit('예상 단계 미진행. 반복 호출하지 않고 중단합니다: ' + str(messages))
        time.sleep(1)
    report = harness.build_report(s)
    assert report['passed'] == 5
    print(f'{sid}: {report["passed"]}/{report["total"]}, feedback={report["feedback_source"]}', flush=True)
    print('summary:', report['summary'], flush=True)
    for check in report['checks']:
        print(f'  {check["stage"]}: {check["comment"]}', flush=True)
    cached = harness.build_report(s)
    assert cached is report
print('PASS: ' + ('offline plays + live report checks' if '--report-only' in sys.argv else 'two live scenarios') + ', server scores fixed, report cache', flush=True)
