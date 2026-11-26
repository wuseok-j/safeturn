"""제출 전 회귀: 중복 전송·재시작·동시 요청·만료·부정문·질문."""
import os
import tempfile
os.environ['MIA_DB_PATH'] = os.path.join(tempfile.mkdtemp(), 'reliability.db')
os.environ['LLM_PROVIDER'] = 'mock'
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import db, harness, rules
from app.main import app


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.sid = self.client.post('/sessions', json={'scenario_id': 'fire_office'}).json()['session_id']
        self.body = {'text': '불이야! 119 신고할게요', 'request_id': 'retry-id-0001', 'expected_stage': 1}

    def send(self, body=None):
        return self.client.post(f'/sessions/{self.sid}/messages', json=body or self.body)

    def test_same_request_processed_once(self):
        first = self.send()
        second = self.send()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        s = harness.get_session(self.sid)
        self.assertEqual(len(s.timeline), 1)
        self.assertEqual(len([m for m in s.transcript if m['role'] == 'user']), 1)

    def test_retry_survives_memory_reset(self):
        first = self.send().json()
        harness.SESSIONS.pop(self.sid)
        self.assertEqual(self.send().json(), first)
        self.assertEqual(len(harness.get_session(self.sid).timeline), 1)

    def test_concurrent_duplicate_is_single_action(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: self.send(), range(2)))
        self.assertTrue(all(r.status_code == 200 for r in responses))
        self.assertEqual(responses[0].json(), responses[1].json())
        self.assertEqual(len(harness.get_session(self.sid).timeline), 1)

    def test_stale_stage_and_changed_retry_are_rejected(self):
        self.send()
        changed = {**self.body, 'text': '다른 입력'}
        self.assertEqual(self.send(changed).status_code, 409)
        stale = {**self.body, 'request_id': 'different-id-0002'}
        self.assertEqual(self.send(stale).status_code, 409)
        self.assertEqual(len(harness.get_session(self.sid).timeline), 1)

    def test_in_memory_session_also_expires(self):
        with db.connect() as conn:
            conn.execute("UPDATE sessions SET updated_at='2000-01-01T00:00:00+00:00' WHERE id=?", (self.sid,))
        self.assertEqual(self.client.get(f'/sessions/{self.sid}').status_code, 404)

    def test_negated_protection_does_not_pass_but_stop_instruction_does(self):
        stage = harness.SCENARIOS['fire_office']['stages'][2]
        self.assertNotIn('cover', rules.observe(stage, '소매로 코와 입을 막지 마'))
        eq = harness.SCENARIOS['earthquake_school']['stages'][1]
        self.assertNotIn('head', rules.observe(eq, '머리를 보호하지 않아도 돼'))
        elevator = harness.SCENARIOS['fire_office']['stages'][1]
        self.assertIn('stop_lift', rules.observe(elevator, '엘리베이터 타지 마'))

    def test_question_is_not_risky_action(self):
        stage = harness.SCENARIOS['fire_office']['stages'][1]
        self.assertFalse(rules.dangerous(stage, '같이 타자?'))
        self.assertTrue(rules.dangerous(stage, '같이 타자'))

    def test_simultaneous_reports_generate_once(self):
        s = harness.get_session(self.sid)
        s.status = 'cleared'
        harness.persist(s)
        with patch('app.ai.evaluate', return_value={'summary': '기본 피드백', 'comments': {}}) as generate:
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda _: self.client.get(f'/sessions/{self.sid}/report'), range(2)))
        self.assertTrue(all(r.status_code == 200 for r in responses))
        generate.assert_called_once()

    def test_health_never_returns_keys(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['mode'], 'mock')
        self.assertEqual(set(response.json()), {'status', 'mode', 'model', 'admin_configured'})

    def test_blank_input_rejected_without_attempt(self):
        self.assertEqual(self.send({'text': '   '}).status_code, 422)
        self.assertEqual(harness.get_session(self.sid).turns_in_stage, 0)

    def test_quota_notice_preserves_state(self):
        with patch('app.ai.judge_action', return_value={'verdict': 'unclear', 'reply': '', 'reason': 'fallback', 'error_code': 'quota'}):
            response = self.send().json()
        self.assertIn('이용 요청', response['messages'][-1]['text'])
        self.assertEqual(response['risk'], 0)
        self.assertEqual(response['attempts_left'], 3)


if __name__ == '__main__':
    unittest.main()
