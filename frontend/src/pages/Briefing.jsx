import { useState } from "react";

export default function Briefing({ scenario, onStart, onBack }) {
  return (
    <main className="page briefing">
      <button className="ghost" onClick={onBack}>← 목록</button>
      <section className="report-head"><div>
        <span className="tag">시작 전 브리핑 · {scenario.category}</span>
        <h1>{scenario.title}</h1>
        <p className="summary">{scenario.summary}</p>
        <p className="muted">{scenario.total_stages}단계 · 약 {scenario.estimated_minutes || 7}분</p>
      </div></section>
      <h2 className="section-title">당신의 임무</h2>
      <p className="eyebrow">{scenario.briefing?.role || "현장의 당사자"}</p>
      <p>{scenario.briefing?.mission || scenario.summary}</p>
      <div className="skill-tags">{scenario.briefing?.focus?.map(label => <span key={label}>{label}</span>)}</div>
      <div className="cast-heading"><div><span className="eyebrow">MEET YOUR COMPANIONS</span><h2 className="section-title">함께할 인물</h2></div><p>같은 현장, 서로 다른 마음.<br />당신의 한마디가 이들의 다음 행동을 바꿉니다.</p></div>
      <div className="character-grid">{scenario.characters.map(c => <CharacterCard key={c.name} character={c} />)}</div>
      <h2 className="section-title">플레이 방법</h2>
      <ol className="instructions">
        <li>상황과 상대의 말을 읽고, 내가 할 행동을 구체적으로 입력하세요.</li>
        <li>위험한 판단은 위험도를 높입니다. 한 단계에서 행동을 시도할 기회는 3번입니다.</li>
        <li>궁금한 건 상대에게 자유롭게 물어보세요. 질문과 대화는 기회를 쓰지 않습니다.</li>
        <li>종료 후 내 발언과 단계별 행동 기준을 비교할 수 있습니다.</li>
      </ol>
      <p className="demo-note">당신의 판단이 다음 장면에 남습니다. 행동을 여러 번에 나누어 말할 수 있지만, 위험한 선택을 하면 해당 단계의 확인 근거를 다시 모읍니다. 자동 판정은 표현을 놓칠 수 있으며, 결과에서 근거를 확인할 수 있습니다.</p>
      <div className="actions"><button className="primary" onClick={onStart}>준비 완료 · 현장으로</button></div>
    </main>
  );
}

function CharacterCard({ character: c }) {
  const [broken, setBroken] = useState(false);
  return <article className="character-card">
    <div className="character-art">{c.image && !broken
      ? <img src={`/scenes/${c.image.split('/').map(encodeURIComponent).join('/')}`} alt={`${c.name} 캐릭터`} onError={() => setBroken(true)} />
      : <span className="character-initial" aria-hidden="true">{c.name.slice(0, 1)}</span>}<span className="character-art-label">함께하는 인물</span></div>
    <div className="character-copy"><span className="character-role">{c.role}</span><h3>{c.name}</h3>
      {c.quote && <blockquote>“{c.quote}”</blockquote>}
      <p>{c.introduction || `${c.name}도 당신과 같은 현장에 있습니다. 상대의 말에 귀 기울이고, 지금의 판단을 함께 나누어 보세요.`}</p>
    </div>
  </article>;
}
