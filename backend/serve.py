"""제출용 단일 로컬 서버: /api 백엔드, / 정적 웹 화면."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.main import app as api

dist = Path(__file__).resolve().parents[1] / 'frontend/dist'
if not (dist / 'index.html').is_file():
    raise RuntimeError('frontend에서 npm.cmd run build를 먼저 실행하세요.')
app = FastAPI(title='SafeTurn local demo')
app.mount('/api', api)
app.mount('/', StaticFiles(directory=dist, html=True))
