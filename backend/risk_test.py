"""위험 행동 표현·오탐·API 위험도/리포트 검증. 실제 AI 호출 없음."""
import os
import tempfile
os.environ['MIA_DB_PATH'] = os.path.join(tempfile.mkdtemp(), 'risk.db')
os.environ['LLM_PROVIDER'] = 'mock'

import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import harness, rules, scenario_check
from app.main import app
from demo_cases import ANSWERS


# 각 단계의 실행 의사 표현. AI가 unclear라도 서버에서 위험으로 판정해야 한다.
CASES = {
    'earthquake_school': [
        ['빨리 밖으로 나가자', '바깥으로 나갈게', '복도로 달려가자', '창문 쪽으로 가자'],
        ['친구를 밀고 먼저 가자', '선생님 안내 무시하고 가자', '혼자 뛰어나가자'],
        ['엘베 타고 내려가자', '승강기를 이용하자', '엘리베이터 탈게'],
        ['건물 바로 옆에서 기다리자', '외벽 밑에서 쉬자', '담장 가까이 서있자'],
        ['가방 찾으러 교실로 돌아가자', '건물에 다시 들어가자', '학교방송 무시하자'],
    ],
    'fire_office': [
        ['그냥 업무 보자', '연기는 무시하자', '계속 일하자'],
        ['엘리베이터 타고 내려가자', '엘레베이터 탈게', '승강기를 이용하자'],
        ['서서 내려가자', '허리 펴고 이동하자', '달려 내려가자'],
        ['문을 바로 열어', '문을 발로 차자', '손잡이 확인 안 하고 열자'],
        ['노트북 가지러 들어가자', '사무실로 다시 들어가자', '같이 들어가자'],
    ],
    'elevator_apartment': [
        ['문을 강제로 열자', '억지로 벌리자'],
        ['천장을 열어보자', '환기구로 나가자'],
        ['점프해요', '엘리베이터를 흔들자', '벽을 발로 차자'],
        ['틈으로 뛰어내리자', '혼자 나갈게', '구조대원 지시 무시하자'],
        ['같은 엘리베이터를 탈게', '다시 타고 가자', '점검 중인 승강기 이용하자'],
    ],
}


class RiskTests(unittest.TestCase):
    def test_expanded_expressions_raise_risk_even_when_ai_says_unclear(self):
        client = TestClient(app)
        with patch('app.ai.judge_action', return_value={
                'verdict': 'unclear', 'intent': 'chat', 'reply': '어떻게 할까?', 'reason': 'test'}):
            for sid, stages in CASES.items():
                for index, texts in enumerate(stages):
                    for text in texts:
                        with self.subTest(sid=sid, stage=index + 1, text=text):
                            session, _ = harness.create_session(sid)
                            self.addCleanup(harness.SESSIONS.pop, session.id, None)
                            session.stage_index = index
                            stage = harness.current_stage(session)
                            response = client.post(f'/sessions/{session.id}/messages', json={'text': text})
                            self.assertEqual(response.status_code, 200)
                            self.assertEqual(response.json()['risk'], stage['if_wrong']['risk_delta'])
                            self.assertEqual(session.timeline[-1]['verdict'], 'wrong')
                            self.assertEqual(session.timeline[-1]['risk_before'], 0)
                            self.assertEqual(session.timeline[-1]['risk_after'], session.risk)

    def test_questions_negations_and_safe_answers_do_not_raise_risk(self):
        for sid, stages in CASES.items():
            for index, texts in enumerate(stages):
                stage = harness.SCENARIOS[sid]['stages'][index]
                for text in texts:
                    with self.subTest(sid=sid, stage=index + 1, text=text):
                        self.assertFalse(rules.dangerous(stage, text + '?'))
                self.assertFalse(rules.dangerous(stage, ANSWERS[sid][index]))
        examples = [
            ('earthquake_school', 0, '밖으로 나가지 마'),
            ('earthquake_school', 0, '밖으로 나가지는 말자'),
            ('earthquake_school', 0, '밖으로 안 나가자'),
            ('earthquake_school', 0, '복도로 뛰어나가지 마'),
            ('earthquake_school', 0, '밖으로 나가면 안 돼'),
            ('earthquake_school', 0, '밖으로 나가도 될까'),
            ('earthquake_school', 0, '흔들림이 멈추면 밖으로 나가자'),
            ('earthquake_school', 0, '흔들림이 멈춘 뒤 밖으로 나가자'),
            ('earthquake_school', 2, '엘리베이터 타지 말고 계단으로 가자'),
            ('earthquake_school', 3, '건물 옆에서 기다리지 마'),
            ('fire_office', 4, '노트북 가지러 들어가지 마'),
            ('elevator_apartment', 0, '문을 강제로 열지 마'),
            ('elevator_apartment', 2, '엘리베이터를 흔들지 마'),
        ]
        for sid, index, text in examples:
            with self.subTest(text=text):
                self.assertFalse(rules.dangerous(harness.SCENARIOS[sid]['stages'][index], text))

    def test_safe_or_question_sentence_cannot_hide_following_danger(self):
        stage = harness.SCENARIOS['earthquake_school']['stages'][0]
        for text in ['밖으로 나가도 돼? 빨리 밖으로 나가자',
                     '흔들림이 멈추면 밖으로 나가자. 아니 지금 밖으로 나갈게',
                     '책상 아래에서 몸을 보호하자. 아니 복도로 달려가자']:
            with self.subTest(text=text):
                self.assertTrue(rules.dangerous(stage, text))

    def test_repeated_danger_ends_play_and_report_preserves_risk(self):
        client = TestClient(app)
        with patch('app.ai._api_key', return_value=None):
            session, _ = harness.create_session('earthquake_school')
            self.addCleanup(harness.SESSIONS.pop, session.id, None)
            for _ in range(3):
                result = client.post(f'/sessions/{session.id}/messages', json={'text': '빨리 밖으로 나가자'})
            self.assertEqual(result.json()['status'], 'failed')
            self.assertEqual(result.json()['risk'], session.scenario['max_risk'])
            report = client.get(f'/sessions/{session.id}/report').json()
            self.assertEqual(report['timeline'][-1]['risk_after'], session.risk)

    def test_ai_wrong_alone_still_cannot_raise_risk(self):
        session, _ = harness.create_session('earthquake_school')
        self.addCleanup(harness.SESSIONS.pop, session.id, None)
        with patch('app.ai.judge_action', return_value={
                'verdict': 'wrong', 'intent': 'action', 'reply': '불안해.', 'reason': 'test'}):
            harness.handle_message(session, '어떻게 해야 할지 생각 중이야')
        self.assertEqual(session.risk, 0)
        self.assertEqual(session.timeline[-1]['verdict'], 'unclear')

    def test_scenarios_validate(self):
        for sid in CASES:
            self.assertEqual(scenario_check.check(harness.SCENARIOS[sid])['errors'], [])


if __name__ == '__main__':
    unittest.main()
