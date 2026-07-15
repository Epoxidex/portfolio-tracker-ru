import type { Position } from "../api/dashboard";
import { formatMoney, formatPercent } from "../lib/format";

const kindNames: Record<string, string> = {
  bond: "Облигация",
  share: "Акция",
  etf: "Фонд",
  currency: "Валюта",
  deposit: "Вклад",
};

export function PositionsTable({ positions }: { positions: Position[] }) {
  if (!positions.length) {
    return <div className="empty-state compact"><strong>Активных позиций пока нет</strong><p>Добавьте актив или импортируйте портфель из T‑Invest.</p></div>;
  }

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead><tr><th>Инструмент</th><th>Количество</th><th>Вложено</th><th>Стоимость</th><th>Результат</th></tr></thead>
        <tbody>
          {positions.map((position) => (
            <tr key={position.id}>
              <td>
                <span className="instrument-cell"><strong>{position.ticker || position.name}</strong><small>{position.ticker ? position.name : kindNames[position.kind] || position.kind}</small></span>
              </td>
              <td>{position.qty.toLocaleString("ru-RU", { maximumFractionDigits: 4 })} <small>{position.currency !== "RUB" ? position.currency : ""}</small></td>
              <td>{formatMoney(position.invested)}</td>
              <td><strong>{formatMoney(position.value)}</strong></td>
              <td className={position.pnl >= 0 ? "positive" : "negative"}>
                <strong>{formatMoney(position.pnl, true)}</strong><small>{formatPercent(position.pnl_pct)}</small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
