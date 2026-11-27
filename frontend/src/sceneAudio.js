// 시작/이어하기 클릭 안에서 오디오를 준비해 브라우저의 자동재생 정책을 따른다.
let sharedContext = null;
export function soundPreferred() {
  try { return localStorage.getItem('safeturn-sound') !== 'off'; } catch { return true; }
}
export function saveSoundPreference(enabled) {
  try { localStorage.setItem('safeturn-sound', enabled ? 'on' : 'off'); } catch { /* 저장 불가 */ }
}
export function prepareSceneAudio(force = false) {
  if (!force && !soundPreferred()) return null;
  const Audio = window.AudioContext || window.webkitAudioContext;
  if (!Audio) return null;
  if (!sharedContext || sharedContext.state === 'closed') sharedContext = new Audio();
  void sharedContext.resume().catch(() => {});
  return sharedContext;
}
export function releaseSceneAudio(context) {
  if (sharedContext === context) sharedContext = null;
  if (context && context.state !== 'closed') void context.close().catch(() => {});
}

// 음원 다운로드 없이 배경층(공기/기계음)과 사건층(경보/충격/발걸음)을 따로 합성한다.
export function playSoundscape(context, kind, risk = 0) {
  const nodes = [], sources = [];
  const now = context.currentTime;
  const master = context.createGain();
  master.gain.setValueAtTime(0, now);
  master.gain.linearRampToValueAtTime(.22 + Math.min(1, risk) * .06, now + .3);
  master.connect(context.destination); nodes.push(master);
  function noise(frequency, volume, style = 'air', duration = 4, looping = true) {
    const buffer = context.createBuffer(1, Math.ceil(context.sampleRate * duration), context.sampleRate);
    const samples = buffer.getChannelData(0);
    for (let i = 0; i < samples.length; i++) {
      const t = i / context.sampleRate;
      let envelope = 1;
      if (style === 'crackle') envelope = Math.random() > .998 ? 3 : .12;
      if (style === 'rattle') envelope = Math.pow(Math.max(0, Math.sin(t * 37)), 14);
      if (style === 'steps') envelope = Math.exp(-((t % .58) * 38)) + .45 * Math.exp(-(((t + .12) % .58) * 46));
      if (style === 'impact') envelope = Math.exp(-t * 9);
      samples[i] = (Math.random() * 2 - 1) * envelope;
    }
    const source = context.createBufferSource(); source.buffer = buffer; source.loop = looping;
    const filter = context.createBiquadFilter(); filter.type = frequency < 300 ? 'lowpass' : 'bandpass'; filter.frequency.value = frequency; filter.Q.value = .8;
    const gain = context.createGain(); gain.gain.value = volume;
    source.connect(filter).connect(gain).connect(master); source.start();
    if (!looping) source.stop(now + duration);
    nodes.push(source, filter, gain); sources.push(source);
  }
  function tone(frequency, volume, type = 'sine', duration = null, sweep = 0, modulation = 0) {
    const source = context.createOscillator(); source.type = type; source.frequency.value = frequency;
    const gain = context.createGain(); gain.gain.setValueAtTime(0, now); gain.gain.linearRampToValueAtTime(volume, now + .04);
    if (duration) gain.gain.exponentialRampToValueAtTime(.0001, now + duration);
    if (sweep) {
      const lfo = context.createOscillator(); const depth = context.createGain();
      lfo.frequency.value = .65; depth.gain.value = sweep; lfo.connect(depth).connect(source.frequency); lfo.start();
      nodes.push(lfo, depth); sources.push(lfo);
    }
    if (modulation) {
      const lfo = context.createOscillator(); const depth = context.createGain();
      lfo.frequency.value = modulation; depth.gain.value = volume * .4; lfo.connect(depth).connect(gain.gain); lfo.start();
      nodes.push(lfo, depth); sources.push(lfo);
    }
    source.connect(gain).connect(master); source.start();
    if (duration) source.stop(now + duration);
    nodes.push(source, gain); sources.push(source);
  }
  switch (kind) {
    case 'crackle': noise(1400, .2, 'crackle'); noise(450, .045); break;
    case 'alarm': tone(820, .09, 'sine', null, 210); noise(1300, .13, 'crackle'); break;
    case 'smoke': tone(760, .055, 'sine', null, 170); noise(340, .16); noise(1200, .1, 'crackle'); break;
    case 'door': tone(700, .035, 'sine', null, 150); noise(400, .09); tone(170, .08, 'triangle', 1.2); break;
    case 'siren': noise(400, .055); tone(600, .035, 'sine', null, 180); break;
    case 'rumble': noise(100, .6); tone(42, .18, 'sine', null, 0, 3.5); noise(2200, .08, 'rattle'); break;
    case 'settle': noise(230, .07); tone(120, .06, 'triangle', 1.8); break;
    case 'steps': noise(260, .24, 'steps', 3.48); noise(450, .025); break;
    case 'wind': noise(360, .1); break;
    case 'assembly': noise(500, .04); tone(540, .04, 'sine', .8); tone(720, .025, 'sine', 1.5); break;
    case 'stall': tone(65, .12, 'triangle', 2); noise(500, .42, 'impact', 1, false); tone(190, .1, 'sine', .65); noise(160, .08); break;
    case 'intercom': noise(2400, .16, 'rattle', 1.2, false); tone(900, .035, 'sine', .35); noise(170, .09); break;
    case 'vent': noise(170, .12); tone(95, .028, 'sine', null, 0, .8); break;
    case 'rescue': noise(700, .18, 'air', 1.4, false); tone(320, .07, 'triangle', .9); noise(350, .035); break;
    case 'hall': noise(380, .035); noise(240, .1, 'steps', 3.48); break;
    default: noise(250, .04);
  }
  let stopped = false;
  return () => {
    if (stopped) return;
    stopped = true;
    for (const source of sources) { try { source.stop(); } catch { /* 이미 종료 */ } }
    for (const node of nodes) node.disconnect();
  };
}
