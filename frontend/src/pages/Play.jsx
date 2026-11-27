import { useEffect, useRef, useState } from "react";
import { activePlay, api } from "../api.js";
import { categoryEmoji, riskLevel } from "../ui.js";

const MAX_LEN = 300;
const ACTION_HOLD_MS = 3000;

function sceneAsset(path) {
  return `/scenes/${path.split("/").map(encodeURIComponent).join("/")}`;
}

async function prepareImage(path) {
  if (!path) return false;
  const image = new Image();
  image.src = sceneAsset(path);
  let timer;
  try {
    return await Promise.race([
      image.decode().then(() => true, () => false),
      new Promise(resolve => { timer = window.setTimeout(() => resolve(false), 900); }),
    ]);
  } finally {
    window.clearTimeout(timer);
  }
}

// adminToken 이 있으면 운영자 미리 플레이 (작성 중 시나리오도 시작 가능)
// resumeId 가 있으면 새로 시작하지 않고 서버 DB에 저장된 플레이를 이어서 한다
export default function Play({ scenario, onFinish, onExit, adminToken, resumeId, onBusyChange }) {
  const [turn, setTurn] = useState(null);        // 마지막으로 받은 Turn (상태값: 단계·위험도·status)
  const [messages, setMessages] = useState([]);  // 지금까지의 채팅 전체
  const [pending, setPending] = useState("");    // 서버 응답을 기다리는 내 말
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const [actionScene, setActionScene] = useState(null);
  const started = useRef(false);
  const chatBox = useRef(null);
  const scenePanel = useRef(null);
  const inFlight = useRef(false);
  const lastAttempt = useRef(null);

  useEffect(() => {
    onBusyChange?.(!!pending);
    return () => onBusyChange?.(false);
  }, [pending, onBusyChange]);

  // 화면이 열리면 플레이 시작 (개발 모드에서 두 번 실행되는 것을 막기 위해 ref 사용)
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    start();
  }, []);

  // 새 메시지가 오면 채팅창만 맨 아래로 스크롤
  useEffect(() => {
    const box = chatBox.current;
    if (box) box.scrollTo({ top: box.scrollHeight, behavior: "smooth" });
  }, [messages, pending, error]);

  async function start(fresh = false) {
    setError("");
    try {
      const t = resumeId && !fresh
        ? await api.resumeSession(resumeId)
        : await api.startSession(scenario.id, adminToken);
      setTurn(t);
      setMessages(t.messages);
      remember(t);
    } catch (e) {
      started.current = false;
      if (resumeId && !fresh) activePlay.clear();   // 만료·삭제된 플레이는 잊는다
      setError(e.message);
    }
  }

  // 진행 중이면 이 브라우저에 기억(이어하기용), 끝났으면 지운다. 운영자 미리 플레이는 기억하지 않는다.
  function remember(t) {
    if (adminToken) return;
    if (t.status === "playing") activePlay.save(t.session_id, scenario);
    else activePlay.clear();
  }

  async function send(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || inFlight.current || turn?.status !== "playing") return;
    inFlight.current = true;
    const attempt = lastAttempt.current?.text === text ? lastAttempt.current
      : { text, id: crypto.randomUUID(), stage: turn.stage };
    lastAttempt.current = attempt;
    setPending(text);
    setInput("");
    setError("");
    try {
      const t = await api.sendMessage(turn.session_id, text, attempt.id, attempt.stage);
      let remainingMessages = t.messages;
      if (t.image !== turn.image) void prepareImage(t.image);
      if (t.action_scene && await prepareImage(t.action_scene.image)) {
        const panel = scenePanel.current;
        const wasOpen = panel?.open;
        if (panel) panel.open = true;
        const shown = t.action_scene.message_count ?? 0;
        setMessages(prev => [...prev, ...t.messages.slice(0, shown)]);
        remainingMessages = t.messages.slice(shown);
        setActionScene(t.action_scene);
        await new Promise(resolve => window.setTimeout(resolve, ACTION_HOLD_MS));
        if (panel && !wasOpen && t.status !== "cleared") panel.open = false;
        setActionScene(null);
      }
      if (t.status === "cleared" && scenePanel.current) scenePanel.current.open = true;
      setTurn(t);
      setMessages(prev => [...prev, ...remainingMessages]);
      remember(t);
      lastAttempt.current = null;
    } catch (err) {
      setInput(text); // 실패하면 쓴 문장을 되돌려 놓는다
      setError(err.message);
      if (err.status === 409 || err.status === 400) {
        try {
          const latest = await api.resumeSession(turn.session_id);
          setTurn(latest); setMessages(latest.messages); remember(latest);
          lastAttempt.current = null;
        } catch { /* 기존 오류 안내 유지 */ }
      }
    } finally {
      setPending("");
      inFlight.current = false;
    }
  }

  const ended = turn && turn.status !== "playing";
  const cleared = turn?.status === "cleared";
  const sceneTitle = cleared ? "대피 완료" : turn?.stage_title;

  return (
    <main className="play">
      {/* 상단: 시나리오 제목, 단계 진행, 위험도 */}
      <div className="play-status">
        <div className="play-title">
          <button className="ghost" onClick={onExit} disabled={!!pending}>← 목록</button>
          <strong>{scenario.title}</strong>
        </div>
        {turn && (
          <div className="gauges">
            <StageDots current={turn.stage} total={turn.total_stages} status={turn.status} />
            <RiskGauge risk={turn.risk} max={turn.max_risk} />
          </div>
        )}
      </div>

      <div className="mission-strip">{scenario.briefing?.mission || "동료와 안전하게 대피하기"}
        {turn && <span>{ended ? "플레이 종료" : `행동 시도 기회 ${turn.attempts_left}회 · 질문·대화는 단계당 최대 6회`}</span>}
      </div>
      {!!turn?.conditions?.length && <div className="condition-trail" aria-label="이전 선택의 영향">{turn.conditions.map((label, i) => <span key={i}>{label}</span>)}</div>}
      <div className={`play-workspace ${!turn ? "is-loading" : ""}`}>
      {turn && (
        <details className={`scene-panel${actionScene || cleared ? " is-showing-cutaway" : ""}`} ref={scenePanel} open>
          <summary>현재 장면 · {sceneTitle}<span>펼치기 / 접기</span></summary>
          <div className="scene-content">
            <div className={`scene risk-${riskLevel(turn.risk, turn.max_risk)}`}>
              <SceneVisual category={scenario.category} turn={turn} action={actionScene} />
            </div>
            <div className="scene-stage">STAGE {turn.stage} / {turn.total_stages}</div>
            <h2 className="scene-heading">{sceneTitle}</h2>
            <p className="scene-description">{cleared ? "함께 안전한 장소에 도착했습니다." : actionScene?.description ?? turn.situation}</p>
            {!cleared && <p className="scene-guide">선택한 행동은 다음 상황에 남습니다. 결과에서 내 발언과 판단 근거를 확인할 수 있습니다.</p>}
          </div>
        </details>
      )}
      <section className="dialogue-panel" aria-label="대화 플레이">
      <div className="dialogue-heading"><strong>대화</strong><span>{turn?.speaker || "상황을 준비하고 있습니다"}</span></div>
      {/* 채팅 */}
      <div className="chat" ref={chatBox} role="log" aria-label="상황과 대화" aria-live="polite">
        {messages.map((m, i) => <Bubble key={i} m={m} />)}
        {pending && (!actionScene || !actionScene.message_count) && <Bubble m={{ role: "user", name: "나", text: pending }} dim />}
        {pending && <div className="typing">{actionScene ? "행동이 상황에 반영되고 있어요…" : "상대가 반응하는 중…"}</div>}
        {error && (
          <div className="error-box">
            {error} {!turn && (resumeId
              ? <button onClick={() => { started.current = true; start(true); }}>새로 시작</button>
              : <button onClick={() => start()}>다시 시도</button>)}
          </div>
        )}
      </div>

      {!turn && !error && <div className="loading-note" role="status">{resumeId ? "이전 대화를 불러오는 중…" : "현장 상황을 준비하는 중…"}</div>}

      {/* 입력창 또는 종료 배너 */}
      {ended ? (
        <div className={`end-banner ${turn.status}`}>
          <span>{turn.status === "cleared" ? "건물 밖 도착 · 판단을 복기하세요" : "대피 중단 · 판단을 복기하세요"}</span>
          <button className="primary" onClick={() => onFinish(turn.session_id)}>리포트 보기</button>
        </div>
      ) : (
        <form className="composer" onSubmit={send}>
          <input
            value={input}
            aria-label="내가 할 행동"
            aria-describedby="composer-help"
            onChange={(e) => setInput(e.target.value.slice(0, MAX_LEN))}
            onKeyDown={(e) => { if (e.key === 'Enter' && e.nativeEvent.isComposing) e.preventDefault(); }}
            placeholder={turn ? "행동을 말하거나, 궁금한 걸 물어보세요" : "준비 중…"}
            disabled={!turn || !!pending}
            autoFocus
          />
          <span className="count">{input.length}/{MAX_LEN}</span>
          <button className="primary" disabled={!turn || !!pending || !input.trim()}>보내기</button>
        </form>
      )}
      {!ended && <p id="composer-help" className="composer-help">행동은 구체적으로, 질문은 자유롭게. 응답 대기 중에는 중복 전송할 수 없습니다.</p>}
      </section>
      </div>
    </main>
  );
}

function SceneVisual({ category, turn, action }) {
  const frame = action ? {
    image: action.image, alt: action.description, caption: "행동 확인", kind: "action",
  } : {
    image: turn.image, alt: turn.status === "cleared" && turn.image_includes_speaker ? "안전하게 대피한 뒤 안도하며 웃는 인물들" : `${turn.stage_title} 장면`,
    portrait: turn.speaker_image, integrated: turn.image_includes_speaker,
    caption: turn.status === "cleared" ? "안전하게 대피했어요" : turn.speaker,
    kind: turn.status === "cleared" ? "cleared" : "stage",
  };
  frame.key = JSON.stringify(frame);
  const [layers, setLayers] = useState({ current: frame, previous: null });
  if (layers.current.key !== frame.key) setLayers({ current: frame, previous: layers.current });

  return (
    <>
      {layers.previous && <SceneFrame key={layers.previous.key} frame={layers.previous} category={category} previous />}
      <SceneFrame key={layers.current.key} frame={layers.current} category={category} />
    </>
  );
}

function SceneFrame({ frame, category, previous = false }) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [portraitFailed, setPortraitFailed] = useState(false);
  const hasImage = frame.image && !failed;
  const hasPortrait = frame.portrait && (!frame.integrated || !hasImage) && !portraitFailed;

  return (
    <div className={`scene-frame${loaded || !hasImage ? " is-visible" : ""}`}
      data-scene-kind={previous ? undefined : frame.kind} aria-hidden={previous || undefined}>
      {hasImage
        ? <img className="scene-background" src={sceneAsset(frame.image)} alt={frame.alt} onLoad={() => setLoaded(true)} onError={() => setFailed(true)} />
        : <div className="scene-placeholder"><span aria-hidden="true">{categoryEmoji(category)}</span></div>}
      {hasPortrait && <img className="scene-portrait" src={sceneAsset(frame.portrait)} alt="" onError={() => setPortraitFailed(true)} />}
      {frame.caption && <span className="scene-caption">{frame.caption}</span>}
    </div>
  );
}

function Bubble({ m, dim }) {
  if (m.role === "narrator") return <div className="narration">📍 {m.text}</div>;
  if (m.role === "system") return <div className="system-note">{m.text}</div>;
  const mine = m.role === "user";
  return (
    <div className={`bubble-row ${mine ? "mine" : ""} ${dim ? "dim" : ""}`}>
      {!mine && <div className="avatar">{m.name.slice(0, 1)}</div>}
      <div>
        {!mine && <div className="speaker">{m.name}</div>}
        <div className="bubble">{m.text}</div>
      </div>
    </div>
  );
}

function StageDots({ current, total, status }) {
  return (
    <div className="stage-dots" title={`${current}/${total}단계`}>
      {Array.from({ length: total }, (_, i) => {
        const n = i + 1;
        const done = n < current || status === "cleared";
        return <span key={n} className={done ? "done" : n === current ? "now" : ""} />;
      })}
      <small>{current}/{total}</small>
    </div>
  );
}

function RiskGauge({ risk, max }) {
  const pct = Math.min(100, Math.round((risk / max) * 100));
  return (
    <div className="risk" title="위험도가 끝까지 차면 대피 실패">
      <small>위험도</small>
      <div className="risk-bar">
        <div className={`risk-fill risk-${riskLevel(risk, max)}`} style={{ width: `${pct}%` }} />
      </div>
      <small>{Math.min(risk, max)}/{max}</small>
    </div>
  );
}
