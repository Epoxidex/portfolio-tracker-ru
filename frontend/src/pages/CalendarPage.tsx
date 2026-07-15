import { useEffect, useMemo, useState } from "react";
import { getCalendar, getPassiveIncome, type CalendarEvent, type PassiveIncome } from "../api/dashboard";
import { PageHeading } from "../components/PageHeading";
import { formatDate, formatMoney, todayInMoscow } from "../lib/format";

const eventTone: Record<string, string> = { "Купон": "teal", "Проценты": "gold", "Дивиденд": "violet", "Погашение": "blue", "Возврат вклада": "blue" };

export function CalendarPage({ revision }: { revision: number }) {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [income, setIncome] = useState<PassiveIncome>({ annual: 0, monthly: 0, detail: [] });
  const [showPast, setShowPast] = useState(false);
  useEffect(() => { void Promise.all([getCalendar(), getPassiveIncome()]).then(([calendar, passive]) => { setEvents(calendar); setIncome(passive); }); }, [revision]);
  const today = todayInMoscow();
  const visible = useMemo(() => events.filter((event) => showPast || event.date >= today), [events, showPast, today]);
  const groups = useMemo(() => Object.entries(visible.reduce<Record<string, CalendarEvent[]>>((acc, event) => { const key = event.date.slice(0, 7); (acc[key] ??= []).push(event); return acc; }, {})), [visible]);
  const upcoming = visible.filter((event) => event.date >= today).slice(0, 5).reduce((sum, event) => sum + event.amount, 0);

  return (
    <>
      <PageHeading eyebrow="Денежный поток" title="Календарь выплат" subtitle="Купоны, дивиденды, проценты, возвраты вкладов и погашения" actions={<label className="toggle-label"><input type="checkbox" checked={showPast} onChange={(event) => setShowPast(event.target.checked)} /> Прошедшие</label>} />
      <section className="income-hero">
        <div><p className="panel-kicker">Ожидается в ближайших событиях</p><strong>{formatMoney(upcoming)}</strong><span>{visible.filter((event) => event.date >= today).length} будущих выплат</span></div>
        <div><p className="panel-kicker">Пассивный доход</p><strong>{formatMoney(income.monthly)}<small>/мес</small></strong><span>{formatMoney(income.annual)} в год</span></div>
      </section>
      <div className="calendar-layout">
        <section className="panel calendar-timeline">
          <div className="panel-heading"><div><p className="panel-kicker">Хронология</p><h2>Все события</h2></div><span className="panel-meta">{visible.length}</span></div>
          {groups.length ? groups.map(([month, items]) => <div className="month-group" key={month}><h3>{new Intl.DateTimeFormat("ru-RU", { month: "long", year: "numeric" }).format(new Date(`${month}-01T00:00:00`))}</h3>{items.map((event, index) => <article className="payment-row" key={`${event.date}-${event.instrument}-${index}`}><time>{formatDate(event.date)}</time><i className={`event-dot tone-${eventTone[event.type] || "teal"}`} /><span><strong>{event.instrument}</strong><small>{event.type}</small></span><b>{formatMoney(event.amount)}</b></article>)}</div>) : <div className="chart-empty">В выбранном периоде выплат нет</div>}
        </section>
        <aside className="panel income-detail"><div className="panel-heading"><div><p className="panel-kicker">Run-rate</p><h2>Источники дохода</h2></div></div>{income.detail.length ? income.detail.sort((a, b) => b.annual - a.annual).map((item) => <div className="income-source" key={item.name}><span><strong>{item.name}</strong><small>{formatMoney(item.annual / 12)} в месяц</small></span><b>{formatMoney(item.annual)}</b></div>) : <div className="empty-state compact"><strong>Пассивного дохода пока нет</strong></div>}</aside>
      </div>
    </>
  );
}
