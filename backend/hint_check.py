"""재촉 대사가 정답을 흘리는지 실제 AI로 확인 (작업 2, 담당: 김채희) — ⚠️ 실제 API 호출, 소액 비용.

실행: python -X utf8 hint_check.py [반복 횟수, 기본 2]

'행동을 일부만 한' 상황을 만들어 AI(박지훈)의 재촉 대사를 모은다.
남은 행동의 수단·방법을 짐작하게 하는 단어가 대사에 있으면 [흘림?] 으로 표시한다.
자동 표시는 참고용이다. 최종 판단은 사람이 대사를 읽고 한다.
진행 판정은 서버가 하므로 이 스크립트는 '대사'만 본다 (서버 진행 규칙 확인은 decision_test.py).
"""
import sys
import time

from app import ai, harness

if not ai._api_key():
    sys.exit("❌ GEMINI_API_KEY 가 없어서 가짜 AI로 동작합니다. .env 를 확인하세요.")

SC = harness.SCENARIOS["fire_office"]

ALERT_WORDS = ["비상벨", "119", "신고", "발신기", "빨간", "상자", "버튼", "누르", "눌러", "전화", "벨", "경보"]

# (단계 번호, 이미 확인된 rubric id, 이용자 입력, 남은 행동을 드러내는 단어[, 앞선 대화])
# 앞선 대화가 있으면 '같은 단계에서 여러 번 시도한' 상황 — 실제 플레이에서 흘림이 가장 심했던 경우
CASES = [
    (1, ["warn"], "다른 사람들한테 불났다고 알리자",
     ALERT_WORDS),
    (1, ["alert"], "내가 119에 신고할게",
     ["알리", "알려", "외치", "소리", "불이야", "사람들", "다들"]),
    (2, ["stairs"], "난 계단으로 갈게",
     ["타지 마", "타지마", "말려", "멈출", "멈춰", "정전", "갇히", "연기가 들어"]),
    (2, ["stop_lift"], "엘리베이터 타지 마",
     ["계단", "걸어", "비상구"]),
    (3, ["low"], "자세 낮춰서 내려가자",
     ["입", "코", "수건", "소매", "막", "가리", "옷"]),
    (3, ["cover"], "소매로 입 막아",
     ["낮", "숙", "엎드", "기어", "자세", "허리", "서서"]),
    # 반복 시도: 실제 플레이(11/19)에서 "복도에 있는 빨간 상자"가 나온 흐름
    (1, ["warn"], "사람들에게 알리자", ALERT_WORDS,
     [("user", "일단 사람들에게 알리고 대피하자"),
      ("character", "그래, 다들 대피해야지! 근데 이거 우리만 알면 되는 거야? 아직 아무도 안 오는데?")]),
    (3, ["low"], "자세 낮추라니까", ["입", "코", "수건", "소매", "막", "가리", "옷"],
     [("user", "자세 낮춰서 내려가자"),
      ("character", "그래, 자세 낮추니까 좀 낫네! 근데 연기가 너무 매워서 숨 쉬기가 힘든데 어떡하지?")]),
    # 아무것도 확인 안 됨 + 엉뚱한 행동: 실제 플레이에서 "다른 사람들한테 알려야 하는 거 아냐?"가 나온 흐름
    (1, [], "일단 콘센트부터 빼자", ["알리", "알려", "외치", "불이야", "사람들", "다들"] + ALERT_WORDS),
]


def context(stage_no: int, done: list[str]) -> dict:
    st = next(s for s in SC["stages"] if s["stage"] == stage_no)
    rubric = st.get("rubric", [])
    story = [f'{p["stage"]}단계 「{p["title"]}」: 이용자가 직접 해냄' for p in SC["stages"] if p["stage"] < stage_no]
    return {
        **st,
        "world_state": {},
        "world_facts": list(SC.get("role_doc", {}).get("world_facts", [])) + list(st.get("facts", [])),
        "confirmed_actions": [i["label"] for i in rubric if i["id"] in done],
        "missing_actions": [i["label"] for i in rubric if i["id"] not in done],
        "story_so_far": story,
    }


def main():
    repeat = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    leaks = total = 0
    for stage_no, done, text, leak_words, *prior in CASES:
        st = context(stage_no, done)
        ch = next(c for c in SC["characters"] if c["id"] == st["character_id"])
        history = [
            {"role": "narrator", "name": "상황", "text": st["situation"], "stage": stage_no},
            {"role": "character", "name": ch["name"], "text": st["opening_line"], "stage": stage_no},
        ]
        for role, said in (prior[0] if prior else []):
            history.append({"role": role, "name": "나" if role == "user" else ch["name"], "text": said, "stage": stage_no})
        history.append({"role": "user", "name": "나", "text": text, "stage": stage_no})
        print(f"\n[{stage_no}단계] 확인됨: {st['confirmed_actions']} / 남음: {st['missing_actions']}")
        print(f"  나: {text}")
        for _ in range(repeat):
            r = ai.judge_action(SC, st, ch, text, history)
            reply = r.get("reply", "")
            if r.get("reason") == "fallback":
                print("  ⚠️ AI 응답 실패 (429 등) — 잠시 후 다시 실행")
                continue
            hits = [w for w in leak_words if w in reply]
            total += 1
            leaks += bool(hits)
            mark = f"[흘림? {', '.join(hits)}]" if hits else "[OK]"
            print(f"  {ch['name']}: {reply}  ({r.get('verdict')}) {mark}")
            time.sleep(4.5)   # 무료 한도(분당 요청 수) 보호
    print(f"\n자동 표시 기준 흘림 의심: {leaks}/{total}")


if __name__ == "__main__":
    main()
