"""시나리오에 정의한 관찰 가능한 행동만 근거로 인정한다.

정규식은 의미 이해를 대체하지 않는다. 미등록 표현은 미확인으로 남기고,
AI의 correct 제안만으로 근거를 만들어 내지 않는다.
"""
import re


NOT_ACTION = re.compile(r"라고하면|라고말하면|안할|안하겠|하지않(?!고|은채)|하지말(?!고)")
QUESTION_END = re.compile(r"(?:까|되나요|괜찮나요|어떻게돼|어떡해|어때|[아어해여]도(?:돼|되나))요?$")


# 같은 대상을 가리키는 여러 표기를 하나로 통일한다. 시나리오 패턴은 대표 표기만 쓰면 된다.
# 띄어쓰기를 지운 문장에 적용하므로, 다른 낱말 속에 우연히 섞인 경우는 예외로 둔다.
SYNONYMS = [
    # 엘레베이터·엘리베이타·엘베·승강기·리프트
    (re.compile(r"엘[리레래]베이?[터타]|엘베이[터타]|엘베|승강기|리프트|elevator"), "엘리베이터"),
    # 쌤·샘·선생·담임·교사 ('학교사람' 속 교사, '샘물' 속 샘은 제외)
    (re.compile(r"담임(?:선생님?|쌤|샘)?|선생님?|쌤|샘(?!물)|(?<!학)교사"), "선생님"),
    # 화재벨·소방벨·경보기·화재경보기·비상 버튼·비상밸
    (re.compile(r"화재경보기?|경보(?:기|벨|버튼)?|화재벨|소방벨|비상밸|비상버튼|화재버튼"), "비상벨"),
    # 화재다·화재야·화재 발생·불이다
    (re.compile(r"화재(?:다|야|발생|났)|불이다"), "불이야"),
    # 일일구·소방서
    (re.compile(r"일일구|소방서"), "119"),
    # 테이블·책걸상
    (re.compile(r"책걸상|테이블"), "책상"),
    # 손수건·타올·타월 ('불이 타올라' 속 타올은 제외)
    (re.compile(r"손수건|타올(?![라랐])|타월"), "수건"),
    # 문고리
    (re.compile(r"문고리"), "손잡이"),
    # 넓은 장소·넓은 데·넓은 공간 (시나리오에서 '운동장'과 함께 정답으로 인정)
    (re.compile(r"넓은(?:장소|데|공간)"), "넓은곳"),
    # 랩탑·컴퓨터
    (re.compile(r"랩탑|컴퓨터"), "노트북"),
]


def normalize(text: str) -> str:
    for pattern, word in SYNONYMS:
        text = pattern.sub(word, text)
    return text


def compact(text: str) -> str:
    return normalize(re.sub(r"[\s,.!?。！？]", "", text.lower()))


def action_text(text: str) -> str:
    """실행 의사로 볼 수 있는 문장만 남긴다.

    질문(물음표로 끝나는 문장)·가정·부정 문장은 그 문장만 뺀다.
    예) "불 난 거 아냐? 사람들한테 빨리 알리자" → "사람들한테빨리알리자"
    메시지 전체를 버리면 실제 사람들이 쓰는 "질문 + 행동" 문장이 인정되지 않는다.
    남은 문장은 합쳐서 검사하므로 "7층이에요. 탕비실이요." 처럼 나뉜 행동도 인정된다.
    """
    kept = []
    for sentence in re.split(r"(?<=[?？!！.。\n])", text):
        if sentence.strip().endswith(("?", "？")):
            continue
        value = compact(sentence)
        if value and not QUESTION_END.search(value) and not NOT_ACTION.search(value):
            kept.append(value)
    return "".join(kept)


def observe(stage: dict, text: str) -> list[str]:
    value = action_text(text)
    if not value:
        return []
    found = []
    for criterion in stage.get("rubric", []):
        if any(re.search(p, value) for p in criterion.get("exclude", [])):
            continue
        direct = all(any(_affirmed(p, value) for p in group) for group in criterion["patterns"])
        concept = criterion.get('concept')
        # 이미 시작한 세션의 기존 시나리오 사본도 같은 의미의 표현을 인정한다.
        legacy_lift = criterion.get('id') in ('stop_lift', 'no_lift') and '엘리베이터' in criterion.get('label', '')
        alternative = (concept == 'avoid_elevator' or legacy_lift) and _elevator_alternative(stage, value)
        if direct or alternative:
            found.append(criterion["id"])
    return found


def _affirmed(pattern, value):
    for match in re.finditer(pattern, value):
        # '막지 마', '보호하지 않아도 돼'를 '막기/보호하기'로 인정하지 않는다.
        # '타지 마'처럼 금지 자체가 행동 기준인 패턴은 이미 부정 표현까지 매칭하므로 유지된다.
        if re.match(r'^[가-힣]{0,3}(지(?:마|말|않)|필요없|안할|안해|안하|못해)', value[match.end():]):
            continue
        return True
    return False


def _elevator_alternative(stage, value):
    return ('계단' in stage.get('correct_action', '')
            and _affirmed(r'엘리베이터.{0,6}(위험|대신|말고)', value)
            and _affirmed(r'계단.{0,8}(가자|가요|갈게|갑시다|이동|내려|대피|이용|선택)', value)
            and not dangerous(stage, value))


def dangerous(stage: dict, text: str) -> bool:
    return danger_outcome(stage, text) is not None


def danger_outcome(stage: dict, text: str) -> dict | None:
    default = stage.get('if_wrong', {})
    outcomes = [*default.get('events', []), {**default, 'patterns': stage.get('danger_patterns', [])}]
    # 문장별로 검사해 부정/질문/나중의 조건부 행동과 현재 실행을 구분한다.
    # 한 문장의 안전한 조건이 뒤 문장의 위험 행동까지 숨기면 안 된다.
    for sentence in re.split(r"(?<=[?？!！.。\n])", text):
        value = action_text(sentence)
        if not value:
            continue
        if stage.get('danger_defer_patterns') and any(
                re.search(p, value) for p in stage['danger_defer_patterns']):
            continue
        for outcome in outcomes:
            if any(re.search(p, value) for p in outcome.get('exclude', [])):
                continue
            if _matches_danger(outcome['patterns'], value):
                return outcome
    return None


def _matches_danger(patterns, value):
    for pattern in patterns:
        for match in re.finditer(pattern, value):
            suffix = value[match.end():]
            prefix = value[:match.start()]
            if re.search(r'(안|못)(나가|나갈|들어가|들어갈|타|탈|이용|열|밀|뛰|달|잡|쥐)', match.group()):
                continue
            if re.search(r'(?:안|절대안|절대로안)$', prefix):
                continue
            if re.match(r'(들어가지마|들어가면안|가지마|말자|면안|면위험|는건위험|는것은위험|지마|지말|지않|지못)', suffix):
                continue
            if re.match(r'[가-힣]{0,4}(지(?:는|도)?(?:마|말|않|못)|면안|면위험)', suffix):
                continue
            return True
    return False
