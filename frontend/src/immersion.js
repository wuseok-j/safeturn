import { useEffect, useRef, useState } from 'react';
import { playSoundscape, prepareSceneAudio, releaseSceneAudio, saveSoundPreference, soundPreferred } from './sceneAudio.js';

// 연출은 현재 단계·위험도를 읽기만 한다. 판정과 진행은 서버가 결정한다.
export function atmosphereFor(scenario, turn) {
  if (!turn || turn.status !== 'playing') return { theme: 'calm', phase: 'settled', label: !turn ? '현장 연결 중' : turn.status === 'cleared' ? '현장을 벗어났습니다' : '연습 종료 · 판단을 돌아볼 시간', smoke: 0, sound: null };
  const index = turn.stage - 1;
  const profiles = {
    fire_office: {
      theme: 'fire', phase: ['smoke', 'alarm', 'dense-smoke', 'hot-door', 'outside'],
      labels: ['희미한 연기 · 실내', '경보가 울리는 복도', '짙은 연기 · 계단', '문틈으로 새는 연기', '건물 밖 · 구조대 도착'],
      smoke: [.32, .48, .78, .5, 0], sounds: ['crackle', 'alarm', 'smoke', 'door', 'siren'],
    },
    earthquake_school: {
      theme: 'quake', phase: ['tremor', 'settled-room', 'evacuation', 'open-air', 'assembly'],
      labels: ['흔들림이 계속되는 교실', '흔들림이 잦아든 교실', '대피 중인 복도', '탁 트인 건물 밖', '집결 구역 · 안내방송'],
      smoke: [0, 0, 0, 0, 0], sounds: ['rumble', 'settle', 'steps', 'wind', 'assembly'],
    },
    elevator_apartment: {
      theme: 'lift', phase: ['stall', 'intercom', 'waiting', 'rescue', 'hall'],
      labels: ['갑자기 멈춘 승강기', '끊어진 인터폰 연결', '좁은 공간 · 기다림', '문 밖에서 들리는 구조대', '복도에 돌아온 일상'],
      smoke: [0, 0, 0, 0, 0], sounds: ['stall', 'intercom', 'vent', 'rescue', 'hall'],
    },
  };
  const profile = profiles[scenario.id];
  if (!profile) return { theme: 'calm', phase: 'settled', label: turn.stage_title, smoke: 0, sound: null };
  return { theme: profile.theme, phase: profile.phase[index] || 'settled', label: profile.labels[index] || turn.stage_title, smoke: profile.smoke[index] || 0, sound: profile.sounds[index] || null };
}

export function useImmersion(scenario, turn) {
  const [effects, setEffects] = useState(() => { try { return localStorage.getItem('safeturn-effects') !== 'off'; } catch { return true; } });
  const [sound, setSound] = useState(soundPreferred);
  const [audioError, setAudioError] = useState('');
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const audio = useRef(null), stopSound = useRef(null);
  const ambience = atmosphereFor(scenario, turn);
  const risk = turn?.max_risk ? turn.risk / turn.max_risk : 0;
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    if (!sound || !ambience.sound) return;
    try { audio.current = prepareSceneAudio(); }
    catch { setAudioError('환경음을 켜지 못했습니다. 환경음 버튼을 다시 눌러 주세요.'); return; }
    if (!audio.current) { setAudioError('이 브라우저에서는 환경음을 지원하지 않습니다.'); return; }
    const start = () => { stopSound.current?.(); stopSound.current = playSoundscape(audio.current, ambience.sound, risk); };
    if (!document.hidden) start();
    const onVisibility = () => { if (document.hidden) { stopSound.current?.(); stopSound.current = null; } else start(); };
    document.addEventListener('visibilitychange', onVisibility);
    return () => { stopSound.current?.(); stopSound.current = null; document.removeEventListener('visibilitychange', onVisibility); };
  }, [sound, ambience.sound, turn?.stage, turn?.status, risk]);
  useEffect(() => {
    try { if (soundPreferred()) audio.current = prepareSceneAudio(); } catch { /* 클릭 재시도로 복구 */ }
    return () => { stopSound.current?.(); releaseSceneAudio(audio.current); };
  }, []);
  function toggleEffects() {
    setEffects(previous => { const next = !previous; try { localStorage.setItem('safeturn-effects', next ? 'on' : 'off'); } catch { /* 저장 불가 */ } return next; });
  }
  async function toggleSound() {
    if (sound) { stopSound.current?.(); saveSoundPreference(false); setSound(false); return; }
    try {
      audio.current = prepareSceneAudio(true);
      if (!audio.current) throw new Error('unsupported');
      await audio.current.resume();
      saveSoundPreference(true); setAudioError(''); setSound(true);
    } catch { setAudioError('환경음을 켜지 못했습니다. 다시 눌러 주세요.'); }
  }
  return { ambience, effects, sound, reduced, audioError, toggleEffects, toggleSound };
}
