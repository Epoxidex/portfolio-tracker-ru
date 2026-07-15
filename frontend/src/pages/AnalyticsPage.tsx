import { useEffect, useMemo, useState, type ReactNode } from "react";
import { getHistory, getLeaders, getPriceHistory, getReturns, type HistoryPoint, type Leader, type PriceSeries, type ReturnPoint } from "../api/dashboard";
import { BarChart, LineChart } from "../components/Charts";
import { PageHeading } from "../components/PageHeading";
import { formatMoney, formatPercent } from "../lib/format";

export function AnalyticsPage({ revision }: { revision: number }) {
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [returns, setReturns] = useState<ReturnPoint[]>([]);
  const [leaders, setLeaders] = useState<Leader[]>([]);
  const [series, setSeries] = useState<PriceSeries[]>([]);
  const [returnPeriod, setReturnPeriod] = useState<"daily" | "monthly" | "yearly">("monthly");
  const [leaderPeriod, setLeaderPeriod] = useState<"day" | "week" | "month">("month");
  const [priceId, setPriceId] = useState<number | null>(null);

  useEffect(() => { void getHistory().then(setHistory); void getPriceHistory(365).then((items) => { setSeries(items); setPriceId((current) => current ?? items[0]?.id ?? null); }); }, [revision]);
  useEffect(() => { void getReturns(returnPeriod).then((data) => setReturns(data.points)); }, [returnPeriod, revision]);
  useEffect(() => { void getLeaders(leaderPeriod).then((data) => setLeaders(data.items)); }, [leaderPeriod, revision]);
  const selected = useMemo(() => series.find((item) => item.id === priceId), [series, priceId]);

  return (
    <>
      <PageHeading eyebrow="Динамика" title="Аналитика" subtitle="Снимки, доходность, лидеры движения и история рыночных цен" />
      <div className="content-grid two-columns">
        <ChartPanel title="Стоимость портфеля" kicker="По снимкам" controls={<span className="chart-legend"><i className="gold-dot" />Стоимость <i className="blue-dot" />Вложено</span>}>
          <LineChart labels={history.map((item) => item.day || item.ts.slice(0, 10))} lines={[{ values: history.map((item) => item.value), color: "#f6c760" }, { values: history.map((item) => item.invested), color: "#70a9ff" }]} empty="График появится после первого снимка" />
        </ChartPanel>
        <ChartPanel title="Доходность" kicker="Периоды" controls={<Segmented value={returnPeriod} values={["daily", "monthly", "yearly"]} labels={["Дни", "Месяцы", "Годы"]} onChange={(value) => setReturnPeriod(value as typeof returnPeriod)} />}>
          <BarChart values={returns.map((item) => item.pct)} labels={returns.map((item) => item.label)} empty="Нужно минимум два снимка" />
        </ChartPanel>
        <section className="panel wide-panel">
          <div className="panel-heading"><div><p className="panel-kicker">Вклад в изменение</p><h2>Лидеры движения</h2></div><Segmented value={leaderPeriod} values={["day", "week", "month"]} labels={["День", "Неделя", "Месяц"]} onChange={(value) => setLeaderPeriod(value as typeof leaderPeriod)} /></div>
          <div className="leaders-modern">
            {leaders.length ? leaders.sort((a, b) => Math.abs(b.change) - Math.abs(a.change)).map((item, index) => (
              <div className="leader-modern" key={`${item.name}-${index}`}><span className="leader-index">{String(index + 1).padStart(2, "0")}</span><span className="leader-name"><strong>{item.ticker || item.name}</strong><small>{item.ticker ? item.name : ""}</small></span><span><strong>{formatMoney(item.value)}</strong><small>{item.change_pct === null ? "новая позиция" : formatPercent(item.change_pct)}</small></span><span className={item.change >= 0 ? "positive" : "negative"}><strong>{formatMoney(item.change, true)}</strong><small>{formatPercent(item.impact_pct, false)} движения</small></span></div>
            )) : <div className="chart-empty">Нет изменений за выбранный период</div>}
          </div>
        </section>
        <section className="panel wide-panel">
          <div className="panel-heading"><div><p className="panel-kicker">Рынок</p><h2>История цен</h2></div><select className="compact-select" value={priceId ?? ""} onChange={(event) => setPriceId(Number(event.target.value))}><option value="">Выберите инструмент</option>{series.map((item) => <option value={item.id} key={item.id}>{item.ticker || item.name}</option>)}</select></div>
          <LineChart labels={(selected?.history ?? []).map((item) => item.ts.slice(0, 10))} lines={[{ values: (selected?.history ?? []).map((item) => item.price), color: "#55d99b" }]} empty="История цены выбранного инструмента пока отсутствует" />
        </section>
      </div>
    </>
  );
}

function ChartPanel({ title, kicker, controls, children }: { title: string; kicker: string; controls: ReactNode; children: ReactNode }) {
  return <section className="panel chart-panel"><div className="panel-heading"><div><p className="panel-kicker">{kicker}</p><h2>{title}</h2></div>{controls}</div>{children}</section>;
}

function Segmented({ value, values, labels, onChange }: { value: string; values: string[]; labels: string[]; onChange: (value: string) => void }) {
  return <div className="segmented">{values.map((item, index) => <button className={value === item ? "active" : ""} key={item} onClick={() => onChange(item)}>{labels[index]}</button>)}</div>;
}
