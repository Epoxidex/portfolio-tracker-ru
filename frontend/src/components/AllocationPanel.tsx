import type { PortfolioClassSummary } from "../api/portfolio";
import { formatMoney, formatPercent } from "../lib/format";

type AllocationPanelProps = {
  classes: Record<string, PortfolioClassSummary>;
};

const colors = ["#f6c760", "#6ea8fe", "#58d6c2", "#b596f5", "#fb8f67", "#f67b91"];

export function AllocationPanel({ classes }: AllocationPanelProps) {
  const rows = Object.entries(classes)
    .sort(([, left], [, right]) => right.value - left.value);
  const total = rows.reduce((sum, [, item]) => sum + item.value, 0);

  return (
    <article className="panel allocation-panel">
      <div className="panel-heading">
        <div>
          <p className="panel-kicker">Структура</p>
          <h2>Классы активов</h2>
        </div>
        <span className="panel-meta">{rows.length} классов</span>
      </div>

      {rows.length ? (
        <div className="allocation-list">
          {rows.map(([name, item], index) => {
            const share = total ? item.value / total : 0;
            return (
              <div className="allocation-row" key={name}>
                <span className="allocation-swatch" style={{ background: colors[index % colors.length] }} />
                <div className="allocation-name">
                  <strong>{name}</strong>
                  <span>{formatPercent(share, false)} портфеля</span>
                </div>
                <div className="allocation-value">
                  <strong>{formatMoney(item.value)}</strong>
                  <span className={item.pnl >= 0 ? "positive" : "negative"}>
                    {formatMoney(item.pnl, true)}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="empty-state">
          <span aria-hidden="true">◎</span>
          <strong>Активов пока нет</strong>
          <p>Добавьте первую позицию в стабильном интерфейсе или через MCP.</p>
        </div>
      )}
    </article>
  );
}
