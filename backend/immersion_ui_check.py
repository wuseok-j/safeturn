"""빌드 후 실행: 격리 mock 서버에서 인물 카드·현장 효과·Web Audio 수명·작은 화면을 검증한다."""
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))
from demo_cases import ANSWERS
env = {**os.environ, 'LLM_PROVIDER': 'mock', 'MIA_DB_PATH': str(Path(tempfile.mkdtemp()) / 'immersion.db')}
server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'serve:app', '--host', '127.0.0.1', '--port', '18768'],
                         cwd=root / 'backend', env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
audio_probe = '''(() => {
  window.audioProbe = { contexts: 0, starts: 0, stops: 0, closed: 0 };
  const Native = window.AudioContext || window.webkitAudioContext;
  if (!Native) return;
  window.AudioContext = class extends Native {
    constructor(...args) { super(...args); audioProbe.contexts++; audioProbe.latest = this; }
    createBufferSource() {
      const source = super.createBufferSource();
      const start = source.start.bind(source), stop = source.stop.bind(source);
      source.start = (...args) => { audioProbe.starts++; return start(...args); };
      source.stop = (...args) => { audioProbe.stops++; return stop(...args); };
      return source;
    }
    close() { audioProbe.closed++; return super.close(); }
  };
})()'''
try:
    for _ in range(60):
        try:
            urllib.request.urlopen('http://127.0.0.1:18768/api/scenarios', timeout=1)
            break
        except Exception:
            time.sleep(.2)
    else:
        raise RuntimeError('Server did not start')
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        for name, width, height in [('desktop',1280,900),('mobile',390,844),('short',390,500)]:
            for sid, title, theme in [('fire_office','오피스 화재 대피','fire'),('earthquake_school','학교 지진 대응','quake'),('elevator_apartment','아파트 엘리베이터 갇힘','lift')]:
                context = browser.new_context(viewport={'width':width,'height':height})
                context.add_init_script(audio_probe)
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto('http://127.0.0.1:18768')
                page.locator('.scenario-card').filter(has_text=title).get_by_role('button',name='임무 확인하기').click()
                expect(page.locator('.character-card')).to_have_count(2 if theme == 'fire' else 1)
                page.wait_for_function("Array.from(document.querySelectorAll('.character-art img')).every(i => i.complete && i.naturalWidth > 0)")
                assert all(text.strip() for text in page.locator('.character-copy p').all_text_contents())
                if name != 'short':
                    page.screenshot(path=str(root/'.qa'/f'cast-{name}-{sid}.png'), full_page=True)
                assert page.evaluate('audioProbe.contexts') == 0, '브리핑 전 자동재생 금지'
                page.get_by_role('button',name='준비 완료').click()
                play = page.locator('.immersive-play')
                expect(play).to_have_class(__import__('re').compile(f'theme-{theme}'))
                expect(page.get_by_role('button',name='환경음 켜짐')).to_be_visible()
                page.wait_for_function('audioProbe.starts > 0')
                page.wait_for_function("audioProbe.latest.state === 'running'")
                assert page.evaluate('audioProbe.contexts') == 1
                if theme == 'quake':
                    assert page.locator('.play-workspace').evaluate("el => getComputedStyle(el).animationName") == 'scene-tremor'
                if theme == 'fire':
                    assert float(page.locator('.scene-smoke').evaluate('el => getComputedStyle(el).opacity')) > 0
                if name == 'desktop' and theme == 'fire':
                    page.get_by_role('button',name='환경음 켜짐').click()
                    for _ in range(2):
                        page.get_by_role('textbox',name='내가 할 행동').fill('그냥 기다리자')
                        page.get_by_role('button',name='보내기',exact=True).click()
                        expect(page.locator('.typing')).to_have_count(0)
                    expect(play).to_have_attribute('data-risk','high')
                    assert float(play.evaluate("el => el.style.getPropertyValue('--danger-opacity')")) > 0
                    page.screenshot(path=str(root/'.qa/immersion-risk-high.png'))
                    page.get_by_role('button',name='화면 효과 켜짐').click()
                    expect(play).to_have_class(__import__('re').compile('effects-off'))
                    page.wait_for_function("getComputedStyle(document.querySelector('.scene-smoke')).opacity === '0'")
                bounds = page.locator('.composer').bounding_box()
                assert bounds['y'] + bounds['height'] <= height + 1, (name, sid, bounds)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.get_by_role('button',name='← 목록',exact=True).click()
                expect(page.locator('.immersion-veil')).to_have_count(0)
                if name == 'desktop' and theme == 'fire':
                    assert page.evaluate('audioProbe.closed') == 1
                    # 끄기 선택은 이어하기에도 유지되고, 다시 켜기는 새 컨텍스트를 만든다.
                    page.locator('.resume-banner').get_by_role('button',name='이어하기',exact=True).click()
                    expect(page.get_by_role('button',name='환경음 꺼짐')).to_be_visible()
                    assert page.evaluate('audioProbe.contexts') == 1
                    before = page.evaluate('audioProbe.starts')
                    page.get_by_role('button',name='환경음 꺼짐').click()
                    page.wait_for_function(f'audioProbe.starts > {before}')
                    page.get_by_role('button',name='← 목록',exact=True).click()
                    assert page.evaluate('audioProbe.closed') == 2
                assert not errors, errors
                print(f'PASS {name} {theme}: cast, atmosphere, controls, composer, no overflow/errors',flush=True)
                if name == 'desktop':
                    page.goto('http://127.0.0.1:18768')
                    page.locator('.scenario-card').filter(has_text=title).get_by_role('button',name='임무 확인하기').click()
                    page.get_by_role('button',name='준비 완료').click()
                    expected_sounds = {
                        'fire': ['crackle','alarm','smoke','door','siren'],
                        'quake': ['rumble','settle','steps','wind','assembly'],
                        'lift': ['stall','intercom','vent','rescue','hall'],
                    }[theme]
                    play = page.locator('.immersive-play')
                    for number, text in enumerate(ANSWERS[sid]):
                        expect(play).to_have_attribute('data-soundscape', expected_sounds[number])
                        page.get_by_role('textbox',name='내가 할 행동').fill(text)
                        page.get_by_role('button',name='보내기',exact=True).click()
                        expect(page.locator('.typing')).to_have_count(0)
                    expect(play).to_have_attribute('data-soundscape','silent')
                    assert not errors, errors
                    print(f'PASS {theme}: all five stage soundscapes transition and stop at completion',flush=True)
                context.close()
        context = browser.new_context(reduced_motion='reduce')
        page = context.new_page()
        page.goto('http://127.0.0.1:18768')
        page.locator('.scenario-card').filter(has_text='학교 지진 대응').get_by_role('button',name='임무 확인하기').click()
        page.get_by_role('button',name='준비 완료').click()
        expect(page.locator('.immersive-play')).to_have_class(__import__('re').compile('motion-reduced'))
        assert page.locator('.play-workspace').evaluate('el => getComputedStyle(el).animationName') == 'none'
        print('PASS reduced motion: earthquake shake suppressed',flush=True)
        # 실제 합성 결과를 렌더해 무음/클리핑을 검사한다. 장치에서의 청취 평가는 별도다.
        page.route('**/qa-scene-audio.js', lambda route: route.fulfill(
            content_type='text/javascript', body=(root/'frontend/src/sceneAudio.js').read_text(encoding='utf-8')))
        rendered = page.evaluate('''async () => {
          const {playSoundscape} = await import('/qa-scene-audio.js');
          const kinds = ['crackle','alarm','smoke','door','siren','rumble','settle','steps','wind','assembly','stall','intercom','vent','rescue','hall'];
          const results = [];
          for (const kind of kinds) {
            const ctx = new OfflineAudioContext(1, 48000 * 2, 48000);
            const stop = playSoundscape(ctx, kind, .5);
            const output = (await ctx.startRendering()).getChannelData(0);
            let peak = 0, sum = 0;
            for (const sample of output) { peak = Math.max(peak, Math.abs(sample)); sum += sample * sample; }
            stop(); results.push({kind, peak, rms:Math.sqrt(sum/output.length)});
          }
          return results;
        }''')
        for result in rendered:
            assert .001 < result['peak'] < .9 and result['rms'] > .00005, result
        print('PASS 15 soundscapes: rendered signal present, no clipping',flush=True)
        browser.close()
finally:
    server.terminate()
    server.wait(timeout=10)
