"""화재·지진 시나리오와 장면 파일, 판정 사례를 오프라인 검증한다."""
import os
import tempfile
os.environ['MIA_DB_PATH'] = os.path.join(tempfile.mkdtemp(), 'content.db')
os.environ['LLM_PROVIDER'] = 'mock'
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import harness, rules, scenario_check
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
from demo_cases import ANSWERS


class ContentTests(unittest.TestCase):
    def setUp(self):
        p = patch('app.ai._api_key', return_value=None)
        p.start()
        self.addCleanup(p.stop)

    def test_content_validation_and_every_image_exists(self):
        for sid in ANSWERS:
            sc = harness.SCENARIOS[sid]
            self.assertEqual(scenario_check.check(sc)['errors'], [], sid)
            paths = [sc['thumbnail'], sc['cleared_image']]
            for st in sc['stages']:
                paths.extend([st['image'], st['action_image']])
                paths.extend(option['image'] for option in st.get('action_alternatives', []))
            for path in paths:
                self.assertTrue((ROOT / 'frontend/public/scenes' / path).is_file(), path)

    def test_action_scene_is_only_sent_for_a_confirmed_transition(self):
        client = TestClient(app)
        started = client.post('/sessions', json={'scenario_id': 'fire_office'}).json()
        url = f"/sessions/{started['session_id']}/messages"
        self.assertIsNone(started['action_scene'])
        for text in ('그냥 기다리자', '불이야!'):
            turn = client.post(url, json={'text': text}).json()
            self.assertEqual(turn['stage'], 1)
            self.assertIsNone(turn['action_scene'])
        turn = client.post(url, json={'text': '비상벨을 누를게'}).json()
        self.assertEqual(turn['stage'], 2)
        self.assertEqual(turn['action_scene']['image'], 'fire_office/action1-ai.jpg')
        count = turn['action_scene']['message_count']
        self.assertEqual([m['role'] for m in turn['messages'][:count]], ['user', 'character'])
        self.assertEqual(turn['messages'][count]['role'], 'narrator')
        self.assertIsNone(client.get(f"/sessions/{started['session_id']}").json()['action_scene'])

        started = client.post('/sessions', json={'scenario_id': 'fire_office'}).json()
        for _ in range(3):
            turn = client.post(f"/sessions/{started['session_id']}/messages", json={'text': '음...'}).json()
        self.assertEqual(turn['stage'], 2)
        self.assertIsNone(turn['action_scene'])

    def test_both_scenarios_complete_with_all_evidence(self):
        for sid, answers in ANSWERS.items():
            with self.subTest(sid=sid):
                s, _ = harness.create_session(sid)
                for index, text in enumerate(answers):
                    self.assertEqual(s.stage_index, index)
                    harness.handle_message(s, text)
                self.assertEqual(s.status, 'cleared')
                report = harness.build_report(s)
                self.assertEqual(report['passed'], 5)
                self.assertTrue(all(e['met'] for c in report['checks'] for e in c['evidence']))

    def test_each_stage_good_bad_ambiguous_question(self):
        cases = {
            'fire_office': ['그냥 기다리자', '같이 타자', '숨 참고 뛰자', '확 열어', '같이 들어가자'],
            'earthquake_school': ['복도로 뛰자', '선생님 무시하고 먼저 뛰자', '같이 타자', '벽 옆에서 기다리자', '방송 무시하자'],
        }
        for sid, answers in ANSWERS.items():
            for index, (good, bad) in enumerate(zip(answers, cases[sid])):
                with self.subTest(sid=sid, stage=index + 1):
                    st = harness.SCENARIOS[sid]['stages'][index]
                    self.assertEqual(set(rules.observe(st, good)), {r['id'] for r in st['rubric']})
                    self.assertTrue(rules.dangerous(st, bad), bad)
                    self.assertEqual(rules.observe(st, '음...'), [])
                    self.assertEqual(rules.observe(st, '지금 어디야?'), [])

    def test_ai_wrong_alone_cannot_raise_risk(self):
        s, _ = harness.create_session('fire_office')
        with patch('app.ai.judge_action', return_value={'verdict': 'wrong', 'intent': 'chat', 'reply': '위험해', 'reason': 'test'}):
            harness.handle_message(s, '조금 무서워')
        self.assertEqual(s.risk, 0)


if __name__ == '__main__':
    unittest.main()
