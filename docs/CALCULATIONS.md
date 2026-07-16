# How calculations work

This application is a personal dashboard, not a broker report or accounting system. The rules below are explicit so the numbers can be audited.

## Positions and P&L

- Securities and foreign currency use a moving weighted-average cost basis. A sale realizes the difference between its proceeds and the released average cost; a later purchase starts from the remaining cost basis. For a T-Invest position, the broker quantity is authoritative, while cost comes from recorded operations when they explain that quantity. If the imported history is incomplete, the broker average price is used instead. Current market value and `expected_yield` never redefine historical cost.
- Bond value includes the current clean price plus accrued coupon income (НКД).
- Position P&L is unrealized P&L plus recorded coupons/dividends and moving-average realized P&L. The portfolio headline uses external-capital accounting instead: current value plus factual external withdrawals minus factual external contributions. Selling, settling, or reinvesting inside the portfolio therefore does not reset or increase lifetime profit.
- Fully closed positions are not shown in the active positions table. This means the dashboard is primarily a view of the current portfolio, not a lifetime tax ledger.
- `lifetime_results` separately retains recorded coupons, dividends, deposit interest and moving-average realized P&L for closed as well as active assets. It is still an estimate when imported broker history starts after the true acquisition date.
- `invested` means gross money contributed from outside the portfolio, not the current cost basis of its assets. Position rows expose that different concept as `cost_basis` (and retain `invested` as a compatibility alias).
- XIRR is calculated from external contributions, external withdrawals, and the current total portfolio value. Treat XIRR as an estimate when imported broker history is incomplete.

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

Only cash rows identified as external funding or withdrawal affect portfolio
`invested` and headline lifetime P&L. Deposit settlements, security sales,
coupon/dividend payments and subsequent purchases are internal movements. For
legacy local rows and broker histories without explicit cash inputs, the app
infers the smallest outside contribution needed to fund the recorded cash
outflows. The summary reports that inferred portion separately.

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

### Bond coupon schedules

An exact user-supplied coupon schedule takes precedence over the legacy estimate
based on one coupon amount, payment frequency and next coupon date. Each schedule
row stores a payment date and the expected coupon in RUB per bond. The calendar
multiplies it by the current quantity, so a later purchase, sale or T-Invest
position synchronization changes all future expected totals automatically.

The optional maturity date creates a separate nominal-repayment event. Schedule
entries are forecasts only: they do not create income transactions or RUB. An
actual coupon is recorded separately, normally by T-Invest synchronization. A
manual schedule can therefore enrich a T-Invest instrument without pretending
that a broker trade or payment occurred.

## Data-source limitations

- T-Invest synchronization imports the operation types the application understands: cash inputs/outputs, buys, sells, coupons, dividends and bond repayments. Taxes, fees, securities transfers and some corporate actions are not yet a complete accounting model.
- T-Bank itself recommends a broker report when operation history must be exact; some corporate-action history can be incomplete in the API.
- Future coupon/dividend calendars require instrument metadata. A newly discovered instrument can have a price and transaction history before its future-payment metadata is available. An exact bond schedule can be supplied through REST or MCP until automatic source data is available.
- The official CBR rate is the default currency source. `bank_buy` and `bank_sell` scrape one configured third-party bank page and can stop working when that page changes.
- Automatic snapshots exist only while the application is running. Missing reference periods intentionally produce no comparison.
- Monetary values currently use floating-point numbers. This is sufficient for a dashboard but not for tax-grade kopek reconciliation.
