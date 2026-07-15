# How calculations work

This application is a personal dashboard, not a broker report or accounting system. The rules below are explicit so the numbers can be audited.

## Positions and P&L

- Securities and foreign currency use a moving weighted-average cost basis. A sale realizes the difference between its proceeds and the released average cost; a later purchase starts from the remaining cost basis.
- Bond value includes the current clean price plus accrued coupon income (НКД).
- Current P&L is unrealized P&L plus recorded coupons/dividends and realized P&L for positions that remain open.
- Fully closed positions are not shown in the active positions table. This means the dashboard is primarily a view of the current portfolio, not a lifetime tax ledger.
- `lifetime_results` separately retains recorded coupons, dividends, deposit interest and moving-average realized P&L for closed as well as active assets. It is still an estimate when imported broker history starts after the true acquisition date.
- XIRR is calculated from instrument cash flows and the current terminal value of invested assets. Ruble cash from T-Invest is excluded from the terminal value to avoid counting sale proceeds twice. Treat XIRR as an estimate, especially when the imported operation history is incomplete.

## Ruble cash and internal transfers

RUB is split into two components: the broker-authoritative T-Invest balance and
the manual local cash ledger. The displayed RUB position is their sum, but a
manual bank deposit, currency purchase or manual security purchase can spend
only manual RUB. This prevents a local operation from pretending that money was
withdrawn from the broker when T-Invest still reports it there.

Manual `topup` and `withdrawal` rows are audit entries for the RUB balance.
Transfers between RUB and another asset create matching rows on both sides. For
example, buying USD subtracts the all-in RUB cost and creates `fx_buy`; selling
USD creates `fx_sell` and adds the net factual proceeds to RUB. RUB ledger rows
are excluded from XIRR and period-leader calculations so an internal transfer
does not look like investment performance.

## Day, week and month changes

Snapshots are converted to Moscow calendar dates; only the last snapshot of each date is used.
Snapshots earlier than `PORTFOLIO_TRACKING_START_DATE` are excluded. T-Invest
operation import is capped at the same date, while current active quantities are
reconciled against the broker's current portfolio. The boundary does not delete
manual deposits or currency holdings and does not rewrite the broker's cost basis
for an asset already held on that date.

- **Day:** current last snapshot versus the last snapshot of the immediately preceding calendar day.
- **Week:** current last snapshot versus the last available snapshot inside the preceding Monday–Sunday week.
- **Month:** current last snapshot versus the last available snapshot inside the preceding calendar month.

If the required previous period has no snapshot, the UI shows that there is no reference snapshot instead of inventing a comparison. Changes compare stored market values instrument by instrument and offset recorded buys and sells during the window. The ruble cash balance is excluded, so a transfer to the brokerage account does not look like investment performance. A broker-side correction of average cost or expected yield also does not masquerade as a market movement.

The leaders list uses the same reference periods and the same calculation as the headline change. Its signed ruble contributions therefore add up to the headline value. Items are sorted by the absolute ruble impact on the portfolio.

## Deposits

New deposits store the annual rate as a decimal internally, while the UI accepts a familiar percentage such as `18`.

- **At maturity, without capitalization:** simple daily accrual, `principal × annual rate × days / 365`.
- **Monthly capitalization:** the entered nominal annual rate is divided by 12 for complete months; a remaining partial month accrues daily.
- Old deposits that have no `interest_mode` keep the previous effective-annual monthly model for backward compatibility.

The estimate is before taxes. Banks may use a different day-count convention, rounding rule, changing rate or early-termination rule; compare the result with the deposit agreement.

After the maturity date, a deposit remains in the current portfolio at its capped
estimated closing value and is reported by `pending_reconciliations`. Settlement
is explicit because the bank can round differently, withhold tax or apply an
early-termination rule. Settling records return of principal and the difference
between principal and actual payout, closes the deposit, and credits manual RUB.
For a normal maturity the user may explicitly accept the estimate; an early
closure always requires the factual payout.

## Securities and T-Invest lifecycle

T-Invest securities are broker-authoritative. Manual ledger tools reject their
buys and sells. After a broker trade or bond repayment, synchronization imports
the supported operation, reconciles the current quantity and cost data, updates
the broker RUB balance and takes a snapshot. Bond repayment is represented as a
sale for the repaid amount. Securities that are genuinely tracked outside
T-Invest can use the manual buy/sell ledger and the same moving-average cost rule.

## Data-source limitations

- T-Invest synchronization imports the operation types the application understands: buys, sells, coupons, dividends and bond repayments. Taxes, fees and some corporate actions are not yet a complete accounting model.
- T-Bank itself recommends a broker report when operation history must be exact; some corporate-action history can be incomplete in the API.
- Future coupon/dividend calendars require instrument metadata. A newly discovered instrument can have a price and transaction history before its future-payment metadata is available.
- The official CBR rate is the default currency source. `bank_buy` and `bank_sell` scrape one configured third-party bank page and can stop working when that page changes.
- Automatic snapshots exist only while the application is running. Missing reference periods intentionally produce no comparison.
- Monetary values currently use floating-point numbers. This is sufficient for a dashboard but not for tax-grade kopek reconciliation.
