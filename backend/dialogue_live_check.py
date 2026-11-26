"""반복 응답 재현용 실제 Gemini 2회 검사. 임시 DB, API 비용 발생."""
import os
import tempfile
os.environ['MIA_DB_PATH'] = os.path.join(tempfile.mkdtemp(), 'dialogue-live.db')
os.environ['LLM_PROVIDER'] = 'gemini'
from app import ai, harness

if not ai._api_key():
    raise SystemExit('Gemini 키 설정 필요')
s, _ = harness.create_session('earthquake_school')
s.stage_index = 2
s.stage_results = {1: 'correct', 2: 'correct'}
s.conditions = {'shelter': 'success', 'guided': 'success'}
harness._enter_stage(s)
replies = []
for text in ['그냥 선생님지시만 따라다녀', '응, 선생님 말씀대로 같이 움직이자']:
    messages = harness.handle_message(s, text)
    reply = next((m['text'] for m in messages if m['role'] == 'character'), None)
    if not reply:
        raise SystemExit('실제 AI 응답 실패: ' + str(messages))
    replies.append(reply)
    print('user:', text, flush=True)
    print('character:', reply, flush=True)
assert replies[0] != replies[1]
assert s.stage_index == 2 and s.risk == 0
print('PASS: two live responses differ, no invented progression', flush=True)
