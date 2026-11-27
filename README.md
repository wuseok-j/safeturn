# 세이프턴 SafeTurn — 재난·안전 대응 롤플레잉

세이프턴은 대화 한 턴과 판단 하나가 다음 상황에 영향을 주는 재난 대응 연습 서비스입니다.

> **문제:** 안전교육은 대부분 영상 시청이라, 실제 상황에서 판단해 보는 연습을 할 수 없다.
> **해결:** 화재·지진 등 상황 속 인물과 채팅하며 직접 판단하고, 행동별 피드백을 받는다.

운영자(교사·기업 안전 담당자)가 재난 시나리오를 올리고, 이용자(학생·직원)가 시나리오 속 인물과 채팅하며 판단해 본 뒤, 끝나면 행동별 평가 리포트를 받는 생성형 AI 서비스.

**최종 로컬 실행:** `start-local.cmd` → http://127.0.0.1:8000 . 인터넷 없이 시연할 때는 `.\start-local.cmd offline`으로 실행한다. 상세 설정·시연 순서·완주 예시는 [SUBMISSION.txt](SUBMISSION.txt)를 따른다. 제출 검증은 `backend\.venv\Scripts\python.exe -X utf8 tools/verify_release.py --ui`, 비밀값을 제외한 ZIP 생성은 같은 Python으로 `tools/package_submission.py`를 실행한다.

## 구조

```
[이용자 웹] ─┐
             ├─> [백엔드 API] ─> [하네스] ─> [LLM API]
[운영자 CMS] ┘        │             │
                    [DB] <──────────┘
```

**하네스 원칙:** 진행 상태(단계·위험도·시도 횟수)는 모델이 아니라 **서버가 쥔다.**
모델은 "캐릭터 대사"와 "행동 판정 제안"만 만들고, 단계 이동은 서버가 시나리오 규칙으로 결정한다.

## 폴더 구조

| 위치 | 내용 |
|---|---|
| `backend/app/harness.py` | 하네스: 단계 진행·위험도·판정 검증 (핵심) |
| `backend/app/ai.py` | Gemini 행동 판정·종료 피드백 (키 없음·생성 실패 시 기본 응답) |
| `backend/app/safety.py` | 인젝션·부적절 표현 1차 필터 |
| `backend/app/main.py`, `schemas.py` | API 서버, 요청·응답 형식 |
| `backend/play_test.py` | 시나리오 자동 플레이 테스트 |
| `data/scenarios/` | 시나리오 JSON + [작성 가이드](data/scenarios/README.md) |
| `docs/api-spec.md` | 프론트 ↔ 백엔드 API 명세 |
| `docs/research/` | 유사 서비스·시장 조사 |
| `docs/tasks/` | **팀원별 할 일** |
| `frontend/` | React 웹 프로토타입 (목록 → 플레이 → 리포트) |
| `docs/decision-design.md` | 다중 행동 근거·선택 상태·판단 복기 설계와 한계 |

## 선택이 남는 플레이

2026-11-25: 화재·학교 지진 두 시나리오, 원본 SVG 장면 10개, PC 2단/모바일 접기 화면, 실제 발언을 인용하는 AI 리포트를 포함한다. 위험도는 서버에 등록된 위험 행동이 확인될 때만 증가한다. 미등록 위험 표현은 추가 검수 대상이다.

목록 → 임무 브리핑 → 채팅 → 판단 복기로 진행한다. 서버가 필수 행동을 항목별로 확인하며, 여러 발언에 걸쳐 근거를 모을 수 있다. 단계에서 도움을 받았는지에 따라 다음 장면이 바뀐다. 리포트는 실제 발언, 위험도 변화, 충족·미확인 행동과 출처를 보여준다. 건물 밖 도착 여부와 행동 충족도는 별개다.

`backend/decision_test.py`에서 AI의 잘못된 성공 제안, 부분 행동, 도움 경로, 장애 시 기회 보존 등을 API 키 없이 검증한다. 표현 판정은 제한된 패턴 기반이며 의미 이해나 안전 역량 인증을 대체하지 않는다.

최종 안정화에는 요청 id 기반 재전송 중복 방지, 세션별 직렬화, 메모리 세션의 만료 확인, 부정문·질문 판정 보강이 포함된다. 총평과 점수는 서버 기록에서 만들고, AI는 단계별 참고 코멘트를 제공한다. 로컬 단일 프로세스 사용 범위다.

### 인물과 현장 연출

브리핑의 인물 카드는 캐릭터 초상화·관계·소개·첫인상 대사를 보여준다. 운영자 CMS의 캐릭터 항목에서 소개·대사·이미지 경로를 편집할 수 있다.

기본 세 시나리오는 단계별 연기·지진 진동/먼지·승강기 충격과 위험도에 따른 붉은 가장자리 효과를 제공한다. 플레이 상단에서 화면 효과와 환경음을 각각 켜고 끌 수 있다. 환경음은 기본 켜짐이며 시작·이어하기 클릭 시 Web Audio를 준비한다. 사용자가 끄면 다음 플레이에서도 유지한다. 화재 경보/타는 소리, 지진 진동/물체 떨림/대피 발걸음, 승강기 충격/인터폰 잡음/환기음 등 15개 단계별 음향을 합성한다. 다른 탭으로 이동하거나 플레이를 나가면 멈추고, 완료 시 현장음이 종료된다. OS의 동작 줄이기 설정에서는 흔들림과 연기 애니메이션을 실행하지 않는다. 연출은 서버의 단계·위험도를 읽기만 하며 판정에 관여하지 않는다.

빌드 후 `backend/.venv/Scripts/python.exe -X utf8 backend/immersion_ui_check.py`로 PC·모바일·작은 높이의 인물 카드/효과/오디오 수명/입력창 배치를 검사할 수 있다. 실제 Gemini는 호출하지 않는다.

### 개발 검증

backend에서 `pip install -r requirements-dev.txt`로 화면 검증 도구를 설치한다. `content_test.py`는 두 시나리오의 CMS 검사·행동 기준·실제 장면 파일을, `report_ai_test.py`는 피드백의 인용·실패 복구·점수 불변성을 검증한다. 모두 API 비용 없이 실행한다.

프론트에서 `npm.cmd run build` 후 backend에서 `python -X utf8 ui_check.py`를 실행하면 설치된 Microsoft Edge의 헤드리스 모드로 PC/모바일 완주·새로고침 이어하기·전송 오류 복원·좁은 화면 높이를 확인한다. 임시 DB와 mock AI를 사용하고 결과 이미지는 Git 제외된 `.qa/`에 저장한다. 로컬 18765 포트가 비어 있어야 한다.

`python -X utf8 final_rehearsal.py`는 **실제 API 비용이 발생**하는 두 시나리오 리허설이다. `--report-only`를 붙이면 플레이는 mock, 종료 피드백만 실제 Gemini로 확인한다. 장면 SVG 재생성은 루트에서 `python tools/build_scene_assets.py`로 실행한다.

## 처음 받았을 때

```bash
git clone https://github.com/wuseok-j/MIA-Mock-Interview-Assistant-.git
cd MIA-Mock-Interview-Assistant-
cp .env.example .env          # .env 의 GEMINI_API_KEY 에 키 입력 (Windows: copy .env.example .env)

cd backend
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> **Windows에서 `.venv\Scripts\activate` 가 빨간 오류("스크립트를 실행할 수 없으므로…")로 막히면**
> PowerShell 기본 보안 설정 때문이다. 둘 중 하나로 해결한다.
> - **한 번만 설정 (추천):** `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 입력 → `Y`. 내 계정에서만 적용되고 관리자 권한은 필요 없다. 이후 activate 가 정상 동작한다.
> - **활성화 없이 실행:** 명령 앞에 `.venv\Scripts\python -m` 을 붙인다.
>   예) `.venv\Scripts\python -m pip install -r requirements.txt`, `.venv\Scripts\python -m uvicorn app.main:app --reload`

### 하네스 동작 확인 (API 키 없어도 됨)
```bash
python play_test.py
```
모범 플레이 / 인젝션 시도 / 위험한 플레이 3가지가 자동으로 돌고 `✅` 가 나오면 성공.

### 서버 실행
```bash
uvicorn app.main:app --reload
```
http://localhost:8000/docs 에서 `POST /sessions` → `POST /sessions/{id}/messages` 순서로 직접 플레이할 수 있다.

### 웹 화면으로 플레이
서버를 켜 둔 채로 다른 터미널에서:
```bash
cd frontend
npm install      # 처음 한 번만
npm run dev
```
http://localhost:5173 → 시나리오 선택 → 채팅 플레이 → 리포트. (자세한 내용은 `frontend/README.md`)

### 실제 AI 첫 호출 확인
```bash
python first_run.py
```
캐릭터 대사 1개와 토큰 사용량·예상 비용이 출력되면 성공.

Gemini 설정은 루트 `.env`의 `LLM_PROVIDER=gemini`, `GEMINI_API_KEY`, `LLM_MODEL_FAST`를 사용한다. 연결 확인 모델은 `gemini-3.1-flash-lite`다. 키 없이 실행하거나 `LLM_PROVIDER=mock`이면 오프라인 판정을 사용한다. `LLM_API_KEY`는 더 이상 사용하지 않는다. 종료 피드백은 `LLM_MODEL_SMART`로 생성하며 실패 시 기본 문구를 유지한다.

가격 변수가 0이면 비용 미설정이다. 무료라는 뜻이 아니며, `first_run.py`는 가격을 설정했을 때만 예상 비용을 계산한다. 사용 가능 모델 조회는 `python model_check.py`로 실행한다.

### 플레이 기록 저장 (DB)
- 플레이는 매 턴 `backend/mia.db`(SQLite, 깃에 안 올라감)에 저장된다. 따로 설치할 것은 없다.
- 브라우저를 새로고침하거나 서버를 다시 켜도, 시나리오 목록 화면의 **이어하기**로 계속할 수 있다 (24시간 동안 활동이 없으면 만료).
- AI 호출마다 토큰·응답 시간이 기록되어 운영자 화면 이용 현황에 **1판당 토큰·비용**이 나온다 (`.env` 의 `PRICE_*` 설정 시).
- 기록을 처음부터 다시 시작하려면 서버를 끄고 `backend/mia.db` 파일을 지우면 된다.
- 테스트: `cd backend` → `python -X utf8 db_test.py` (서버 재시작을 흉내 내서 확인, 임시 DB 사용)

### 운영자 CMS (시나리오 만들기·고치기·공개)
1. 루트 `.env` 에 `ADMIN_TOKEN=원하는긴비밀번호` 를 넣고 서버를 다시 켠다. (비워 두면 운영자 기능이 꺼진다)
2. 웹 화면 오른쪽 위 **운영자** → 토큰 입력
3. 시나리오 목록·이용 현황 확인 / **새 시나리오**(빈 뼈대 또는 기존 시나리오 복제) / **편집** / **미리 플레이** / **공개하기**

- 새 시나리오는 '작성 중'으로 만들어져 이용자에게 보이지 않는다. 저장할 때 서버가 검사하고(`backend/app/scenario_check.py`), 오류가 0개일 때만 공개할 수 있다.
- 저장하면 `data/scenarios/<id>.json` 파일이 바뀐다. 팀에 공유하려면 그 파일을 평소처럼 브랜치 → PR로 올린다.
- 테스트: `cd backend` → `python -X utf8 cms_test.py`

## 협업 규칙

> 처음이라면 **[협업 가이드](docs/협업가이드.md)** 부터 — GitHub Desktop으로 브랜치 → PR 올리는 법을 순서대로 정리했다.

1. `main` 브랜치에는 직접 push 하지 않는다. 기능별 브랜치에서 작업 후 PR로 합친다.
   - 브랜치 이름: `feat/채팅화면`, `content/지진시나리오`, `docs/서비스조사` 처럼 `종류/내용`
2. **PR 승인·머지는 장우석만 한다.** (`main` 보호 규칙 + `.github/CODEOWNERS`) PR을 올리면 단톡에 링크를 남긴다.
3. **API 키 등 비밀 정보는 절대 커밋하지 않는다. AI 채팅창에도 붙여넣지 않는다.** 실수로 올렸다면 즉시 팀에 알리고 키를 폐기·재발급한다.
4. 프론트·백엔드 형식은 `docs/api-spec.md`, 시나리오 형식은 `data/scenarios/README.md` 가 기준이다. 바꿀 때는 문서부터 수정하고 공유한다.
5. 깃은 GitHub Desktop 사용. 충돌이 나면 혼자 해결하지 말고 장우석에게.
