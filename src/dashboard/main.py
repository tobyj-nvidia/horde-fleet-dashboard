from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dashboard.db import close_pool, get_pool, ping_db
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
=======
from dashboard.routes.api import api_router
>>>>>>> origin/fleet/989feb15-d3c6-4e0d-aa44-530a6491144f
from dashboard.routes.fragments import router as fragments_router
=======
from dashboard.routes.api import router as api_router
>>>>>>> origin/fleet/65716921-940c-419f-8319-359b71d39e7b
=======
from dashboard.routes.fragments import router as fragments_router
>>>>>>> origin/fleet/911b3304-1490-4058-bf85-bf9239cd6182

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_pool()


app = FastAPI(title="Horde Fleet Dashboard", lifespan=lifespan)
app.include_router(fragments_router)

app.include_router(api_router)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(api_router, prefix="/api")
app.include_router(fragments_router)
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/healthz")
async def healthz():
    db_status = "connected" if await ping_db() else "unavailable"
    return {"status": "ok", "db": db_status}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
