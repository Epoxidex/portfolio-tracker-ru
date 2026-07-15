import { useCallback, useEffect, useState, type FormEvent } from "react";
import { getCash, getReconciliations, getTransactions, mutate, requestId, type CashBalance, type Reconciliation, type Transaction } from "../api/actions";
import { Field, SelectField, SubmitButton } from "../components/FormFields";
import { PageHeading } from "../components/PageHeading";
import { formatDate, formatMoney } from "../lib/format";

type ActionKind = "cash" | "deposit" | "currency" | "security";
const today = new Date().toISOString().slice(0, 10);

export function OperationsPage({ revision, onChanged }: { revision: number; onChanged: () => Promise<void> }) {
  const [cash, setCash] = useState<CashBalance>({ broker: 0, manual: 0, total: 0 });
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [reconciliations, setReconciliations] = useState<Reconciliation[]>([]);
  const [action, setAction] = useState<ActionKind>("cash");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error?: boolean } | null>(null);

  const load = useCallback(async () => {
    const [nextCash, nextTransactions, pending] = await Promise.all([getCash(), getTransactions(), getReconciliations()]);
    setCash(nextCash); setTransactions(nextTransactions.slice().reverse()); setReconciliations(pending.items);
  }, []);
  useEffect(() => { void load(); }, [load, revision]);

  const perform = async (task: () => Promise<unknown>, success: string) => {
    setBusy(true); setNotice(null);
    try { await task(); setNotice({ text: success }); await load(); await onChanged(); }
    catch (error) { setNotice({ text: error instanceof Error ? error.message : "Операция не выполнена", error: true }); }
    finally { setBusy(false); }
  };

  const settle = (item: Reconciliation) => perform(() => mutate("/ledger/deposits/settle", {
    request_id: requestId("ui-settle"), confirm: true, instrument: `id:${item.instrument_id}`,
    settled_on: today, actual_payout_rub: item.estimated_payout_rub,
  }), `Вклад «${item.name}» закрыт, выплата добавлена в RUB`);

  return (
    <>
      <PageHeading eyebrow="Журнал" title="Операции" subtitle="Ручные деньги, вклады, валюта и бумаги — с обновлением стоимости и прибыли" />
      {notice && <div className={`notice ${notice.error ? "error" : "success"}`}>{notice.text}</div>}
      <section className="cash-strip">
        <CashMetric label="Всего RUB" value={cash.total} /><CashMetric label="Ручные RUB" value={cash.manual} /><CashMetric label="У брокера" value={cash.broker} />
        <span className="cash-note">Ручные покупки расходуют только ручную часть RUB</span>
      </section>
      {reconciliations.length > 0 && <section className="reconciliation-panel"><div><p className="panel-kicker">Требует внимания</p><h2>Завершившиеся активы</h2></div>{reconciliations.map((item) => <article key={item.instrument_id}><span><strong>{item.name}</strong><small>Срок: {formatDate(item.maturity_date)} · {item.kind === "deposit" ? "нужно зачислить выплату" : "нужна синхронизация"}</small></span>{item.kind === "deposit" && <button className="secondary-button" disabled={busy} onClick={() => void settle(item)}>Зачислить {formatMoney(item.estimated_payout_rub ?? 0)}</button>}</article>)}</section>}
      <div className="operations-layout">
        <section className="panel operation-compose">
          <div className="panel-heading"><div><p className="panel-kicker">Новая запись</p><h2>Добавить операцию</h2></div></div>
          <div className="action-picker">{(["cash", "deposit", "currency", "security"] as ActionKind[]).map((item) => <button className={action === item ? "active" : ""} key={item} onClick={() => setAction(item)}>{({ cash: "RUB", deposit: "Вклад", currency: "Валюта", security: "Бумаги" })[item]}</button>)}</div>
          {action === "cash" && <CashForm busy={busy} perform={perform} />}
          {action === "deposit" && <DepositForm busy={busy} perform={perform} />}
          {action === "currency" && <CurrencyForm busy={busy} perform={perform} />}
          {action === "security" && <SecurityForm busy={busy} perform={perform} />}
        </section>
        <section className="panel transaction-panel">
          <div className="panel-heading"><div><p className="panel-kicker">Последние записи</p><h2>История операций</h2></div><span className="panel-meta">{transactions.length}</span></div>
          <div className="transaction-list">{transactions.length ? transactions.slice(0, 80).map((tx) => <article key={tx.id}><time>{formatDate(tx.date)}</time><span><strong>{tx.ticker || tx.instrument || transactionName(tx.kind)}</strong><small>{transactionName(tx.kind)}{tx.quantity ? ` · ${Math.abs(tx.quantity).toLocaleString("ru-RU")}` : ""}</small></span><b className={tx.amount >= 0 ? "positive" : "negative"}>{formatMoney(tx.amount, true)}</b></article>) : <div className="empty-state compact"><strong>Операций пока нет</strong></div>}</div>
        </section>
      </div>
    </>
  );
}

type Perform = (task: () => Promise<unknown>, success: string) => Promise<void>;

function CashForm({ busy, perform }: { busy: boolean; perform: Perform }) {
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); const direction = String(data.get("direction")); void perform(() => mutate(`/ledger/cash/${direction}`, { request_id: requestId("ui-cash"), confirm: true, amount_rub: Number(data.get("amount")), date: data.get("date"), note: data.get("note") }), direction === "topup" ? "Ручные RUB пополнены" : "Вывод RUB записан"); };
  return <form className="operation-form" onSubmit={submit}><SelectField label="Действие" name="direction"><option value="topup">Пополнение</option><option value="withdrawal">Вывод</option></SelectField><Field label="Сумма, ₽" name="amount" type="number" min="0.01" step="0.01" required /><Field label="Дата" name="date" type="date" defaultValue={today} required /><Field label="Комментарий" name="note" maxLength={200} /><SubmitButton busy={busy}>Сохранить RUB</SubmitButton></form>;
}

function DepositForm({ busy, perform }: { busy: boolean; perform: Perform }) {
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); void perform(() => mutate("/deposits", { name: data.get("name"), principal: Number(data.get("principal")), open_date: data.get("open_date"), close_date: data.get("close_date"), annual_rate_pct: Number(data.get("rate")), interest_mode: data.get("mode") }), "Вклад добавлен в портфель"); };
  return <form className="operation-form" onSubmit={submit}><Field label="Название" name="name" required maxLength={200} placeholder="Вклад на 6 месяцев" /><Field label="Сумма, ₽" name="principal" type="number" min="0.01" step="0.01" required /><Field label="Дата открытия" name="open_date" type="date" defaultValue={today} required /><Field label="Дата окончания" name="close_date" type="date" required /><Field label="Ставка, % годовых" name="rate" type="number" min="0" max="100" step="0.01" required hint="Например, 18 — не 0,18" /><SelectField label="Начисление" name="mode"><option value="simple">В конце срока</option><option value="monthly_capitalization">Ежемесячная капитализация</option></SelectField><SubmitButton busy={busy}>Добавить вклад</SubmitButton></form>;
}

function CurrencyForm({ busy, perform }: { busy: boolean; perform: Perform }) {
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); const side = String(data.get("side")); const totalField = side === "buy" ? "total_cost_rub" : "total_proceeds_rub"; void perform(() => mutate(`/ledger/currencies/${side}`, { request_id: requestId("ui-fx"), confirm: true, code: String(data.get("code")).toUpperCase(), quantity: Number(data.get("quantity")), [totalField]: Number(data.get("total")), traded_on: data.get("date"), current_rate: side === "buy" && data.get("rate") ? Number(data.get("rate")) : undefined, note: data.get("note") }), side === "buy" ? "Покупка валюты записана" : "Продажа валюты записана"); };
  return <form className="operation-form" onSubmit={submit}><SelectField label="Действие" name="side"><option value="buy">Купить</option><option value="sell">Продать</option></SelectField><Field label="Код валюты" name="code" minLength={3} maxLength={3} required placeholder="USD" /><Field label="Количество" name="quantity" type="number" min="0.0001" step="any" required /><Field label="Итого, ₽" name="total" type="number" min="0.01" step="0.01" required /><Field label="Текущий курс (необязательно)" name="rate" type="number" min="0.0001" step="any" /><Field label="Дата сделки" name="date" type="date" defaultValue={today} required /><Field label="Комментарий" name="note" maxLength={200} /><SubmitButton busy={busy}>Записать валюту</SubmitButton></form>;
}

function SecurityForm({ busy, perform }: { busy: boolean; perform: Perform }) {
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); const side = String(data.get("side")); const totalField = side === "buy" ? "total_cost_rub" : "total_proceeds_rub"; void perform(() => mutate(`/ledger/securities/${side}`, { request_id: requestId("ui-security"), confirm: true, instrument: data.get("instrument"), quantity: Number(data.get("quantity")), [totalField]: Number(data.get("total")), commission: Number(data.get("commission") || 0), traded_on: data.get("date"), note: data.get("note") }), side === "buy" ? "Покупка бумаги записана" : "Продажа бумаги записана"); };
  return <form className="operation-form" onSubmit={submit}><SelectField label="Действие" name="side"><option value="buy">Купить</option><option value="sell">Продать</option></SelectField><Field label="Тикер, ISIN или название" name="instrument" required /><Field label="Количество" name="quantity" type="number" min="0.0001" step="any" required /><Field label="Итого, ₽" name="total" type="number" min="0.01" step="0.01" required /><Field label="Комиссия, ₽" name="commission" type="number" min="0" step="0.01" defaultValue="0" /><Field label="Дата сделки" name="date" type="date" defaultValue={today} required /><Field label="Комментарий" name="note" maxLength={200} /><SubmitButton busy={busy}>Записать бумагу</SubmitButton></form>;
}

function CashMetric({ label, value }: { label: string; value: number }) { return <div><span>{label}</span><strong>{formatMoney(value)}</strong></div>; }
function transactionName(kind: string) { return ({ buy: "Покупка", sell: "Продажа", fx_buy: "Покупка валюты", fx_sell: "Продажа валюты", coupon: "Купон", dividend: "Дивиденд", interest: "Проценты", topup: "Пополнение", withdrawal: "Вывод" } as Record<string, string>)[kind] || kind; }
