from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse
from apscheduler.schedulers.background import BackgroundScheduler
from pathlib import Path
from contextlib import asynccontextmanager
from .db import init_db, SessionLocal
from .routers import api
from . import config
from .services import snapshots
from .services.tinvest import fetch_prices
from .services.operations import sync_operations
from .services.banki import fetch_fx
from .dataio import DATABASE_MAINTENANCE_LOCK

BASE = Path(__file__).resolve().parent.parent
REACT_DIST = BASE / "frontend" / "dist"
scheduler = BackgroundScheduler(timezone="Europe/Moscow")


def _job_snapshot():
    with DATABASE_MAINTENANCE_LOCK:
        db = SessionLocal()
        try:
            snapshots.take_snapshot(db, source="auto")
        except Exception as e:
            print("snapshot job error:", e)
        finally:
            db.close()


def _job_fetch():
    with DATABASE_MAINTENANCE_LOCK:
        db = SessionLocal()
        try:
            if config.TINVEST_TOKEN:
                operations = sync_operations(db, days_back=30)
                if not operations.get("ok"):
                    print("sync-operations job error:", operations.get("error"))
                fetch_prices(db)
        except Exception as e:
            print("fetch-prices job error:", e)
        finally:
            db.close()


def _job_fx():
    with DATABASE_MAINTENANCE_LOCK:
        db = SessionLocal()
        try:
            fetch_fx(db)
        except Exception as e:
            print("fetch-fx job error:", e)
        finally:
            db.close()


def _startup():
    init_db()
    if config.FETCH_EVERY_MIN > 0:
        scheduler.add_job(_job_fetch, "interval", minutes=config.FETCH_EVERY_MIN, id="fetch",
                          next_run_time=__import__("datetime").datetime.now())
    if config.FX_EVERY_MIN > 0:
        scheduler.add_job(_job_fx, "interval", minutes=config.FX_EVERY_MIN, id="fx",
                          next_run_time=__import__("datetime").datetime.now())
    if config.SNAPSHOT_EVERY_MIN > 0:
        scheduler.add_job(_job_snapshot, "interval", minutes=config.SNAPSHOT_EVERY_MIN, id="snap")
    if scheduler.get_jobs():
        scheduler.start()


def _shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _startup()
    try:
        yield
    finally:
        _shutdown()


app = FastAPI(title="Портфель — личный трекер", lifespan=lifespan)
app.include_router(api.router)


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/react-preview", include_in_schema=False)
@app.get("/react-preview/", include_in_schema=False)
def react_preview():
    index_file = REACT_DIST / "index.html"
    if not index_file.is_file():
        return PlainTextResponse(
            "React preview is not built. Run `npm.cmd run build` in frontend/.",
            status_code=503,
        )
    return FileResponse(index_file)


app.mount(
    "/react-preview/assets",
    StaticFiles(directory=REACT_DIST / "assets", check_dir=False),
    name="react-preview-assets",
)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
