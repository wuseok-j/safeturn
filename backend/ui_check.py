"""격리 DB·mock AI·Edge headless로 PC/모바일 완주와 이어하기를 확인한다.

실행 전 frontend에서 npm.cmd run build. 개발 DB·실제 API·기존 서버를 사용하지 않는다.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if '--server' in sys.argv:
    import uvicorn
    from app import harness
    if os.getenv('MIA_QA_SCENARIOS'):
        harness.SCENARIO_DIR = Path(os.environ['MIA_QA_SCENARIOS'])
        harness.SCENARIOS = harness.load_scenarios()
    from serve import app
    uvicorn.run(app, host='127.0.0.1', port=18765, log_level='error')
else:
    import subprocess
    import tempfile
    import shutil
    import time
    import urllib.request
    from playwright.sync_api import expect, sync_playwright
    from demo_cases import ANSWERS

    output = ROOT / '.qa'
    output.mkdir(exist_ok=True)
    env = {**os.environ, 'LLM_PROVIDER': 'mock', 'MIA_DB_PATH': str(output / 'ui-test.db'), 'ADMIN_TOKEN': 'qa-local-only'}
    # 매 실행 별도 DB를 사용한다.
    env['MIA_DB_PATH'] = os.path.join(tempfile.mkdtemp(), 'ui.db')
    scenario_copy = Path(tempfile.mkdtemp())
    for source in (ROOT / 'data/scenarios').glob('*.json'):
        shutil.copy2(source, scenario_copy / source.name)
    env['MIA_QA_SCENARIOS'] = str(scenario_copy)
    server = subprocess.Popen([sys.executable, '-X', 'utf8', __file__, '--server'], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen('http://127.0.0.1:18765/api/scenarios', timeout=1)
                break
            except Exception:
                time.sleep(.2)
        else:
            raise RuntimeError('격리 서버 시작 실패')
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            for name, width, height in [('desktop', 1280, 900), ('mobile', 390, 844)]:
                context = browser.new_context(viewport={'width': width, 'height': height})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                for sid, title in [('fire_office', '오피스 화재 대피'), ('earthquake_school', '학교 지진 대응')]:
                    page.goto('http://127.0.0.1:18765')
                    card = page.locator('.scenario-card').filter(has_text=title)
                    card.get_by_role('button', name='임무 확인하기').click()
                    page.get_by_role('button', name='준비 완료').click()
                    page.locator('.scene-heading').wait_for()
                    page.screenshot(path=str(output / f'{name}-{sid}-play.png'), full_page=True)
                    stage_frame = page.locator('[data-scene-kind="stage"]')
                    caption = stage_frame.locator('.scene-caption')
                    assert stage_frame.locator('img').evaluate('(el) => el.complete && el.naturalWidth > 0')
                    expected_speaker = '박지훈' if sid == 'fire_office' else '이수아'
                    expect(caption).to_have_text(expected_speaker)
                    expect(stage_frame.locator('img')).to_have_attribute('src', f'/scenes/{sid}/stage1-ai.jpg')
                    assert stage_frame.locator('.scene-portrait').count() == 0
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), '가로 넘침'
                    if name == 'mobile':
                        page.locator('.scene-panel summary').click()
                        assert not page.locator('.scene-panel').evaluate('(el) => el.open')
                        page.set_viewport_size({'width': 390, 'height': 500})
                        bounds = page.locator('.composer').bounding_box()
                        assert bounds['y'] + bounds['height'] <= 500, '작은 높이에서 입력창 가림'
                        page.locator('.scene-panel summary').click()
                        expect(page.locator('.scene-content')).to_be_visible()
                        expect(stage_frame.locator('.scene-background')).to_be_visible()
                        bounds = page.locator('.composer').bounding_box()
                        assert bounds['y'] + bounds['height'] <= 500, '장면을 펼쳤을 때 입력창 가림'
                        page.locator('.scene-panel summary').click()
                        page.set_viewport_size({'width': width, 'height': height})
                    if name == 'desktop' and sid == 'fire_office':
                        page.route('**/api/sessions/*/messages', lambda route: route.fulfill(
                            status=503, content_type='application/json', body='{"detail":"QA simulated failure"}'))
                        page.get_by_role('textbox', name='내가 할 행동').fill('복원할 문장')
                        page.get_by_role('button', name='보내기', exact=True).click()
                        page.locator('.error-box').wait_for()
                        assert page.get_by_role('textbox', name='내가 할 행동').input_value() == '복원할 문장'
                        page.unroute('**/api/sessions/*/messages')
                        def drop_after_processing(route):
                            route.fetch()
                            route.abort('failed')
                        page.route('**/api/sessions/*/messages', drop_after_processing)
                        page.get_by_role('textbox', name='내가 할 행동').fill(ANSWERS[sid][0])
                        page.get_by_role('button', name='보내기', exact=True).click()
                        page.locator('.error-box').wait_for()
                        session_id = page.evaluate('JSON.parse(localStorage.getItem("mia-active-play")).sessionId')
                        stored = page.request.get(f'http://127.0.0.1:18765/api/sessions/{session_id}').json()
                        assert stored['stage'] == 2, '응답 손실 전에 서버는 처리 완료해야 함'
                        page.unroute('**/api/sessions/*/messages')
                    for index, text in enumerate(ANSWERS[sid]):
                        if sid == 'earthquake_school' and index == 2:
                            text = '엘리베이터는위험해 계단으로가자'
                        box = page.get_by_role('textbox', name='내가 할 행동')
                        if sid == 'earthquake_school' and index == 0:
                            box.fill('책상 아래에 숨자')
                            page.get_by_role('button', name='보내기', exact=True).click()
                            partial = page.locator('[data-scene-kind="partial"] img')
                            expect(partial).to_have_attribute('src', '/scenes/earthquake_school/partial-shelter.jpg')
                            expect(partial).to_be_visible()
                            expect(page.locator('.typing')).to_have_count(0)
                            expect(page.get_by_text('책상이 자꾸 밀려', exact=False)).to_be_visible()
                            expect(page.locator('.stage-dots small')).to_have_text('1/5')
                            text = '책상 다리를 잡을게'
                        if sid == 'fire_office' and index == 3:
                            for trial, mistakes in [('아직 움직이지 마.', 0), ('문을 열려고 손잡이를 잡을게.', 1)]:
                                box.fill(trial)
                                page.get_by_role('button', name='보내기', exact=True).click()
                                if mistakes:
                                    cut = page.locator('[data-scene-kind="outcome"] img')
                                    expect(cut).to_have_attribute('src', '/scenes/fire_office/outcome-hot-handle.jpg')
                                    expect(cut).to_be_visible()
                                expect(page.get_by_text(f'이 장면의 위험 행동 {mistakes}회', exact=True)).to_be_visible()
                                expect(page.locator('.typing')).to_have_count(0)
                                expect(page.locator('.stage-dots small')).to_have_text('4/5')
                            expect(page.locator('.narration').filter(has_text='손에 화상을 입었다')).to_be_visible()
                        box.fill(text)
                        if index == 0:
                            page.evaluate('''() => {
                                window.cutawayTiming = {};
                                const observer = new MutationObserver(() => {
                                    const active = document.querySelector('[data-scene-kind="action"]');
                                    if (active && !cutawayTiming.started) cutawayTiming.started = performance.now();
                                    if (!active && cutawayTiming.started) {
                                        cutawayTiming.ended = performance.now();
                                        observer.disconnect();
                                    }
                                });
                                observer.observe(document.querySelector('.scene'), { childList: true, subtree: true, attributes: true });
                            }''')
                        with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/messages')) as sent:
                            page.get_by_role('button', name='보내기', exact=True).click()
                        response = sent.value.json()
                        action_frame = page.locator('[data-scene-kind="action"]')
                        expect(action_frame).to_be_visible()
                        action_file = 'action1-call-ai.jpg' if sid == 'fire_office' and index == 0 else f'action{index + 1}-ai.jpg'
                        expect(action_frame.locator('img')).to_have_attribute('src', f'/scenes/{sid}/{action_file}')
                        expect(page.locator('.stage-dots small')).to_have_text(f'{index + 1}/5')
                        expect(page.get_by_role('button', name='보내기', exact=True)).to_be_disabled()
                        chat = page.locator('.chat')
                        count = response['action_scene']['message_count']
                        expect(chat.locator('.mine:not(.dim) .bubble').last).to_have_text(text)
                        expect(chat.locator('.bubble-row:not(.mine) .bubble').last).to_have_text(response['messages'][count - 1]['text'])
                        next_narration = chat.locator('.narration, .system-note').filter(has_text=response['messages'][count]['text'])
                        expect(next_narration).to_have_count(0)
                        if name == 'desktop' and index == 0:
                            action_frame.evaluate('(el) => Promise.all(el.getAnimations().map(animation => animation.finished))')
                            page.screenshot(path=str(output / f'{name}-{sid}-action.png'))
                        expect(page.locator('.typing')).to_have_count(0)
                        expect(next_narration.last).to_be_visible()
                        if index == 0:
                            elapsed = page.evaluate('cutawayTiming.ended - cutawayTiming.started')
                            assert 2900 <= elapsed < 4500, f'행동 컷 표시 시간 {elapsed}ms'
                        if name == 'mobile' and index < 4:
                            assert not page.locator('.scene-panel').evaluate('(el) => el.open')
                        if name == 'desktop' and index == 0:
                            page.reload()
                            page.locator('.resume-banner').get_by_role('button', name='이어하기', exact=True).click()
                            page.locator('.scene-heading').wait_for()
                            assert page.locator('.stage-dots small').inner_text() == '2/5'
                            expect(caption).to_have_text(expected_speaker)
                            expect(stage_frame.locator('img')).to_have_attribute('src', f'/scenes/{sid}/stage2-ai.jpg')
                            if sid == 'fire_office':
                                stored = page.request.get(f'http://127.0.0.1:18765/api/sessions/{session_id}').json()
                                assert sum(m['role'] == 'user' and m['text'] == text for m in stored['messages']) == 1
                        if sid == 'fire_office' and index == 3:
                            expect(caption).to_have_text('최민호 소방관')
                            expect(stage_frame.locator('img')).to_have_attribute('src', f'/scenes/{sid}/stage5-ai.jpg')
                    ending = page.locator('[data-scene-kind="cleared"] img')
                    expect(ending).to_be_visible()
                    expect(ending).to_have_attribute('src', f'/scenes/{sid}/cleared-ai.jpg')
                    expect(page.locator('.scene-heading')).to_have_text('대피 완료')
                    if name == 'desktop':
                        ending.evaluate('(el) => el.decode()')
                        page.screenshot(path=str(output / f'{name}-{sid}-ending.png'))
                    page.get_by_role('button', name='리포트 보기', exact=True).click()
                    page.locator('.report-head').wait_for()
                    assert page.locator('.score strong').inner_text() == '5'
                    page.screenshot(path=str(output / f'{name}-{sid}-report.png'), full_page=True)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), '리포트 가로 넘침'
                    assert not errors, errors
                    print(f'PASS: {name} {sid} 5/5, images, report, no overflow or page errors; extra layout/resume/error checks')
                page.goto('http://127.0.0.1:18765')
                page.locator('.scenario-card').filter(has_text='학교 지진 대응').get_by_role('button', name='임무 확인하기').click()
                page.get_by_role('button', name='준비 완료').click()
                for text in ['아직 움직이지 마.', '벽을 두드려볼게', '기다리지 말고 먼저 나가자',
                             '머리를 보호하지 않고 복도로 뛰어갈게.', '머리를 보호하지 않고 복도로 뛰어갈게.']:
                    page.get_by_role('textbox', name='내가 할 행동').fill(text)
                    page.get_by_role('button', name='보내기', exact=True).click()
                    if text in {'벽을 두드려볼게', '기다리지 말고 먼저 나가자'}:
                        cut = page.locator('[data-scene-kind="outcome"] img')
                        image = 'interactions/action-knock.jpg' if text.startswith('벽') else 'earthquake_school/outcome-falling-object.jpg'
                        expect(cut).to_have_attribute('src', f'/scenes/{image}')
                        expect(cut).to_be_visible()
                        if text == '기다리지 말고 먼저 나가자':
                            cut.evaluate('(el) => Promise.all(el.parentElement.getAnimations().map(animation => animation.finished))')
                            page.screenshot(path=str(output / f'{name}-earthquake_school-outcome.png'))
                    page.wait_for_function('!document.querySelector(".typing")')
                    if text == '벽을 두드려볼게':
                        expect(page.locator('.narration').filter(has_text='소리가 짧게 울린다')).to_be_visible()
                        expect(page.get_by_text('이 장면의 위험 행동 0회', exact=True)).to_be_visible()
                    if text == '기다리지 말고 먼저 나가자':
                        expect(page.locator('.narration').filter(has_text='물건이 바로 앞 바닥으로 떨어졌다')).to_be_visible()
                        expect(page.locator('.stage-dots small')).to_have_text('1/5')
                page.get_by_role('button', name='리포트 보기', exact=True).click()
                page.locator('.report-head').wait_for()
                assert page.locator('.score strong').inner_text() == '0'
                failed = page.locator('.check.failed')
                assert '위험도가 한도에 도달' in failed.locator('.check-reason').inner_text()
                assert failed.locator('.action-review').count() == 4
                assert '머리를 드러낸 채 움직이자' in page.locator('.decision-timeline').inner_text()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(output / f'{name}-assessment-failed-report.png'), full_page=True)
                print(f'PASS: {name} failed report identifies missing action and explains all three attempts')
                # 운영자 작업은 별도 임시 시나리오 폴더에서만 수행한다.
                page.get_by_role('button', name='운영자', exact=True).click()
                page.get_by_label('운영자 토큰', exact=True).fill('invalid-test-token')
                page.get_by_role('button', name='들어가기', exact=True).click()
                page.locator('.error-box').wait_for()
                page.get_by_label('운영자 토큰', exact=True).fill('qa-local-only')
                page.get_by_role('button', name='들어가기', exact=True).click()
                page.locator('.admin-new').wait_for()
                page.get_by_role('button', name='기존 시나리오 복제', exact=True).click()
                page.locator('.admin-new select').select_option('fire_office')
                page.get_by_placeholder('earthquake_school', exact=True).fill('qa_' + name)
                page.get_by_placeholder('학교 지진 대응', exact=True).fill('QA ' + name)
                page.get_by_role('button', name='만들고 편집하기', exact=True).click()
                page.locator('.editor-actions').wait_for()
                page.get_by_label('제목', exact=True).fill('QA 수정 ' + name)
                page.get_by_role('button', name='저장', exact=True).click()
                page.locator('.ok-box').wait_for()
                if name == 'desktop':
                    page.screenshot(path=str(output / 'cms-editor.png'), full_page=True)
                page.get_by_role('button', name='미리 플레이', exact=True).click()
                page.locator('.scene-heading').wait_for()
                page.get_by_role('button', name='← 목록', exact=True).click()
                page.get_by_role('button', name='공개하기', exact=True).click()
                page.locator('.ok-box').wait_for()
                page.locator('.brand').click()
                page.locator('.scenario-card').filter(has_text='QA 수정 ' + name).wait_for()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors, errors
                print(f'PASS: {name} CMS invalid token, duplicate, edit, save, preview, publish')
                context.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
