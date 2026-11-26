"""리포트 생성 계약·인용 근거·기본 피드백·서버 결과 고정을 검증한다."""
import os
import tempfile
os.environ['MIA_DB_PATH'] = os.path.join(tempfile.mkdtemp(), 'report_ai.db')
import copy
import json
import unittest
from unittest.mock import patch
import httpx
from app import ai, gemini, harness


class ReportAiTests(unittest.TestCase):
    def setUp(self):
        self.scenario = harness.SCENARIOS['fire_office']
        self.results = {i: 'not_reached' for i in range(1, 6)}
        self.results[1] = 'correct'
        self.transcript = [{'stage': 1, 'role': 'user', 'text': '불이야! 119 신고할게요'}]
        self.data = {'summary': '화재 알림을 연습했습니다. 다음에는 대피 경로를 확인해 보세요.', 'items': [
            {'id': ev['id'], 'quote': self.transcript[0]['text'] if ev['stage'] == 1 else '',
             'comment': '발언과 행동 기준을 비교하세요.'} for ev in self.scenario['evaluation']]}
        env = patch.dict(os.environ, {'GEMINI_API_KEY': 'test-only', 'LLM_MODEL_SMART': 'gemini-3.1-flash-lite'})
        env.start()
        self.addCleanup(env.stop)
        p = patch('app.gemini.httpx.Client')
        self.post = p.start().return_value.__enter__.return_value.post
        self.addCleanup(p.stop)

    def response(self, data):
        return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {
            'parts': [{'text': json.dumps(data, ensure_ascii=False)}]}}],
            'usageMetadata': {'promptTokenCount': 50, 'candidatesTokenCount': 60, 'totalTokenCount': 110}})

    def generate(self):
        return gemini.evaluate(self.scenario, self.results, self.transcript)

    def test_valid_feedback_and_usage(self):
        self.post.return_value = self.response(self.data)
        result = self.generate()
        self.assertEqual(result['feedback_source'], 'ai')
        self.assertEqual(set(result['comments']), {e['id'] for e in self.scenario['evaluation']})
        self.assertEqual(result['usage']['totalTokenCount'], 110)

    def test_invented_quote_is_rejected(self):
        self.data['items'][0]['quote'] = '내가 말하지 않은 행동'
        self.post.return_value = self.response(self.data)
        self.assertIsNone(self.generate())
        self.assertEqual(self.post.call_count, 2)

    def test_unknown_or_missing_item_is_rejected(self):
        self.data['items'][0]['id'] = 'unknown'
        self.post.return_value = self.response(self.data)
        self.assertIsNone(self.generate())

    def test_api_failure_uses_nonempty_basic_feedback(self):
        self.post.return_value = httpx.Response(429)
        with patch('app.ai._api_key', return_value='test-only'):
            result = ai.evaluate(self.scenario, self.results, self.transcript)
        self.assertEqual(result['feedback_source'], 'basic')
        self.assertTrue(result['summary'])
        self.assertTrue(all(result['comments'].values()))
        self.assertEqual(self.post.call_count, 1)

    def test_ai_feedback_cannot_change_scores_and_is_cached(self):
        s, _ = harness.create_session('fire_office')
        s.status = 'cleared'
        s.stage_results = copy.deepcopy(self.results)
        generated = {'summary': '피드백', 'comments': {}, 'feedback_source': 'ai', 'passed': 999,
                     'status': 'failed', 'checks': [], 'model': 'test-model'}
        with patch('app.ai.evaluate', return_value=generated) as evaluate:
            first = harness.build_report(s)
            second = harness.build_report(s)
        self.assertEqual(first['passed'], 1)
        self.assertEqual(first['status'], 'cleared')
        self.assertEqual(len(first['checks']), 5)
        self.assertIs(first, second)
        evaluate.assert_called_once()


if __name__ == '__main__':
    unittest.main()
