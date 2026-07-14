from pydantic import BaseModel, Field, field_validator, model_validator
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
