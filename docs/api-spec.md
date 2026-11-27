# API 명세 v0.4 (재난·안전 롤플레잉)

## 2026-11-25 화면 통합 추가

Report에 `feedback_source: "ai" | "basic"`을 추가한다. checks[].comment는 AI 생성 성공 시 해당 피드백을 사용하며, 장애·잘못된 인용·키 없음에는 기본 문구를 사용한다. summary·점수·상태·항목 충족 여부는 서버 기록으로 계산한다. 피드백은 메모리·DB 리포트 캐시에 저장한다.

## 2026-11-26 제출 안정화

- `GET /health`: status, mode(gemini/mock), model, admin_configured만 반환한다. 키·토큰은 반환하지 않으며 실제 외부 연결 성공을 보장하는 응답은 아니다.
- MessageRequest에 선택 필드 `request_id`(영문/숫자/밑줄/하이픈 8~64자), `expected_stage`(1~100)를 추가한다. text는 공백을 제거한 뒤 비어 있으면 422다.
- 같은 세션·request_id·text를 재전송하면 마지막 32개 요청 범위에서 저장된 Turn을 재사용한다. 응답 캐시는 세션 상태와 함께 DB에 저장된다. 동일 id의 다른 text 또는 이전 단계의 새 요청은 409다.
- 같은 세션의 입력·이어하기·리포트 요청은 단일 프로세스 안에서 직렬화한다. 여러 프로세스 간 분산 잠금이나 결제 수준의 exactly-once 보장을 구현한 것은 아니다.
- UI는 전송 중 중복 제출과 이동을 막고, 통신 실패 후 같은 내용을 재전송할 때 같은 id를 사용한다. 409에서는 최신 대화를 복원한다.
- 캐시된 진행 중 세션도 DB의 마지막 활동을 기준으로 만료를 확인한다. API 장애는 판단 기회·위험도에 영향을 주지 않으며 한도·네트워크·설정 문제를 구분해 안내한다.

위험도와 단계별 위험 행동 횟수는 서버의 `danger_patterns` 또는 `if_wrong.events[].patterns`에 등록된 위험 행동이 확인될 때만 증가한다. 미등록 표현은 인식하지 못할 수 있다.

Turn에 `situation: string`, `speaker: string`을 추가한다. 현재 선택 상태에 맞게 서버가 확정한 장면 설명과 발화자 이름이다. 시작·발언·이어하기 응답에 공통 포함된다. 왼쪽 장면 패널은 narrator 메시지를 추측해서 사용하지 않고 situation을 표시한다. 기존 필드는 유지한다.

장면 이미지는 `/scenes/{Turn.image}`에서 읽는다. `image_includes_speaker`가 참이면 장면 파일에 인물이 포함되어 있다. 인물이 포함되지 않은 장면이나 장면 파일 로드에 실패했을 때는 선택적 `speaker_image`를 이용할 수 있다. 대피한 세션에는 시나리오의 `cleared_image`를 현재 이미지로 내려준다.

정확한 행동이 확인되어 다음 단계나 대피 결말에 도달한 발언 응답에는 `action_scene: { image, description, message_count }`가 포함될 수 있다. 경로는 `/scenes/` 기준이고 설명은 해당 컷의 대체 텍스트다. 클라이언트는 행동 컷을 3초 동안 보여주며 `messages` 앞에서 `message_count`개만 먼저 표시한다. 이어서 행동 결과와 다음 단계의 새 대화 또는 결말을 화면에 표시한다. 시작과 이어하기는 현재 장면을 곧바로 표시한다.

기본 주소: `http://localhost:8000`
서버 실행 후 `http://localhost:8000/docs` 에서 직접 눌러 볼 수 있다.
형식을 바꿀 때는 이 문서와 `backend/app/schemas.py` 를 함께 수정하고 팀에 공유한다.

화면 흐름: **① 시나리오 목록 → ② 임무 브리핑 → ③ 채팅 플레이 → ④ 판단 복기**

---

## 1. 시나리오 목록 `GET /scenarios`

응답 (정답 정보는 포함되지 않음)
```json
[
  {
    "id": "fire_office",
    "title": "오피스 화재 대피",
    "summary": "근무 중인 7층 사무실 탕비실에서 연기가 난다. ...",
    "category": "화재",
    "thumbnail": "fire_office/thumbnail.png",
    "estimated_minutes": 7,
    "total_stages": 5,
    "characters": [{ "name": "박지훈", "role": "옆자리 동료 (입사 2년 차)", "image": "fire_office/jihoon.png" }]
  }
]
```

`GET /scenarios/{id}` 는 위 항목 하나를 돌려준다.

`characters`에는 브리핑용 `introduction`(인물 소개)와 `quote`(첫인상 대사)가 추가된다. 두 필드는 선택이며 이전 시나리오는 빈 문자열로 반환한다. `personality`, `speech_style` 같은 내부 프롬프트 설정은 공개하지 않는다. `image`는 `/scenes/` 기준 캐릭터 이미지 경로다.

## 2. 플레이 시작 `POST /sessions`

요청
```json
{ "scenario_id": "fire_office" }
```
응답 = **Turn** (아래 3번과 같은 형식). 첫 단계의 상황 설명과 캐릭터 첫 대사가 `messages` 에 들어 있다.

## 3. 이용자 발언 `POST /sessions/{session_id}/messages`

요청
```json
{ "text": "불이야! 비상벨 누르고 119에 신고할게요 (1~300자)" }
```
응답 – Turn
```json
{
  "session_id": "a1b2c3d4e5f6",
  "messages": [
    { "role": "user",      "name": "나",     "text": "불이야! ..." },
    { "role": "character", "name": "박지훈", "text": "헉, 진짜 불이야? ..." },
    { "role": "narrator",  "name": "상황",   "text": "비상벨이 울리고 ..." },
    { "role": "character", "name": "박지훈", "text": "엘리베이터 금방 온다! ..." }
  ],
  "stage": 2,
  "stage_title": "엘리베이터 앞",
  "total_stages": 5,
  "risk": 0,
  "max_risk": 6,
  "image": "fire_office/stage2_elevator.png",
  "status": "playing"
}
```

`messages` 는 **이번 턴에 새로 생긴 메시지만** 들어 있다. 화면은 기존 채팅 아래에 이어 붙이면 된다.

| role | 화면 표시 |
|---|---|
| `user` | 오른쪽 말풍선 (내 말) |
| `character` | 왼쪽 말풍선 + 캐릭터 이름·프로필 |
| `narrator` | 가운데 회색 상황 설명 (장면 이미지 옆) |
| `system` | 가운데 안내 박스 (안전 필터 안내, 종료 안내) |

| status | 화면 처리 |
|---|---|
| `playing` | 계속 입력 받기 |
| `cleared` / `failed` | 입력창 잠그고 '리포트 보기' 버튼 |

`risk / max_risk` 는 위험도 게이지로 보여 준다. `image` 가 바뀌면 장면 이미지를 바꾼다.

## 4. 리포트 `GET /sessions/{session_id}/report`

판정 설명은 서버 기록에서 생성한다. `checks[].reason`은 통과·미충족·위험도 한도 종료·미도달 이유이며 `reason_code`로 구분한다. `missing_actions`는 미확인 필수 행동, `action_reviews`는 발언별 `text`, `verdict`, `note`를 제공한다. 위험 행동과 행동 확인 부족을 구분하며, AI 코멘트는 화면에서 접힌 참고 의견으로 표시한다.

`assessment_version`은 판정 설명 버전이다. 이전에 저장된 리포트는 점수를 다시 매기지 않고 `assessment_note`로 이전 기준의 결과임을 알린다. 변경된 판정을 확인하려면 새 플레이를 시작한다.

```json
{
  "session_id": "a1b2c3d4e5f6",
  "scenario_title": "오피스 화재 대피",
  "status": "cleared",
  "risk": 2,
  "max_risk": 6,
  "passed": 4,
  "total": 5,
  "summary": "총평 2~3문장",
  "checks": [
    {
      "id": "c2",
      "stage": 2,
      "stage_title": "엘리베이터 앞",
      "criterion": "엘리베이터 대신 계단으로 대피했다",
      "result": "correct",
      "correct_action": "엘리베이터는 ... 비상계단으로 대피한다.",
      "comment": "이 항목 피드백"
    }
  ],
  "sources": [{ "name": "국민재난안전포털 – 화재 국민행동요령", "url": "https://www.safekorea.go.kr" }]
}
```
`result`: `correct`(통과) / `failed`(실패) / `not_reached`(도달 못 함)

## 오류 응답

| 코드 | 상황 | 화면 처리 |
|---|---|---|
| 400 | 끝난 플레이에 발언 / 안 끝난 플레이의 리포트 요청 | 안내 문구 |
| 404 | 없는 시나리오·세션 id | 시나리오 목록으로 이동 |
| 422 | 빈 입력, 300자 초과 | 입력창 아래 안내 문구 |
| 500·502 | 서버·AI 오류 | '다시 시도' 버튼 (입력한 문장 유지) |

## v0.3 추가 필드

- 리포트 checks에 `user_actions: list[str]`(해당 단계 실제 발언), `attempts: int`(필터 통과 후 판단 시도 수)를 추가한다. 차단 입력은 발언 근거에서 제외한다.
- 화면 흐름은 목록 → 브리핑 → 플레이 → 리포트다. 브리핑 확인 전에는 세션을 생성하지 않는다.
- 자동 판정의 근거를 표시하며 안전 역량 인증으로 표현하지 않는다.

## v0.4 선택의 영향과 근거 기반 복기

기존 필드는 유지하며 아래 필드를 추가한다.

| 응답 | 필드 | 의미 |
|---|---|---|
| ScenarioSummary | `briefing: {role, mission, focus}` | 공개 가능한 역할·목표·연습 역량. 판정 정규식은 비공개 |
| Turn | `conditions: string[]` | 앞선 단계의 확인·도움 이력 표시 |
| Turn | `attempts_left: int` | 기존 클라이언트용 값. 현재 단계의 확인된 위험 행동마다 3에서 1씩 감소하며 최솟값은 0, 종료 시 0. 단계 전환에는 사용하지 않음 |
| Turn | `stage_mistakes: int` | 현재 단계에서 서버가 확인한 위험 행동 횟수 |
| ActionScene | `kind: action \| outcome \| partial` | 안전 행동 확인 컷, 행동 결과 컷 또는 다음 판단으로 이어지는 중간 컷 |
| Turn | `confirmed_actions: string[]` | 진행 중인 현재 장면에서 이미 확인한 행동의 표시 이름 |
| CheckResult | `evidence: Evidence[]` | 행동 항목별 확인 여부·실제 발언·근거 출처 |
| Report | `timeline: Decision[]` | 평가된 입력별 판정·위험도 변화·결과 |
| Report | `conditions: string[]` | 최종 선택 이력 |
| Report | `review_points: string[]` | 미충족·미도달 단계 제목 |

`Evidence`: `{id, label, met: bool, quote: string, sources: [{name, url}]}`. 미확인 quote는 빈 문자열이다.

`Decision`: `{stage, title, action, verdict, risk_before, risk_after, outcome}`. verdict는 기존 correct/wrong/unclear다. 입력 차단과 AI 장애는 타임라인과 판단 횟수에서 제외한다.

여러 발언에서 확인한 행동을 단계별로 누적한다. 위험 행동이 확인되면 그 단계의 근거를 초기화하고, 결과를 `messages`와 리포트의 `timeline`에 남긴다. 누적 위험도가 한도 미만이면 같은 단계에서 이어가며 `max_risk`에 도달하면 실패로 종료한다. 질문과 잡담에는 횟수 제한을 적용하지 않는다. 모든 필수 행동이 확인되면 다음 단계로 진행한다.

현재는 JSON의 제한된 표현 패턴으로 근거를 검증한다. 미등록 표현·복잡한 부정·인용은 오판할 수 있다. 상세 한계와 시연 방법은 [설계 문서](decision-design.md)를 따른다.

## v0.5 운영자 CMS `/admin/...`

모든 요청에 헤더 `X-Admin-Token: <.env 의 ADMIN_TOKEN>` 필요. ADMIN_TOKEN 이 비어 있으면 503, 토큰이 틀리면 401.

| 요청 | 하는 일 |
|---|---|
| `GET /admin/scenarios` | 전체 시나리오(작성 중 포함) 요약: status, 검사 오류·경고 수, 이용 현황 `stats{plays, finished, cleared, avg_passed, stage_fail}` |
| `GET /admin/scenarios/{id}` | 시나리오 전체 JSON(정답·행동 기준 포함) + `errors`, `warnings`, `stats` |
| `POST /admin/scenarios` `{id, title, category}` | 1단계 뼈대로 새로 만들기 (status=draft). id 는 `^[a-z][a-z0-9_]{2,39}$`, 중복이면 409 |
| `POST /admin/scenarios/{id}/duplicate` `{id, title, category}` | 기존 시나리오 복제 (draft) |
| `PUT /admin/scenarios/{id}` 시나리오 JSON | 검사 후 저장. 오류가 있으면 422 `{detail: {message, errors, warnings}}` 이고 저장하지 않음. id 변경 불가 |
| `POST /admin/scenarios/{id}/status` `{status: "draft"|"published"}` | 공개/비공개. 공개는 검사 오류 0개일 때만 |
| `POST /admin/validate` 시나리오 JSON | 저장 없이 검사만 → `{errors, warnings}` |

이용자 API 변화: `GET /scenarios` 는 `status=published`(없으면 published 로 간주)만 보여 준다. 작성 중 시나리오는 `GET /scenarios/{id}`·`POST /sessions` 에 운영자 토큰 헤더가 있을 때만 열린다 (미리 플레이).

## v0.6 이어하기 `GET /sessions/{session_id}` (DB 저장)

응답 = **Turn**. 단, `messages` 에 **지금까지의 대화 전체**가 들어 있다 (화면은 받은 그대로 다시 그리면 된다).
- 세션은 매 턴 서버 DB(SQLite)에 저장되므로 새로고침·서버 재시작 후에도 이어진다.
- 마지막 활동 후 24시간이 지난 '진행 중' 세션은 만료 → 404. 끝난 세션은 리포트 조회가 계속 된다.
- `GET /sessions/{id}/report` 는 한 번 만든 리포트를 DB에 저장해 두고 다시 만들지 않는다.
- 운영자 `GET /admin/scenarios` 의 `stats` 는 DB 기준이며 `ai: {calls, input_tokens, output_tokens, avg_latency_ms, fallbacks, cost_per_play_krw}` 가 추가됐다 (`cost_per_play_krw` 는 `.env` 의 PRICE_* 를 설정했을 때만 값이 있음, 가짜 AI 호출은 제외).
