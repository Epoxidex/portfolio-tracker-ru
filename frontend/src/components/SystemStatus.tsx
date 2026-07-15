import type { PortfolioStatus } from "../api/portfolio";

type SystemStatusProps = {
  status: PortfolioStatus;
};

const fxLabels = {
  cbr: "ЦБ РФ",
  bank_buy: "Банк покупает",
  bank_sell: "Банк продаёт",
};

export function SystemStatus({ status }: SystemStatusProps) {
  const items = [
    {
      label: "Т‑Инвестиции",
      value: status.tinvest.configured ? "Подключены" : "Не подключены",
      ok: status.tinvest.configured,
    },
    {
      label: "Источник валют",
      value: fxLabels[status.fx_source],
      ok: true,
    },
    {
      label: "Снимки портфеля",
      value: String(status.data.snapshots),
      ok: status.data.snapshots > 0,
    },
    {
      label: "Операции в базе",
      value: String(status.data.transactions),
      ok: status.data.transactions > 0,
    },
  ];

  return (
    <article className="panel status-panel">
      <div className="panel-heading">
        <div>
          <p className="panel-kicker">Система</p>
          <h2>Состояние данных</h2>
        </div>
        <span className="live-indicator"><i /> Локально</span>
      </div>

      <div className="status-list">
        {items.map((item) => (
          <div className="status-row" key={item.label}>
            <span>{item.label}</span>
            <strong><i className={item.ok ? "ok" : "muted"} /> {item.value}</strong>
          </div>
        ))}
      </div>

      <p className="privacy-note">
        <span aria-hidden="true">⌁</span>
        Данные остаются на этом компьютере
      </p>
    </article>
  );
}
