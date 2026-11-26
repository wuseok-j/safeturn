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
    from playwright.sync_api import sync_playwright
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
                    assert page.locator('.scene-panel img').evaluate('(el) => el.complete && el.naturalWidth > 0')
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), '가로 넘침'
                    if name == 'mobile':
                        page.locator('.scene-panel summary').click()
                        assert not page.locator('.scene-panel').evaluate('(el) => el.open')
                        page.set_viewport_size({'width': 390, 'height': 500})
                        bounds = page.locator('.composer').bounding_box()
                        assert bounds['y'] + bounds['height'] <= 500, '작은 높이에서 입력창 가림'
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
                        box.fill(text)
                        page.get_by_role('button', name='보내기', exact=True).click()
                        page.wait_for_function('!document.querySelector(".typing")')
                        if name == 'desktop' and index == 0:
                            page.reload()
                            page.locator('.resume-banner').get_by_role('button', name='이어하기', exact=True).click()
                            page.locator('.scene-heading').wait_for()
                            assert page.locator('.stage-dots small').inner_text() == '2/5'
                            if sid == 'fire_office':
                                stored = page.request.get(f'http://127.0.0.1:18765/api/sessions/{session_id}').json()
                                assert sum(m['role'] == 'user' and m['text'] == text for m in stored['messages']) == 1
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
                for text in [*ANSWERS['earthquake_school'][:2], '계단으로 가자',
                             '그냥 선생님 지시만 따라다녀', '그냥 선생님 지시만 따라다녀',
                             *ANSWERS['earthquake_school'][3:]]:
                    page.get_by_role('textbox', name='내가 할 행동').fill(text)
                    page.get_by_role('button', name='보내기', exact=True).click()
                    page.wait_for_function('!document.querySelector(".typing")')
                page.get_by_role('button', name='리포트 보기', exact=True).click()
                page.locator('.report-head').wait_for()
                assert page.locator('.score strong').inner_text() == '4'
                failed = page.locator('.check.failed')
                assert '엘리베이터 탑승 제지' in failed.locator('.check-reason').inner_text()
                assert failed.locator('.action-review').count() == 3
                assert '위험 행동 판정은 아닙니다' in failed.inner_text()
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
