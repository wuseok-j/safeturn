"""판정 보류와 반복 응답에서 성공을 꾸며내지 않는 캐릭터 대사 선택."""
import re


def normalize(text):
    return re.sub(r'[\s.,!?…。！？]', '', text)


def choose_reply(stage, character, text, verdict, suggestion, history, observed):
    recent = [m['text'] for m in history if m['role'] == 'character'][-3:]
    generated = str(suggestion.get('reply') or '').strip()[:300]
    previous = {normalize(reply) for reply in recent}
    if generated and verdict == suggestion.get('verdict') and normalize(generated) not in previous:
        return generated
    if verdict != 'unclear':
        return stage['reactions'][verdict]
    polite = '존댓말' in character.get('speech_style', '')
    teacher = '선생님' in text and any(w in text for w in ('따라', '지시', '안내'))
    if polite:
        ack = '말씀하신 내용은 확인했습니다. ' if observed else ''
        options = [ack + '지금 직접 하실 행동을 조금 더 구체적으로 말씀해 주시겠습니까?',
                   '네, 듣고 있습니다. 이 상황에서 어떻게 움직이실지 말씀해 주십시오.',
                   '말씀하신 뜻은 알겠습니다. 지금 결정한 행동을 설명해 주십시오.',
                   '현재 상황에서 다음에 하실 행동을 구체적으로 확인하고 싶습니다.']
    else:
        ack = '응, 그렇게 할게. ' if observed else ''
        options = [ack + '지금 네가 할 행동을 조금 더 구체적으로 말해 줄래?',
                   '네 뜻은 알겠어. 지금 이 상황에서 어떻게 움직일지 말해 줘.',
                   '듣고 있어. 네가 결정한 행동을 한 번만 더 구체적으로 설명해 줘.',
                   '아직 좀 불안해. 네가 하려는 걸 이해할 수 있게 말해 줄래?']
        if teacher:
            options.insert(0, '선생님 안내를 따르자는 거지? 응, 같이 있을게. 지금 네가 하려는 행동도 말해 줘.')
            options.insert(1, '선생님 말씀을 같이 듣자는 뜻은 알겠어. 지금 이 자리에서 어떻게 행동할지도 알려 줘.')
    return next((reply for reply in options if normalize(reply) not in previous), options[-1])
