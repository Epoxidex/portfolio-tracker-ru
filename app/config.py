import os
import re
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

_db_value = os.getenv("DB_PATH", "portfolio.db")
DB_PATH = Path(_db_value).expanduser()
if not DB_PATH.is_absolute():
    DB_PATH = BASE_DIR / DB_PATH
DB_PATH = DB_PATH.resolve()
DB_URL = f"sqlite:///{DB_PATH.as_posix()}"

# T-Invest API
TINVEST_TOKEN = os.getenv("TINVEST_TOKEN", "").strip()
TINVEST_ACCOUNT_ID = os.getenv("TINVEST_ACCOUNT_ID", "").strip()
TINVEST_SDK_ERROR_REPORTING = os.getenv("TINVEST_SDK_ERROR_REPORTING", "0").lower() in {
    "1", "true", "yes", "on",
}

try:
    PORTFOLIO_GOAL = float(os.getenv("PORTFOLIO_GOAL", "1000000"))
except ValueError as exc:
    raise ValueError("PORTFOLIO_GOAL must be a number") from exc
if PORTFOLIO_GOAL <= 0:
    raise ValueError("PORTFOLIO_GOAL must be positive")

_tracking_start_raw = os.getenv("PORTFOLIO_TRACKING_START_DATE", "").strip()
try:
    PORTFOLIO_TRACKING_START_DATE = (
        date.fromisoformat(_tracking_start_raw) if _tracking_start_raw else None
    )
except ValueError as exc:
    raise ValueError("PORTFOLIO_TRACKING_START_DATE must use YYYY-MM-DD") from exc

# Источник курса валюты: bank_buy | bank_sell | cbr
# bank_buy  = что банк платит вам (вы продаёте валюту)
# bank_sell = что банк берёт с вас (вы покупаете валюту)
# cbr       = официальный курс ЦБ РФ
FX_RATE_SOURCE = os.getenv("FX_RATE_SOURCE", "cbr").lower()
if FX_RATE_SOURCE not in {"bank_buy", "bank_sell", "cbr"}:
    raise ValueError("FX_RATE_SOURCE must be bank_buy, bank_sell or cbr")

# Страница курсов конкретного банка на bankiros.ru
BANKIROS_URL = os.getenv("BANKIROS_URL", "https://bankiros.ru/bank/kamkombank/currency")

# Снимки: каждые N минут когда приложение запущено (0 = выключить автоснимки)
def _non_negative_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{name} cannot be negative")
    return value


SNAPSHOT_EVERY_MIN = _non_negative_int("SNAPSHOT_EVERY_MIN", 60)
# Автообновление цен каждые N минут (0 = выключить)
FETCH_EVERY_MIN = _non_negative_int("FETCH_EVERY_MIN", 0)
# Автообновление курсов валют каждые N минут (0 = выключить)
FX_EVERY_MIN = _non_negative_int("FX_EVERY_MIN", 0)

# Optional private Git repository for unencrypted SQLite backups.
# Authentication is handled by the system Git credential manager, never .env.
BACKUP_GIT_REPOSITORY = os.getenv("BACKUP_GIT_REPOSITORY", "").strip()
BACKUP_GIT_BRANCH = os.getenv("BACKUP_GIT_BRANCH", "main").strip() or "main"
if (
    BACKUP_GIT_BRANCH.startswith("-")
    or ".." in BACKUP_GIT_BRANCH
    or not re.fullmatch(r"[A-Za-z0-9._/-]+", BACKUP_GIT_BRANCH)
):
    raise ValueError("BACKUP_GIT_BRANCH contains unsupported characters")

# Deliberately fixed under an ignored directory so a database can never be
# staged in the public source repository because of a bad environment value.
BACKUP_GIT_DIRECTORY = (BASE_DIR / "backups" / "git-vault").resolve()
