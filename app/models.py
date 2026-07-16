from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .db import Base


class Instrument(Base):
    __tablename__ = "instruments"
    id = Column(Integer, primary_key=True)
    kind = Column(String, nullable=False)        # bond | share | etf | currency | deposit
    name = Column(String, nullable=False)
    ticker = Column(String, default="")
    isin = Column(String, default="")
    figi = Column(String, default="")
    currency = Column(String, default="RUB")     # валюта инструмента (для currency-позиции = код валюты)
    nominal = Column(Float, default=0.0)         # номинал облигации
    last_price = Column(Float, default=0.0)      # текущая чистая цена (₽); для currency = курс продажи (₽ за единицу)
    nkd = Column(Float, default=0.0)             # НКД на единицу (облигации)
    price_updated_at = Column(DateTime)
    meta = Column(JSON, default=dict)            # coupon_per_unit, payments_per_year, ytm, maturity,
                                                 # next_coupon, principal, open_date, close_date, eff_rate, div_per_year...
    transactions = relationship("Transaction", back_populates="instrument", cascade="all, delete-orphan")


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    ts = Column(Date, nullable=False)
    instrument_id = Column(Integer, ForeignKey("instruments.id"))
    kind = Column(String, nullable=False)        # buy/sell/income/fx_buy/fx_sell/topup/withdrawal
    quantity = Column(Float, default=0.0)        # >0 всегда
    price = Column(Float, default=0.0)
    amount = Column(Float, default=0.0)          # ЗНАКОВЫЙ денежный поток из «кармана инвестиций»:
                                                 #   покупка/открытие вклада < 0, продажа/купон/дивиденд/% > 0
    commission = Column(Float, default=0.0)
    note = Column(String, default="")
    instrument = relationship("Instrument", back_populates="transactions")


class PriceHistory(Base):
    __tablename__ = "price_history"
    id = Column(Integer, primary_key=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id"), nullable=False)
    ts = Column(DateTime, default=datetime.utcnow, index=True)
    price = Column(Float, nullable=False)
    instrument = relationship("Instrument")


class Snapshot(Base):
    __tablename__ = "snapshots"
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, default=datetime.utcnow, index=True)
    total_value = Column(Float, default=0.0)
    total_invested = Column(Float, default=0.0)
    total_pnl = Column(Float, default=0.0)
    income_received = Column(Float, default=0.0)
    by_class = Column(JSON, default=dict)
    by_instrument = Column(JSON, default=dict)
    source = Column(String, default="auto")


class MutationRequest(Base):
    """Idempotency record for local metadata mutations that create no cash flow."""

    __tablename__ = "mutation_requests"
    request_id = Column(String, primary_key=True)
    action_type = Column(String, nullable=False)
    result = Column(JSON, default=dict)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )
