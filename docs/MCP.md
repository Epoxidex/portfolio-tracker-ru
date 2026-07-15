# MCP-сервер Portfolio Tracker

Проект содержит локальный MCP-сервер для чтения и контролируемой записи данных
портфеля. Он не умеет совершать сделки или выводить деньги у брокера: токен
T-Invest остаётся read-only. Write-tools изменяют только локальную SQLite.

Сервер использует `stdio`: отдельный сетевой порт не открывается. Клиент запускает
локальный Python-процесс и общается с ним через стандартный ввод-вывод. При этом
ответы MCP содержат личные финансовые данные, поэтому подключайте сервер только к
доверенному локальному клиенту.

## Что доступно

Read-tools:

- `get_data_status` — безопасный статус конфигурации и наполнения базы;
- `get_portfolio_overview` — текущая стоимость, вложения, P&L, XIRR, цель,
  распределение и активные позиции;
- `list_positions` — фильтрация, сортировка и пагинация активных позиций;
- `list_instruments` — полный справочник, включая закрытые позиции;
- `get_instrument` — карточка инструмента, операции и история цены;
- `list_transactions` — операции и денежные потоки по датам, типу и инструменту;
- `get_portfolio_history` — дневные или все исходные снимки;
- `get_price_history` — цены одного или всех инструментов;
- `get_returns` — дневная, месячная или годовая доходность;
- `get_change_leaders` — вклад позиций в изменение за день, неделю или месяц;
- `get_payment_calendar` — купоны, дивиденды, проценты и погашения;
- `get_passive_income` — годовой и среднемесячный run-rate дохода;
- `get_rub_cash` — брокерские, ручные и суммарные рубли;
- `get_lifetime_results` — реализованный P&L и выплаты, включая закрытые активы;
- `get_pending_reconciliations` — завершившиеся вклады и облигации, ожидающие
  закрытия или синхронизации;
- `search_portfolio` — общий поиск по инструментам, позициям и операциям;
- `get_portfolio_context` — единый пакет данных для комплексного анализа;
- `get_calculation_methodology` — правила расчётов и ограничения точности;
- `get_data_dictionary` — сущности, поля, типы, единицы и знаки денежных потоков.

Write-tools:

- `top_up_rub_cash` и `withdraw_rub_cash` — внешнее пополнение или вывод ручных рублей;
- `open_deposit_with_cash` — открытие вклада с атомарным списанием RUB;
- `settle_deposit_to_rub` — закрытие вклада и зачисление выплаты в RUB;
- `buy_manual_currency` и `sell_manual_currency` — ручные валютные сделки;
- `buy_manual_security` и `sell_manual_security` — сделки с бумагами вне T-Invest;
- `set_bond_coupon_schedule` — точный локальный график купонов и погашения
  облигации, включая бумаги из T-Invest;
- `apply_portfolio_actions` — атомарный пакет до 50 связанных действий;
- `synchronize_tinvest` — импорт операций, текущих позиций, RUB и цен из read-only API.

Каждая локальная операция записи требует `confirm=true` и уникальный
`request_id` длиной 8–80 символов. Повтор с тем же `request_id` возвращает
`already_applied=true` и не создаёт дубликат. Если одно действие составного
пакета завершилось ошибкой, весь пакет откатывается.

Пример для фразы «внёс 50 000 ₽ и сразу открыл вклад»:

```json
{
  "request_id": "deposit-20260715-001",
  "confirm": true,
  "actions": [
    {"type": "cash_topup", "amount_rub": 50000, "date": "2026-07-15"},
    {
      "type": "open_deposit",
      "name": "Вклад на год",
      "principal": 50000,
      "open_date": "2026-07-15",
      "close_date": "2027-07-15",
      "annual_rate_pct": 16,
      "interest_mode": "monthly_capitalization"
    }
  ]
}
```

Пример для фразы «добавь график купонов по облигации»:

```json
{
  "request_id": "coupon-schedule-20260715-001",
  "instrument": "RU000EXAMPLE",
  "confirm": true,
  "mode": "replace",
  "payments": [
    {"payment_date": "2026-10-15", "coupon_per_unit_rub": 42.5},
    {"payment_date": "2027-01-15", "coupon_per_unit_rub": 42.5}
  ],
  "maturity_date": "2027-01-15",
  "nominal_per_unit_rub": 1000
}
```

`coupon_per_unit_rub` — ожидаемая сумма на одну облигацию. Календарь умножает
её на актуальное количество бумаг, поэтому после синхронизации покупки или
продажи прогноз автоматически меняется. `replace` полностью заменяет график,
а `upsert` добавляет новые даты и обновляет совпавшие. Пустой `replace` очищает
ручной график. Это прогноз: фактически полученный купон по-прежнему записывается
отдельной операцией или импортируется из T-Invest.

Также доступны ресурсы `portfolio://status`, `portfolio://summary`,
`portfolio://positions`, `portfolio://income`, `portfolio://cash`,
`portfolio://lifetime-results`, `portfolio://reconciliations`,
`portfolio://methodology`, `portfolio://data-dictionary` и шаблон
`portfolio://instrument/{identifier}`. MCP-аннотации различают read-only tools,
локальные идемпотентные write-tools и сетевую синхронизацию T-Invest.

## Правила безопасной записи

- Модель не должна вызывать write-tool для гипотетического вопроса «что будет,
  если…». Нужна явная команда пользователя внести конкретную операцию.
- Связанные действия передаются одним `apply_portfolio_actions`, чтобы не оставить
  половину операции в базе.
- Ручные активы расходуют только ручную часть RUB. Брокерские рубли нельзя
  потратить на банковский вклад без фактического вывода из T-Invest и последующего
  ручного пополнения.
- Бумаги с источником `tinvest` нельзя покупать или продавать ручными tools.
  Сделка сначала совершается у брокера, затем вызывается `synchronize_tinvest`.
- Для досрочного закрытия вклада обязательна фактическая сумма выплаты. После
  даты окончания можно принять расчётную сумму, но ответ пометит её как estimate.

## REST ledger endpoints

Те же операции доступны локальному интерфейсу и скриптам через REST:

- `GET /api/ledger/cash`, `/api/ledger/realized` и
  `/api/ledger/reconciliations`;
- `POST /api/ledger/cash/topup` и `/api/ledger/cash/withdrawal`;
- `POST /api/ledger/deposits/open` и `/api/ledger/deposits/settle`;
- `POST /api/ledger/currencies/buy` и `/api/ledger/currencies/sell`;
- `POST /api/ledger/securities/buy` и `/api/ledger/securities/sell`;
- `POST /api/ledger/actions` для атомарного пакета;
- `PUT /api/bonds/coupon-schedule` для точного графика купонов и погашения.

Каждая мутация принимает `request_id` и буквальное `confirm: true`. Денежные
POST-запросы также принимают необязательный `create_snapshot`. Поля конкретного
действия совпадают с параметрами MCP tools.

## Установка и локальная проверка

После создания виртуального окружения установите зависимости и инициализируйте
приложение обычным способом:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.cli init
```

Для ручной проверки протокола можно использовать официальный MCP Inspector:

```powershell
npx -y @modelcontextprotocol/inspector .\.venv\Scripts\python.exe .\mcp_server.py
```

`init` нужен только для новой пустой установки. Для существующей установки не
заменяйте `.env` и базу и не запускайте `demo --replace`.

## Подключение к Codex

В Codex Desktop откройте **Settings → MCP servers → Add server**, выберите
`STDIO`, укажите полный путь к Python из `.venv` как команду, а полный путь к
`mcp_server.py` как аргумент. После сохранения перезапустите Codex.

Ту же настройку можно добавить в личный `~/.codex/config.toml` или в локальный
`.codex/config.toml` доверенного проекта:

```toml
[mcp_servers.portfolio_tracker]
command = "<PROJECT>\\.venv\\Scripts\\python.exe"
args = ["<PROJECT>\\mcp_server.py"]
startup_timeout_sec = 15.0
tool_timeout_sec = 60.0
```

На macOS/Linux используйте `<PROJECT>/.venv/bin/python` и прямые слеши. Не
добавляйте токен T-Invest, ID счёта или содержимое `.env` в конфигурацию MCP:
сервер сам читает локальный `.env` проекта и никогда не возвращает секреты через
`get_data_status`.

## Границы точности

MCP использует те же сервисы расчётов, что локальный REST API и интерфейс. Это личный
дашборд, а не брокерский или налоговый отчёт. Полные правила находятся в
[`CALCULATIONS.md`](CALCULATIONS.md) и доступны самому MCP как methodology.
