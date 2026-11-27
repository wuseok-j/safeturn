"""Gemini action adapter; deterministic report comments.

No key (or LLM_PROVIDER=mock) keeps offline playback available.
The harness owns progression, risk, evidence and results.
"""
from __future__ import annotations
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from . import gemini, rules

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_ACTION_END = re.compile(r'(?:자|보자|을게|할게|갈게|올게|볼게|을래|할래|겠어|겠습니다|해줘|해봐)$')
_HESITATION = re.compile(r'생각(좀|을|해|하)|고민|망설|모르겠|할지|(?:지말자|그만하자)$')
_MOCK_INTERACTIONS = (
    (r'두드리|두드려|부딪|내리치|내리쳐|던지|던져',
     '행동을 시도하자 가까운 곳에 소리가 짧게 울린다. 두 사람은 잠시 멈춰 주변의 반응을 살핀다.',
     '방금 소리 들었지? 주변은 아직 그대로야.'),
    (r'살펴|찾아|둘러|들여다|비춰|비추',
     '가까이 보이는 곳부터 살핀다. 지금 자리에서 확인할 수 있는 범위까지만 보인다.',
     '여기서 보이는 건 같이 살펴볼게.'),
    (r'부르|불러|신호|소리치|소리쳐|전화|연락',
     '지금 자리에서 신호를 보내 보지만, 상대에게 닿았는지는 아직 확인되지 않는다.',
     '잠깐, 반응이 오는지 들어볼게.'),
    (r'밀|옮기|옮겨|들어올|당겨|당기',
     '손을 뻗어 말한 동작을 시도한다. 바로 뜻대로 되지 않아 두 사람은 손을 멈춘다.',
     '잠깐, 생각처럼 움직이지 않아.'),
)


def _api_key():
    return gemini.api_key() if os.getenv("LLM_PROVIDER", "gemini").strip().lower() == "gemini" else None


def judge_action(scenario, stage, character, user_text, history):
    provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    if provider not in ("gemini", "mock"):
        return dict(gemini.FALLBACK)
    if not _api_key():
        return _mock_judge_action(scenario, stage, character, user_text, history)
    return gemini.judge(scenario, stage, character, user_text, history)


def _mock_judge_action(scenario: dict, stage: dict, character: dict,
                       user_text: str, history: list[dict]) -> dict:
    """이용자의 행동(말)을 보고 판정을 '제안'하고, 캐릭터의 다음 대사를 만든다.

    scenario:  시나리오 전체 (role_doc 등)
    stage:     현재 단계 (situation, correct_action, keywords ...)
    character: 지금 말하는 캐릭터 (name, personality, speech_style)
    user_text: 이용자의 이번 입력
    history:   이번 단계에서 오간 대화 [{"role": "narrator"|"character"|"user"|"system", "name", "text"}]

    반환: {"verdict": "correct" | "wrong" | "unclear",
           "intent":  "action" | "question" | "chat"  (질문·대화는 판단 기회를 쓰지 않음. 서버가 최종 결정),
           "reply":   캐릭터 대사 (1~2문장, 캐릭터 말투),
           "reason":  판정 이유 한 줄 (로그·디버깅용, 화면에 안 나감)}
      - correct: correct_action 의 핵심을 실행하거나 제안함
      - wrong:   위험한 행동을 하거나 따라가려 함
      - unclear: 그 외 (질문, 애매함, 상황과 무관한 말)
    실패 시 {"verdict": "unclear", "reply": "", "reason": "fallback"}
      → reply 가 비어 있으면 서버가 stage["reactions"] 문장을 대신 쓴다.
    """
    # API 키가 없을 때 쓰는 키워드 기반 가짜 판정.
    text = rules.action_text(user_text)
    preview = stage.get('server_preview')
    if preview == 'wrong' or (preview and stage.get('rubric')):
        verdict = preview
    elif any(rules.compact(k) in text for k in stage["keywords"]):
        verdict = "correct"
    elif any("".join(k.split()) in text for k in stage.get("wrong_keywords", [])):
        verdict = "wrong"
    else:
        verdict = "unclear"
    intent = 'action' if verdict != 'unclear' or stage.get('observed_this_turn') else 'chat'
    if intent == 'chat' and (user_text.strip().endswith(('?', '？')) or rules.QUESTION_END.search(rules.compact(user_text))):
        intent = 'question'
    reply = stage["reactions"][verdict]
    if intent == "question":
        reply = stage.get("question_reply", "지금 그런 거 따질 때야? 빨리 어떻게 할지 정해!")
    elif intent == 'chat' and any(phrase in text for phrase in ('움직이지마', '잠깐멈춰', '잠깐기다려')):
        reply = '네, 잠시 멈추겠습니다.' if '존댓말' in character.get('speech_style', '') else '알았어, 잠깐 멈출게.'
    interaction = ''
    visual = 'scene'
    if intent == 'chat' and _ACTION_END.search(text) and not _HESITATION.search(text):
        intent = 'action'
        interaction = '말한 행동을 이 자리에서 시도한다. 주변을 살피는 사이에도 현재 상황은 이어진다.'
        reply = '응, 옆에서 지켜보고 있어.'
        for pattern, outcome, reaction in _MOCK_INTERACTIONS:
            if re.search(pattern, text):
                interaction, reply = outcome, reaction
                break
        if re.search(r'두드리|두드려', text):
            visual = 'knock'
        elif re.search(r'(휴대폰|휴대전화|손전등|플래시).{0,8}(비춰|비추)', text):
            visual = 'light'
        elif re.search(r'(손으?로|표면|벽).{0,8}(만지|만져|밀)', text):
            visual = 'touch'
    return {"verdict": verdict, "intent": intent, "interaction": interaction, "interaction_visual": visual, "reply": reply,
            "reason": "mock: keyword match"}


def evaluate(scenario: dict, results: dict[int, str], transcript: list[dict]) -> dict:
    """플레이가 끝난 뒤 리포트용 코멘트와 총평을 쓴다.

    results:    {단계번호: "correct" | "failed" | "not_reached"}  ← 통과 여부는 서버가 이미 정했다.
    transcript: 전체 대화 [{"stage", "role", "name", "text"}]

    반환: {"summary": "총평 2~3문장",
           "comments": {"c1": "이 항목에 대한 피드백 1~2문장", ...}}   # scenario["evaluation"] 의 id 기준
    통과/실패를 바꾸는 권한은 없다. 이용자의 실제 발언을 근거로 칭찬·보완점을 쓴다.
    실패 시 {"summary": "", "comments": {}} (서버가 빈 칸으로 표시)
    """
    if _api_key():
        generated = gemini.evaluate(scenario, results, transcript)
        if generated:
            return generated
    # 키 없음·API 장애·잘못된 근거 인용이면 읽을 수 있는 기본 피드백 유지.
    comments = {}
    for ev in scenario["evaluation"]:
        r = results.get(ev["stage"])
        if r == "correct":
            comments[ev["id"]] = "서버의 행동 기준이 충족되었습니다. 항목별 발언 근거를 확인해 보세요."
        elif r == "failed":
            comments[ev["id"]] = "시도 횟수 또는 위험도 한도에 도달했습니다. 행동 기준을 확인하고 다시 연습해 보세요."
        else:
            comments[ev["id"]] = "플레이가 먼저 종료되어 이 단계는 평가하지 않았습니다."
    passed = sum(r == "correct" for r in results.values())
    return {
        "summary": f"{len(results)}단계 중 {passed}단계가 규칙 기반 판정을 통과했습니다. 키워드 일치에 따른 연습 기록이며 실제 안전 역량을 인증하지 않습니다.",
        "comments": comments,
        "feedback_source": "basic",
        "model": "mock" if not _api_key() else os.getenv("LLM_MODEL_SMART", "gemini-3.1-flash-lite"),
        "reason": "mock" if not _api_key() else "fallback",
    }
