"""시나리오에 정의한 관찰 가능한 행동만 근거로 인정한다.

정규식은 의미 이해를 대체하지 않는다. 미등록 표현은 미확인으로 남기고,
AI의 correct 제안만으로 근거를 만들어 내지 않는다.
"""
import re


NOT_ACTION_WORDS = ("라고하면", "라고말하면", "안할", "안하겠", "하지않", "하지말")


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
        if value and not any(word in value for word in NOT_ACTION_WORDS):
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
    value = action_text(text)
    for pattern in stage.get("danger_patterns", []):
        for match in re.finditer(pattern, value):
            suffix = value[match.end():]
            if re.match(r'(들어가지마|들어가면안|가지마|말자)', suffix):
                continue
            return True
    return False
