import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Alert, Badge, Button, Group, Paper, SegmentedControl, SimpleGrid, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconAlertTriangle, IconBuildingBank, IconCash, IconCircleCheck, IconCoins, IconPigMoney } from "@tabler/icons-react";
import { getCash, getReconciliations, getTransactions, mutate, requestId, type CashBalance, type Reconciliation, type Transaction } from "../api/actions";
import { Field, SelectField, SubmitButton } from "../components/FormFields";
import { PageHeading } from "../components/PageHeading";
import { formatDate, formatMoney, todayInMoscow } from "../lib/format";

type ActionKind = "cash" | "deposit" | "currency" | "security";
const today = todayInMoscow();

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

  const settle = (item: Reconciliation) => {
    const entered = window.prompt(
      `Укажите фактическую выплату по вкладу «${item.name}», ₽`,
      String(item.estimated_payout_rub ?? ""),
    );
    if (entered === null) return;
    const actualPayout = Number(entered.replace(",", "."));
    if (!Number.isFinite(actualPayout) || actualPayout <= 0) {
      setNotice({ text: "Фактическая выплата должна быть положительным числом", error: true });
      return;
    }
    void perform(() => mutate("/ledger/deposits/settle", {
      request_id: requestId("ui-settle"), confirm: true, instrument: `id:${item.instrument_id}`,
      settled_on: today, actual_payout_rub: actualPayout,
    }), `Вклад «${item.name}» закрыт, выплата добавлена в RUB`);
  };

  return (
    <>
      <PageHeading eyebrow="Журнал" title="Операции" subtitle="Движение денег, вклады, валюта и бумаги — с прозрачным влиянием на портфель" />
      {notice && <Alert mb="md" color={notice.error ? "red" : "teal"} icon={notice.error ? <IconAlertTriangle size={18}/> : <IconCircleCheck size={18}/>} radius="lg">{notice.text}</Alert>}
      <SimpleGrid cols={{base:1,xs:3}} spacing="md" mb="md">
        <CashMetric label="Всего RUB" value={cash.total} icon={IconCash} color="indigo" />
        <CashMetric label="Ручные RUB" value={cash.manual} icon={IconCoins} color="teal" />
        <CashMetric label="У брокера" value={cash.broker} icon={IconBuildingBank} color="blue" />
      </SimpleGrid>
      <Alert mb="md" color="gray" variant="light" radius="lg" icon={<IconCash size={18}/>}>Ручные покупки расходуют только ручную часть RUB. Баланс брокера меняется после синхронизации T‑Invest.</Alert>
      {reconciliations.length > 0 && <Paper withBorder radius="lg" p="lg" mb="md" className="attention-card"><Group mb="sm"><ThemeIcon color="orange" variant="light"><IconAlertTriangle size={18}/></ThemeIcon><div><Text className="section-kicker">Требует внимания</Text><Title order={3}>Завершившиеся активы</Title></div></Group><Stack gap={0}>{reconciliations.map(item=><Group className="reconciliation-row" key={item.instrument_id} justify="space-between"><div><Text size="sm" fw={700}>{item.name}</Text><Text size="xs" c="dimmed">Срок: {formatDate(item.maturity_date)} · {item.kind==="deposit"?"нужно зачислить выплату":"нужна синхронизация"}</Text></div>{item.kind==="deposit"&&<Button variant="light" color="orange" disabled={busy} onClick={()=>void settle(item)}>Зачислить {formatMoney(item.estimated_payout_rub??0)}</Button>}</Group>)}</Stack></Paper>}
      <div className="operations-layout">
        <Paper withBorder radius="xl" p={{base:"md",md:"xl"}}>
          <Text className="section-kicker">Новая запись</Text><Title order={3}>Добавить операцию</Title>
          <SegmentedControl fullWidth mt="lg" mb="xl" value={action} onChange={value=>setAction(value as ActionKind)} data={[{value:"cash",label:"RUB"},{value:"deposit",label:"Вклад"},{value:"currency",label:"Валюта"},{value:"security",label:"Бумаги"}]}/>
          {action === "cash" && <CashForm busy={busy} perform={perform} />}
          {action === "deposit" && <DepositForm busy={busy} perform={perform} />}
          {action === "currency" && <CurrencyForm busy={busy} perform={perform} />}
          {action === "security" && <SecurityForm busy={busy} perform={perform} />}
        </Paper>
        <Paper withBorder radius="xl" p={{base:"md",md:"xl"}}>
          <Group justify="space-between"><div><Text className="section-kicker">Последние записи</Text><Title order={3}>История операций</Title></div><Badge variant="light">{transactions.length}</Badge></Group>
          <Stack gap={0} mt="lg" className="transaction-modern-list">{transactions.length?transactions.slice(0,80).map(tx=><Group className="transaction-modern-row" key={tx.id} justify="space-between" wrap="nowrap"><Group wrap="nowrap"><div className={`transaction-icon ${tx.amount>=0?"in":"out"}`}>{tx.amount>=0?"+":"−"}</div><div><Text size="sm" fw={700}>{tx.ticker||tx.instrument||transactionName(tx)}</Text><Text size="xs" c="dimmed">{formatDate(tx.date)} · {transactionName(tx)}{tx.quantity?` · ${Math.abs(tx.quantity).toLocaleString("ru-RU")}`:""}</Text></div></Group><Text size="sm" fw={750} c={tx.amount>=0?"teal.7":"red.6"}>{formatMoney(tx.amount,true)}</Text></Group>):<Text c="dimmed" ta="center" py={60}>Операций пока нет</Text>}</Stack>
        </Paper>
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

function CashMetric({ label, value, icon: Icon, color }: { label: string; value: number; icon: typeof IconCash; color: string }) { return <Paper withBorder radius="lg" p="lg"><Group wrap="nowrap"><ThemeIcon size={42} radius="md" variant="light" color={color}><Icon size={20}/></ThemeIcon><div><Text size="xs" c="dimmed" fw={650}>{label}</Text><Text size="xl" fw={780}>{formatMoney(value)}</Text></div></Group></Paper>; }
function transactionName(tx: Transaction) {
  const note = tx.note ?? "";
  if (note.includes(":rub-to-deposit")) return "Перевод RUB во вклад";
  if (note.includes(":deposit-to-rub")) return "Выплата вклада в RUB";
  if (note.includes(":rub-to-currency")) return "Перевод RUB в валюту";
  if (note.includes(":currency-to-rub")) return "Продажа валюты в RUB";
  if (note.includes(":rub-to-security")) return "Перевод RUB в бумаги";
  if (note.includes(":security-to-rub")) return "Продажа бумаг в RUB";
  return ({ buy: "Покупка", sell: "Продажа", fx_buy: "Покупка валюты", fx_sell: "Продажа валюты", coupon: "Купон", dividend: "Дивиденд", interest: "Проценты", topup: "Пополнение", withdrawal: "Вывод" } as Record<string, string>)[tx.kind] || tx.kind;
}
