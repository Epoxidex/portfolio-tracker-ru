import { useCallback, useEffect, useState } from "react";
import {
  getPortfolioOverview,
  type PortfolioStatus,
  type PortfolioSummary,
} from "./api/portfolio";
import { AllocationPanel } from "./components/AllocationPanel";
import { GoalCard } from "./components/GoalCard";
import { KpiGrid } from "./components/KpiGrid";
import { SystemStatus } from "./components/SystemStatus";
import { formatDate } from "./lib/format";

type OverviewState = {
  summary: PortfolioSummary;
  status: PortfolioStatus;
};

export function App() {
  const [overview, setOverview] = useState<OverviewState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadOverview = useCallback(async () => {
    setRefreshing(true);
    try {
      setOverview(await getPortfolioOverview());
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить портфель");
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/react-preview/" aria-label="Портфель — главная">
          <span className="brand-mark" aria-hidden="true">◆</span>
          <span>
            <strong>Портфель</strong>
            <small>личный капитал</small>
          </span>
        </a>

        <nav className="nav-tabs" aria-label="Разделы">
          <a className="nav-tab active" href="/react-preview/">Обзор</a>
          <a className="nav-tab" href="/" title="Пока доступно в стабильном интерфейсе">Операции</a>
        </nav>

        <div className="topbar-actions">
          <span className="preview-badge">React preview</span>
          <button
            className="icon-button"
            type="button"
            onClick={() => void loadOverview()}
            disabled={refreshing}
            aria-label="Обновить данные"
            title="Обновить данные"
          >
            <span className={refreshing ? "spin" : ""} aria-hidden="true">↻</span>
          </button>
        </div>
      </header>

      <main>
        <section className="page-heading">
          <div>
            <p className="eyebrow">Финансовая картина</p>
            <h1>Добрый вечер</h1>
            <p className="page-subtitle">
              {overview
                ? `Данные портфеля на ${formatDate(overview.summary.as_of)}`
                : "Собираем актуальные данные портфеля"}
            </p>
          </div>
          <a className="legacy-link" href="/">
            Стабильный интерфейс <span aria-hidden="true">↗</span>
          </a>
        </section>

        {error && (
          <div className="error-banner" role="alert">
            <span aria-hidden="true">!</span>
            <div>
              <strong>Не удалось обновить обзор</strong>
              <p>{error}</p>
            </div>
            <button type="button" onClick={() => void loadOverview()}>Повторить</button>
          </div>
        )}

        {overview ? (
          <div className="dashboard-stack">
            <KpiGrid summary={overview.summary} />
            <div className="overview-grid">
              <GoalCard
                current={overview.summary.value}
                goal={overview.status.portfolio_goal}
                streak={overview.summary.streak}
              />
              <AllocationPanel classes={overview.summary.by_class} />
              <SystemStatus status={overview.status} />
            </div>
          </div>
        ) : (
          <LoadingDashboard />
        )}
      </main>
    </div>
  );
}

function LoadingDashboard() {
  return (
    <div className="dashboard-stack" aria-label="Загрузка обзора">
      <div className="kpi-grid">
        {Array.from({ length: 4 }, (_, index) => (
          <div className="kpi-card skeleton-card" key={index}>
            <span className="skeleton line-short" />
            <span className="skeleton line-long" />
            <span className="skeleton line-medium" />
          </div>
        ))}
      </div>
      <div className="overview-grid">
        {Array.from({ length: 3 }, (_, index) => (
          <div className="panel skeleton-panel" key={index}>
            <span className="skeleton line-medium" />
            <span className="skeleton block" />
          </div>
        ))}
      </div>
    </div>
  );
}
