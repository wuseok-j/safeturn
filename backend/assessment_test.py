"""자연스러운 경로 선택과 설명 가능한 미충족 판정 회귀 검사."""
import os
import tempfile
os.environ['MIA_DB_PATH'] = os.path.join(tempfile.mkdtemp(), 'assessment.db')
os.environ['LLM_PROVIDER'] = 'mock'
import copy
import unittest
from unittest.mock import patch
from app import harness, rules


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.s, _ = harness.create_session('earthquake_school')
        self.s.stage_index = 2
        self.stage = harness.current_stage(self.s)

    def test_screenshot_phrase_satisfies_both_route_items(self):
        for text in ['엘리베이터는위험해 계단으로가자', '엘리베이터 대신 계단으로 가자',
                     '엘리베이터 말고 계단으로 가자', '계단으로 가자. 엘리베이터는 위험해']:
            with self.subTest(text=text):
                self.assertEqual(set(rules.observe(self.stage, text)), {'stairs', 'no_lift'})

    def test_route_advances_without_redundant_stop_phrase(self):
        harness.handle_message(self.s, '엘리베이터는위험해 계단으로가자')
        self.assertEqual(self.s.stage_results[3], 'correct')
        self.assertEqual(self.s.stage_index, 3)
        self.assertEqual(self.s.risk, 0)

    def test_danger_negation_and_questions_do_not_get_free_pass(self):
        for text in ['엘리베이터 위험해? 계단으로 가자?', '엘리베이터 위험해. 계단으로 가지 마',
                     '엘리베이터는 위험해 계단으로 가자. 아니 같이 타자']:
            with self.subTest(text=text):
                self.assertNotIn('no_lift', rules.observe(self.stage, text))

    def test_fire_route_gets_same_interpretation(self):
        fire = harness.SCENARIOS['fire_office']['stages'][1]
        self.assertEqual(set(rules.observe(fire, '엘리베이터는 위험해. 계단으로 가자')), {'stairs', 'stop_lift'})

    def test_missing_action_explanation_preserves_partial_evidence(self):
        for text in ['계단으로 가자', '계단으로 가자', '아직 움직이지 마.']:
            harness.handle_message(self.s, text)
        self.assertEqual(self.s.stage_index, 2)
        self.assertEqual(self.s.turns_in_stage, 0)
        # 이전에 저장된 미충족 단계도 같은 기준으로 설명한다.
        self.s.stage_results[3] = 'failed'
        self.s.status = 'cleared'
        report = harness.build_report(self.s)
        check = report['checks'][2]
        self.assertEqual(check['result'], 'failed')
        self.assertEqual(check['missing_actions'], ['엘리베이터 탑승 제지'])
        self.assertIn('2개 중 1개', check['reason'])
        self.assertEqual(len(check['action_reviews']), 2)
        self.assertIn('위험 행동 판정은 아닙니다', check['action_reviews'][1]['note'])
        self.assertEqual(report['assessment_note'], '')

    def test_risk_limit_has_separate_reason(self):
        harness.handle_message(self.s, '같이 타자')
        harness.handle_message(self.s, '같이 타자')
        report = harness.build_report(self.s)
        check = report['checks'][2]
        self.assertEqual(check['reason_code'], 'risk_limit')
        self.assertIn('위험도 +3', check['action_reviews'][0]['note'])

    def test_legacy_report_is_explained_without_regrading_or_ai_call(self):
        self.s.status = 'cleared'
        old = copy.deepcopy(harness.build_report(self.s))
        old.pop('assessment_version')
        self.s.report = old
        before = old['passed']
        with patch('app.ai.evaluate') as ai:
            result = harness.build_report(self.s)
        ai.assert_not_called()
        self.assertEqual(result['passed'], before)
        self.assertIn('이전 판정 기준', result['assessment_note'])


if __name__ == '__main__':
    unittest.main()
