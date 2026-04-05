from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dashboard.db import close_pool, get_pool, ping_db
from dashboard.routes.fragments import router as fragments_router

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_pool()


app = FastAPI(title="Horde Fleet Dashboard", lifespan=lifespan)
app.include_router(fragments_router)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(fragments_router)
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/healthz")
async def healthz():
    db_status = "connected" if await ping_db() else "unavailable"
    return {"status": "ok", "db": db_status}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
