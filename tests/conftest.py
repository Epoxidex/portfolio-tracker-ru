import os
import tempfile
from pathlib import Path

import pytest


_TEMP_DIR = tempfile.TemporaryDirectory(prefix="portfolio-tracker-tests-")
os.environ["DB_PATH"] = str(Path(_TEMP_DIR.name) / "test.db")
os.environ["TINVEST_TOKEN"] = ""
os.environ["TINVEST_ACCOUNT_ID"] = ""
os.environ["SNAPSHOT_EVERY_MIN"] = "0"
os.environ["FETCH_EVERY_MIN"] = "0"
os.environ["FX_EVERY_MIN"] = "0"
os.environ["PORTFOLIO_TRACKING_START_DATE"] = ""

from app.db import Base, SessionLocal, engine  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    _TEMP_DIR.cleanup()


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session
