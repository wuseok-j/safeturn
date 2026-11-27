"""화재·지진·엘리베이터 시나리오와 장면 파일, 판정 사례를 오프라인 검증한다."""
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
            paths = [sc['thumbnail'], sc['cleared_image'], *harness.INTERACTION_IMAGES.values()]
            for st in sc['stages']:
                paths.extend([st['image'], st['action_image']])
                paths.extend(option['image'] for option in st.get('action_alternatives', []))
                paths.extend(item['partial_scene']['image'] for item in st.get('rubric', []) if item.get('partial_scene'))
                wrong = st['if_wrong']
                paths.extend(outcome['image'] for outcome in [wrong, *wrong.get('events', [])] if outcome.get('image'))
            for path in paths:
                self.assertTrue((ROOT / 'frontend/public/scenes' / path).is_file(), path)

    def test_action_scene_and_outcome_on_the_same_stage(self):
        client = TestClient(app)
        started = client.post('/sessions', json={'scenario_id': 'fire_office'}).json()
        url = f"/sessions/{started['session_id']}/messages"
        self.assertIsNone(started['action_scene'])
        turn = client.post(url, json={'text': '그냥 기다리자'}).json()
        self.assertEqual(turn['stage'], 1)
        self.assertEqual(turn['action_scene']['kind'], 'outcome')
        self.assertEqual(turn['action_scene']['image'], 'fire_office/stage1-ai.jpg')
        self.assertEqual(turn['action_scene']['message_count'], 2)
        turn = client.post(url, json={'text': '불이야!'}).json()
        self.assertEqual(turn['stage'], 1)
        self.assertEqual(turn['action_scene']['kind'], 'partial')
        self.assertEqual(turn['image'], 'fire_office/partial-warn.jpg')
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
        self.assertEqual(turn['stage'], 1)
        self.assertEqual(turn['stage_mistakes'], 0)
        self.assertIsNone(turn['action_scene'])

    def test_free_action_images_match_the_intent(self):
        client = TestClient(app)
        turn = client.post('/sessions', json={'scenario_id': 'earthquake_school'}).json()
        url = f"/sessions/{turn['session_id']}/messages"
        for text, image in [('벽을 두드려볼게', 'action-knock.jpg'),
                            ('휴대폰으로 바닥을 비춰볼게', 'action-light.jpg'),
                            ('손으로 벽을 만져볼게', 'action-hands.jpg')]:
            with self.subTest(text=text):
                turn = client.post(url, json={'text': text}).json()
                self.assertEqual(turn['stage'], 1)
                self.assertEqual(turn['stage_mistakes'], 0)
                scene = turn['action_scene']
                self.assertEqual(scene['kind'], 'outcome')
                self.assertEqual(scene['image'], f'interactions/{image}')
                self.assertEqual(scene['description'], turn['messages'][1]['text'])
        turn = client.post(url, json={'text': '벽을 두드려볼까?'}).json()
        self.assertIsNone(turn['action_scene'])

    def test_partial_action_has_a_persistent_scene_and_an_indirect_hint(self):
        client = TestClient(app)
        for sid, text, image, hint, rest in [
            ('earthquake_school', '책상 아래에 숨자', 'partial-shelter.jpg', '책상이 자꾸 밀려', '책상 다리를 잡을게'),
            ('fire_office', '불이야!', 'partial-warn.jpg', '여기 없는 사람들', '119에 신고할게요'),
            ('elevator_apartment', '문 억지로 열지 마', 'partial-stop-door.jpg', '밖에 있는 사람들', '인터폰을 눌러서 갇혔다고 알리자'),
        ]:
            with self.subTest(scenario=sid):
                start = client.post('/sessions', json={'scenario_id': sid}).json()
                url = f"/sessions/{start['session_id']}"
                with patch('app.ai.judge_action', side_effect=AssertionError('partial is server-verified')):
                    turn = client.post(f'{url}/messages', json={'text': text}).json()
                self.assertEqual(turn['stage'], 1)
                self.assertEqual(turn['risk'], 0)
                self.assertEqual(turn['stage_mistakes'], 0)
                self.assertEqual(len(turn['confirmed_actions']), 1)
                self.assertEqual(turn['action_scene']['kind'], 'partial')
                self.assertEqual(turn['action_scene']['image'], f'{sid}/{image}')
                self.assertIn(hint, turn['messages'][-1]['text'])
                harness.SESSIONS.pop(start['session_id'])
                resumed = client.get(url).json()
                self.assertEqual(resumed['image'], f'{sid}/{image}')
                self.assertEqual(resumed['confirmed_actions'], turn['confirmed_actions'])
                self.assertIsNone(resumed['action_scene'])
                saved = harness.SESSIONS[start['session_id']]
                stage = harness.current_stage(saved)
                self.assertEqual(harness._ai_context(saved, stage)['situation'], resumed['situation'])
                final = client.post(f'{url}/messages', json={'text': rest}).json()
                self.assertEqual(final['stage'], 2)
                self.assertEqual(final['confirmed_actions'], [])

    def test_elevator_stage_action_and_completion_images(self):
        client = TestClient(app)
        turn = client.post('/sessions', json={'scenario_id': 'elevator_apartment'}).json()
        self.assertEqual(turn['image'], 'elevator_apartment/stage1-ai.png')
        self.assertTrue(turn['image_includes_speaker'])
        url = f"/sessions/{turn['session_id']}/messages"
        for number, text in enumerate(ANSWERS['elevator_apartment'], start=1):
            turn = client.post(url, json={'text': text}).json()
            self.assertEqual(turn['action_scene']['image'], f'elevator_apartment/action{number}-ai.png')
            self.assertTrue(turn['action_scene']['description'])
            self.assertEqual(turn['image'], f'elevator_apartment/stage{number + 1}-ai.png'
                             if number < 5 else 'elevator_apartment/cleared-ai.png')
        self.assertEqual(turn['status'], 'cleared')
        resumed = client.get(url.removesuffix('/messages')).json()
        self.assertEqual(resumed['image'], 'elevator_apartment/cleared-ai.png')
        self.assertIsNone(resumed['action_scene'])

    def test_public_cast_has_portraits_and_introductions_without_internal_prompts(self):
        response = TestClient(app).get('/scenarios')
        self.assertEqual(response.status_code, 200)
        for scenario in response.json():
            for character in scenario['characters']:
                with self.subTest(character=character['name']):
                    self.assertTrue(character['introduction'])
                    self.assertTrue(character['quote'])
                    self.assertTrue((ROOT / 'frontend/public/scenes' / character['image']).is_file())
                    self.assertNotIn('personality', character)
                    self.assertNotIn('speech_style', character)

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
            'elevator_apartment': ['문 벌려서 나가자', '천장 뚜껑 열자', '같이 뛰어보자', '먼저 뛰어내리자', '그냥 다시 타자'],
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
