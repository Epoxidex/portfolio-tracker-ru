import { useEffect, useState } from "react";
import type { PortfolioStatus, PortfolioSummary } from "../api/portfolio";
import { getPositions, type Position } from "../api/dashboard";
import { AllocationPanel } from "../components/AllocationPanel";
import { GoalCard } from "../components/GoalCard";
import { KpiGrid } from "../components/KpiGrid";
import { PageHeading } from "../components/PageHeading";
import { PositionsTable } from "../components/PositionsTable";
import { SystemStatus } from "../components/SystemStatus";
import { formatDate } from "../lib/format";

type Props = {
  summary: PortfolioSummary;
  status: PortfolioStatus;
  revision: number;
  onNavigate: (tab: "operations" | "data") => void;
};

export function OverviewPage({ summary, status, revision, onNavigate }: Props) {
  const [positions, setPositions] = useState<Position[]>([]);

  useEffect(() => {
    void getPositions().then(setPositions);
  }, [revision]);

  const empty = status.data.instruments === 0;
  return (
    <>
      <PageHeading
        eyebrow="Финансовая картина"
        title="Обзор портфеля"
        subtitle={`Данные на ${formatDate(summary.as_of)}`}
        actions={<a className="legacy-link" href="/">Старый интерфейс ↗</a>}
      />
      {empty && (
        <section className="onboarding-card">
          <div><p className="panel-kicker">Быстрый старт</p><h2>Подключите реальные данные</h2><p>Импортируйте T‑Invest или добавьте ручные активы. Всё хранится локально.</p></div>
          <div className="button-row"><button className="primary-button" onClick={() => onNavigate("data")}>Импортировать</button><button className="secondary-button" onClick={() => onNavigate("operations")}>Добавить операцию</button></div>
        </section>
      )}
      <div className="dashboard-stack">
        <KpiGrid summary={summary} />
        <div className="overview-grid">
          <GoalCard current={summary.value} goal={status.portfolio_goal} streak={summary.streak} />
          <AllocationPanel classes={summary.by_class} />
          <SystemStatus status={status} />
        </div>
        <section className="panel wide-panel">
          <div className="panel-heading"><div><p className="panel-kicker">Текущий состав</p><h2>Позиции</h2></div><span className="panel-meta">{positions.length} активов</span></div>
          <PositionsTable positions={positions} />
        </section>
      </div>
    </>
  );
}
