from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from apscheduler.schedulers.background import BackgroundScheduler
from pathlib import Path
from contextlib import asynccontextmanager
from .db import init_db, SessionLocal
from .routers import api
from . import config
from .services import snapshots
from .services.tinvest import fetch_prices
from .services.banki import fetch_fx

BASE = Path(__file__).resolve().parent.parent
scheduler = BackgroundScheduler(timezone="Europe/Moscow")


def _job_snapshot():
    db = SessionLocal()
    try:
        snapshots.take_snapshot(db, source="auto")
    except Exception as e:
        print("snapshot job error:", e)
    finally:
        db.close()


def _job_fetch():
    db = SessionLocal()
    try:
        if config.TINVEST_TOKEN:
            fetch_prices(db)
    except Exception as e:
        print("fetch-prices job error:", e)
    finally:
        db.close()


def _job_fx():
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


app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
