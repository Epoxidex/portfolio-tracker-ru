import { useCallback, useEffect, useState } from "react";
import {
  getPortfolioOverview,
  type PortfolioStatus,
  type PortfolioSummary,
} from "./api/portfolio";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { CalendarPage } from "./pages/CalendarPage";
import { OverviewPage } from "./pages/OverviewPage";

type OverviewState = {
  summary: PortfolioSummary;
  status: PortfolioStatus;
};

type Tab = "overview" | "analytics" | "calendar" | "operations" | "data";

const tabs: Array<{ id: Tab; label: string; short: string }> = [
  { id: "overview", label: "Обзор", short: "Обзор" },
  { id: "analytics", label: "Аналитика", short: "Графики" },
  { id: "calendar", label: "Календарь", short: "Выплаты" },
  { id: "operations", label: "Операции", short: "Сделки" },
  { id: "data", label: "Данные", short: "Данные" },
];

export function App() {
  const [overview, setOverview] = useState<OverviewState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [tab, setTab] = useState<Tab>("overview");
  const [revision, setRevision] = useState(0);

  const loadOverview = useCallback(async () => {
    setRefreshing(true);
    try {
      setOverview(await getPortfolioOverview());
      setError(null);
      setRevision((value) => value + 1);
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
        <button className="brand brand-button" type="button" onClick={() => setTab("overview")} aria-label="Портфель — главная">
          <span className="brand-mark" aria-hidden="true">◆</span>
          <span>
            <strong>Портфель</strong>
            <small>личный капитал</small>
          </span>
        </button>

        <nav className="nav-tabs" aria-label="Разделы">
          {tabs.map((item) => <button type="button" className={`nav-tab ${tab === item.id ? "active" : ""}`} onClick={() => setTab(item.id)} key={item.id}>{item.label}</button>)}
        </nav>

        <div className="topbar-actions">
          <a className="preview-badge" href="/">Legacy ↗</a>
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

        {overview ? <Page tab={tab} overview={overview} revision={revision} onNavigate={setTab} /> : <LoadingDashboard />}
      </main>
      <nav className="mobile-nav" aria-label="Разделы">
        {tabs.map((item) => <button type="button" className={tab === item.id ? "active" : ""} onClick={() => setTab(item.id)} key={item.id}><span aria-hidden="true">{mobileIcon(item.id)}</span>{item.short}</button>)}
      </nav>
    </div>
  );
}

function Page({ tab, overview, revision, onNavigate }: { tab: Tab; overview: OverviewState; revision: number; onNavigate: (tab: Tab) => void }) {
  if (tab === "analytics") return <AnalyticsPage revision={revision} />;
  if (tab === "calendar") return <CalendarPage revision={revision} />;
  if (tab === "operations") return <ComingSoon title="Операции" text="Формы сделок, пополнений и вкладов подключаются следующим блоком." />;
  if (tab === "data") return <ComingSoon title="Данные" text="Импорт, обновления, Excel и резервные копии подключаются следующим блоком." />;
  return <OverviewPage summary={overview.summary} status={overview.status} revision={revision} onNavigate={onNavigate} />;
}

function ComingSoon({ title, text }: { title: string; text: string }) {
  return <section className="page-heading"><div><p className="eyebrow">React migration</p><h1>{title}</h1><p className="page-subtitle">{text}</p></div></section>;
}

function mobileIcon(tab: Tab) {
  return ({ overview: "◆", analytics: "⌁", calendar: "□", operations: "+", data: "↻" })[tab];
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
