"""재난·안전 롤플레잉 API 서버.

이 파일은 '요청을 받고 응답 형식을 맞추는' 일만 한다.
진행 규칙은 harness.py, AI 호출은 ai.py, 입력 필터는 safety.py 에 있다.
"""
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import cms, harness, ai, rules
import os
from .schemas import ActionScene, MessageRequest, Report, ScenarioSummary, StartRequest, Turn

app = FastAPI(title="SafeTurn 재난·안전 롤플레잉 API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite 개발 서버
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(cms.router)   # 운영자 CMS: /admin/...


@app.get('/health')
def health():
    return {'status': 'ok', 'mode': 'gemini' if ai._api_key() else 'mock',
            'model': os.getenv('LLM_MODEL_FAST', 'gemini-3.1-flash-lite') if ai._api_key() else 'offline',
            'admin_configured': bool(os.getenv('ADMIN_TOKEN', '').strip())}


def _published(sc: dict) -> bool:
    return sc.get("status", "published") == "published"


def _get(session_id: str) -> harness.Session:
    s = harness.get_session(session_id)   # 메모리 → 없으면 DB (새로고침·서버 재시작 후에도 이어짐)
    if not s:
        raise HTTPException(404, "플레이 기록을 찾을 수 없거나 만료되었습니다. (24시간 동안 활동이 없으면 만료)")
    return s


def _turn(s: harness.Session, messages: list[dict], action_scene: ActionScene | None = None) -> Turn:
    st = harness.current_stage(s)
    speaker = harness.character(s, st["character_id"])
    speaker_image = speaker.get("image")
    if not speaker_image:
        # 이미지가 없었던 이전 세션에도 같은 캐릭터의 새 이미지를 표시한다.
        sc = harness.SCENARIOS.get(s.scenario["id"], {})
        speaker_image = next((c.get("image") for c in sc.get("characters", [])
                              if c["id"] == speaker["id"] and c["name"] == speaker["name"]), None)
    ending_image = s.scenario.get("cleared_image") if s.status == "cleared" else None
    confirmed, partial = harness.partial_progress(s, st)
    return Turn(
        session_id=s.id, messages=messages,
        stage=st["stage"], stage_title=st["title"], total_stages=len(s.scenario["stages"]),
        situation=partial.get('situation') or st["situation"], speaker=speaker["name"], speaker_image=speaker_image,
        risk=s.risk, max_risk=s.scenario["max_risk"], image=ending_image or partial.get('image') or st.get("image"), status=s.status,
        image_includes_speaker=bool(ending_image or partial.get('image') or st.get("image_includes_speaker")), action_scene=action_scene,
        confirmed_actions=confirmed,
        conditions=harness.public_conditions(s), stage_mistakes=s.turns_in_stage,
        attempts_left=max(0, harness.LEGACY_ATTEMPTS_PER_STAGE - s.turns_in_stage) if s.status == "playing" else 0,
    )


def _action_scene(s: harness.Session, stage: dict, messages: list[dict]) -> ActionScene | None:
    number = stage["stage"]
    if not stage.get("action_image") or s.stage_results.get(number) != "correct":
        return None
    # 행동을 보여주는 동안 이용자 발언과 상대의 반응만 먼저 표시한다.
    message_count = 0
    for message in messages:
        if message["role"] not in ("user", "character"):
            break
        message_count += 1
    evidence = s.evidence.get(number, {})
    for option in stage.get("action_alternatives", []):
        action = rules.action_text(evidence.get(option["evidence"], ""))
        if any(keyword.strip() and rules.compact(keyword) in action for keyword in option["contains"]):
            return ActionScene(image=option["image"], description=option["description"], message_count=message_count)
    return ActionScene(image=stage["action_image"], description=stage.get("action_description") or stage["correct_action"],
                       message_count=message_count)


@app.get("/scenarios", response_model=list[ScenarioSummary])
def list_scenarios():
    return [harness.public_scenario(sc) for sc in harness.SCENARIOS.values() if _published(sc)]


@app.get("/scenarios/{scenario_id}", response_model=ScenarioSummary)
def get_scenario(scenario_id: str, x_admin_token: str | None = Header(default=None)):
    sc = harness.SCENARIOS.get(scenario_id)
    if not sc or not (_published(sc) or cms.admin_token_ok(x_admin_token)):
        raise HTTPException(404, "시나리오를 찾을 수 없습니다.")
    return harness.public_scenario(sc)


@app.post("/sessions", response_model=Turn)
def start_session(req: StartRequest, x_admin_token: str | None = Header(default=None)):
    sc = harness.SCENARIOS.get(req.scenario_id)
    # 작성 중(draft) 시나리오는 운영자 미리 플레이로만 시작할 수 있다.
    if not sc or not (_published(sc) or cms.admin_token_ok(x_admin_token)):
        raise HTTPException(404, "시나리오를 찾을 수 없습니다.")
    s, messages = harness.create_session(req.scenario_id)
    return _turn(s, messages)


@app.get("/sessions/{session_id}", response_model=Turn)
def resume_session(session_id: str):
    """이어하기: 지금까지의 대화 전체와 현재 상태를 돌려준다."""
    with harness.session_guard(session_id):
        s = _get(session_id)
        return _turn(s, [{"role": m["role"], "name": m["name"], "text": m["text"]} for m in s.transcript])


@app.post("/sessions/{session_id}/messages", response_model=Turn)
def send_message(session_id: str, req: MessageRequest):
    with harness.session_guard(session_id):
        s = _get(session_id)
        previous = s.processed_requests.get(req.request_id) if req.request_id else None
        if previous:
            if previous['text'] != req.text:
                raise HTTPException(409, '같은 요청 번호에 다른 내용을 보낼 수 없습니다.')
            return Turn(**previous['response'])
        if s.status != "playing":
            raise HTTPException(400, "이미 끝난 플레이입니다.")
        stage = harness.current_stage(s)
        if req.expected_stage is not None and req.expected_stage != stage['stage']:
            raise HTTPException(409, '장면이 이미 변경되어 최신 대화를 불러옵니다. 내용을 확인한 뒤 다시 입력하세요.')
        messages = harness.handle_message(s, req.text, persist_result=False)
        advanced = s.status == "cleared" or harness.current_stage(s)["stage"] != stage["stage"]
        action_scene = _action_scene(s, stage, messages) if advanced else None
        if action_scene is None:
            for index, message in enumerate(messages, start=1):
                if image := message.get('outcome_image'):
                    action_scene = ActionScene(image=image, description=message['text'], message_count=index,
                                               kind=message.get('scene_kind', 'outcome'))
                    break
        response = _turn(s, messages, action_scene)
        if req.request_id:
            s.processed_requests[req.request_id] = {'text': req.text, 'response': response.model_dump()}
            while len(s.processed_requests) > 32:
                s.processed_requests.pop(next(iter(s.processed_requests)))
        harness.persist(s)
        return response


@app.get("/sessions/{session_id}/report", response_model=Report)
def get_report(session_id: str):
    with harness.session_guard(session_id):
        s = _get(session_id)
        if s.status == "playing":
            raise HTTPException(400, "플레이가 아직 끝나지 않았습니다.")
        return harness.build_report(s)
