from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Literal, Optional
from datetime import date


class TxIn(BaseModel):
    ts: date
    instrument_id: Optional[int] = None
    ticker: Optional[str] = None          # альтернатива id — найдём инструмент по тикеру/isin
    kind: Literal[
        "buy", "sell", "coupon", "dividend", "interest",
        "fx_buy", "fx_sell", "topup", "withdrawal",
    ]
    quantity: float = 0
    price: float = 0
    amount: float = 0
    commission: float = 0
    note: str = ""


class InstrumentIn(BaseModel):
    kind: Literal["bond", "share", "etf", "currency", "deposit"]
    name: str = Field(min_length=1, max_length=200)
    ticker: str = ""
    isin: str = ""
    figi: str = ""
    currency: str = "RUB"
    nominal: float = 0
    last_price: float = 0
    nkd: float = 0
    meta: dict = Field(default_factory=dict)


class PriceIn(BaseModel):
    instrument_id: Optional[int] = None
    ticker: Optional[str] = None
    last_price: float = Field(ge=0)
    nkd: Optional[float] = Field(default=None, ge=0)


class DepositIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    principal: float = Field(gt=0, le=1_000_000_000_000)
    open_date: date
    close_date: date
    annual_rate_pct: float = Field(ge=0, le=100)
    interest_mode: Literal["simple", "monthly_capitalization"] = "simple"

    @model_validator(mode="after")
    def validate_dates(self):
        if self.close_date <= self.open_date:
            raise ValueError("close_date must be after open_date")
        return self


class CurrencyHoldingIn(BaseModel):
    code: str = Field(min_length=3, max_length=3)
    quantity: float = Field(gt=0, le=1_000_000_000_000)
    invested_rub: float = Field(gt=0, le=1_000_000_000_000_000)
    acquired_on: date
    name: str = Field(default="", max_length=200)
    rate_rub_per_unit: Optional[float] = Field(default=None, gt=0)
    append: bool = False

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        code = value.strip().upper()
        if len(code) != 3 or not code.isascii() or not code.isalpha():
            raise ValueError("code must be a three-letter ISO-style currency code")
        if code == "RUB":
            raise ValueError("manual RUB cash is managed by T-Invest")
        return code


class TrackingStartIn(BaseModel):
    start_date: date
    confirm: Literal[True]


class BackupRestoreIn(BaseModel):
    filename: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^portfolio-\d{8}-\d{6}(?:-\d+)?\.db$",
    )
    confirm: Literal[True]


class LedgerMutationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(
        min_length=8,
        max_length=80,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,79}$",
        description="Unique idempotency key for this user-confirmed mutation",
    )
    confirm: Literal[True]
    create_snapshot: bool = True


class CashLedgerIn(LedgerMutationIn):
    amount_rub: float = Field(gt=0, le=1_000_000_000_000_000)
    date: date
    note: str = Field(default="", max_length=200)


class DepositOpenLedgerIn(LedgerMutationIn):
    name: str = Field(min_length=1, max_length=200)
    principal: float = Field(gt=0, le=1_000_000_000_000)
    open_date: date
    close_date: date
    annual_rate_pct: float = Field(ge=0, le=100)
    interest_mode: Literal["simple", "monthly_capitalization"] = "simple"
    note: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def validate_deposit_dates(self):
        if self.close_date <= self.open_date:
            raise ValueError("close_date must be after open_date")
        return self


class DepositSettleLedgerIn(LedgerMutationIn):
    instrument: str = Field(min_length=1, max_length=200)
    settled_on: date
    actual_payout_rub: Optional[float] = Field(default=None, gt=0)
    note: str = Field(default="", max_length=200)


class CurrencyBuyLedgerIn(LedgerMutationIn):
    code: str = Field(min_length=3, max_length=3)
    quantity: float = Field(gt=0, le=1_000_000_000_000)
    total_cost_rub: float = Field(gt=0, le=1_000_000_000_000_000)
    traded_on: date
    name: str = Field(default="", max_length=200)
    current_rate: Optional[float] = Field(default=None, gt=0)
    note: str = Field(default="", max_length=200)

    @field_validator("code")
    @classmethod
    def validate_currency_code(cls, value: str) -> str:
        code = value.strip().upper()
        if len(code) != 3 or not code.isascii() or not code.isalpha() or code == "RUB":
            raise ValueError("code must be a non-RUB three-letter currency code")
        return code


class CurrencySellLedgerIn(LedgerMutationIn):
    code: str = Field(min_length=3, max_length=3)
    quantity: float = Field(gt=0, le=1_000_000_000_000)
    total_proceeds_rub: float = Field(gt=0, le=1_000_000_000_000_000)
    traded_on: date
    note: str = Field(default="", max_length=200)

    @field_validator("code")
    @classmethod
    def validate_sell_currency_code(cls, value: str) -> str:
        code = value.strip().upper()
        if len(code) != 3 or not code.isascii() or not code.isalpha() or code == "RUB":
            raise ValueError("code must be a non-RUB three-letter currency code")
        return code


class SecurityTradeLedgerIn(LedgerMutationIn):
    instrument: str = Field(min_length=1, max_length=200)
    quantity: float = Field(gt=0, le=1_000_000_000_000)
    traded_on: date
    commission: float = Field(default=0, ge=0)
    note: str = Field(default="", max_length=200)


class SecurityBuyLedgerIn(SecurityTradeLedgerIn):
    total_cost_rub: float = Field(gt=0, le=1_000_000_000_000_000)


class SecuritySellLedgerIn(SecurityTradeLedgerIn):
    total_proceeds_rub: float = Field(gt=0, le=1_000_000_000_000_000)


class LedgerBatchIn(LedgerMutationIn):
    actions: list[dict] = Field(min_length=1, max_length=50)

    @field_validator("actions")
    @classmethod
    def validate_action_types(cls, actions: list[dict]) -> list[dict]:
        supported = {
            "cash_topup", "cash_withdrawal", "open_deposit", "settle_deposit",
            "buy_currency", "sell_currency", "buy_security", "sell_security",
        }
        for index, action in enumerate(actions):
            if not isinstance(action, dict) or action.get("type") not in supported:
                raise ValueError(f"actions[{index}].type is unsupported")
        return actions
