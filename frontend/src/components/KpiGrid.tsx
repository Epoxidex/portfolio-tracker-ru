import type { PortfolioSummary } from "../api/portfolio";
import { formatMoney, formatPercent } from "../lib/format";

type KpiGridProps = {
  summary: PortfolioSummary;
};

export function KpiGrid({ summary }: KpiGridProps) {
  const cards = [
    {
      label: "Стоимость портфеля",
      value: formatMoney(summary.value),
      detail: `${formatPercent(summary.pnl_pct)} за всё время`,
      tone: summary.pnl >= 0 ? "positive" : "negative",
      accent: "gold",
    },
    {
      label: "Вложено",
      value: formatMoney(summary.invested),
      detail: "Учтённая себестоимость",
      tone: "neutral",
      accent: "blue",
    },
    {
      label: "Финансовый результат",
      value: formatMoney(summary.pnl, true),
      detail: `${formatMoney(summary.income_received)} выплат получено`,
      tone: summary.pnl >= 0 ? "positive" : "negative",
      accent: summary.pnl >= 0 ? "green" : "red",
    },
    {
      label: "XIRR",
      value: summary.xirr === null ? "Нет данных" : formatPercent(summary.xirr),
      detail: summary.xirr === null ? "Нужна история денежных потоков" : "Годовых с учётом дат",
      tone: summary.xirr === null ? "neutral" : summary.xirr >= 0 ? "positive" : "negative",
      accent: "violet",
    },
  ];

  return (
    <section className="kpi-grid" aria-label="Основные показатели">
      {cards.map((card) => (
        <article className={`kpi-card accent-${card.accent}`} key={card.label}>
          <div className="kpi-topline">
            <span className="kpi-label">{card.label}</span>
            <span className="kpi-dot" aria-hidden="true" />
          </div>
          <strong className="kpi-value">{card.value}</strong>
          <span className={`kpi-detail ${card.tone}`}>{card.detail}</span>
        </article>
      ))}
    </section>
  );
}
