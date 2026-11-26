"""스크린샷의 고정 재촉 반복과 AI 대사 보존을 검증한다."""
import os
import tempfile
os.environ['MIA_DB_PATH'] = os.path.join(tempfile.mkdtemp(), 'dialogue.db')
os.environ['LLM_PROVIDER'] = 'mock'
import unittest
from unittest.mock import patch
from app import harness, dialogue


class DialogueTests(unittest.TestCase):
    def setUp(self):
        self.s, _ = harness.create_session('earthquake_school')
        self.s.stage_index = 2
        self.st = harness.current_stage(self.s)

    def test_teacher_reply_does_not_repeat_fixed_prompt(self):
        suggestion = {'verdict': 'correct', 'reply': '응, 다 끝났어!', 'intent': 'action', 'reason': 'test'}
        replies = []
        with patch('app.ai.judge_action', return_value=suggestion):
            for _ in range(2):
                messages = harness.handle_message(self.s, '그냥 선생님지시만 따라다녀')
                replies.append(next(m['text'] for m in messages if m['role'] == 'character'))
        self.assertNotEqual(replies[0], replies[1])
        self.assertTrue(all('선생님' in r for r in replies))
        self.assertNotIn(self.st['partial_reply'], replies)
        self.assertEqual(self.s.stage_index, 2)
        self.assertEqual(self.s.risk, 0)
        self.assertFalse(self.s.evidence[3])

    def test_appropriate_unique_ai_reply_is_preserved(self):
        reply = '선생님이 우리 쪽을 보고 계셔. 나도 네 옆에 있을게.'
        with patch('app.ai.judge_action', return_value={'verdict': 'unclear', 'intent': 'chat', 'reply': reply, 'reason': 'test'}):
            messages = harness.handle_message(self.s, '선생님 보고 있지?')
        self.assertEqual(next(m['text'] for m in messages if m['role'] == 'character'), reply)

    def test_identical_ai_reply_is_replaced(self):
        suggestion = {'verdict': 'unclear', 'intent': 'chat', 'reply': '그래서 어떻게 할까?', 'reason': 'test'}
        replies = []
        with patch('app.ai.judge_action', return_value=suggestion):
            for text in ['조금 무서워', '그래도 같이 있어']:
                messages = harness.handle_message(self.s, text)
                replies.append(next(m['text'] for m in messages if m['role'] == 'character'))
        self.assertEqual(replies[0], suggestion['reply'])
        self.assertNotEqual(replies[0], replies[1])

    def test_ai_receives_current_turn_progress_without_committing_it(self):
        context = harness._ai_context(self.s, self.st, '계단으로 가자')
        self.assertIn('계단으로 이동', context['observed_this_turn'])
        self.assertNotIn('계단으로 이동', context['missing_after_turn'])
        self.assertEqual(context['server_preview'], 'unclear')
        self.assertEqual(self.s.evidence, {})
        context = harness._ai_context(self.s, self.st, '엘리베이터 타지 마. 계단으로 가자')
        self.assertEqual(context['server_preview'], 'correct')

    def test_polite_character_keeps_polite_fallback(self):
        stage = harness.SCENARIOS['fire_office']['stages'][4]
        character = harness.SCENARIOS['fire_office']['characters'][1]
        reply = dialogue.choose_reply(stage, character, '알겠습니다', 'unclear',
                                      {'verdict': 'correct', 'reply': '완료'}, [], [])
        self.assertIn('주시', reply)
        self.assertNotIn('말해 줘', reply)


if __name__ == '__main__':
    unittest.main()
