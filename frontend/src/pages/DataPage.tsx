import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import type { PortfolioStatus } from "../api/portfolio";
import { createBackup, getBackups, restoreBackup, runAction, mutate, type BackupItem } from "../api/actions";
import { Field, SelectField, SubmitButton } from "../components/FormFields";
import { PageHeading } from "../components/PageHeading";
import { formatDate } from "../lib/format";

type Props = { status: PortfolioStatus; onChanged: () => Promise<void> };

export function DataPage({ status, onChanged }: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [backupError, setBackupError] = useState<string | null>(null);
  const [selectedBackup, setSelectedBackup] = useState("");

  const loadBackups = useCallback(async () => {
    try { const result = await getBackups(); setBackups(result.items); setSelectedBackup((value) => value || result.items[0]?.name || ""); setBackupError(null); }
    catch (error) { setBackupError(error instanceof Error ? error.message : "Не удалось загрузить бэкапы"); }
  }, []);
  useEffect(() => { void loadBackups(); }, [loadBackups]);

  const perform = async (key: string, task: () => Promise<unknown>, success: string, refresh = true) => {
    setBusy(key); setMessage(null);
    try { await task(); setMessage({ text: success }); if (refresh) await onChanged(); }
    catch (error) { setMessage({ text: error instanceof Error ? error.message : "Операция не выполнена", error: true }); }
    finally { setBusy(null); }
  };

  const trackingSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const data = new FormData(event.currentTarget); const date = String(data.get("start_date"));
    if (!window.confirm(`Изменить начало учёта на ${date}? Перед очисткой старых импортов будет создан бэкап.`)) return;
    void perform("tracking", () => mutate("/settings/tracking-start", { start_date: date, confirm: true }), "Дата начала учёта обновлена");
  };
  const fxSubmit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); void perform("fx", () => runAction(`/fetch/fx?source=${data.get("source")}`), "Курсы валют обновлены"); };
  const doRestore = async () => {
    if (!selectedBackup || !window.confirm(`Восстановить базу из ${selectedBackup}? Текущая база будет сохранена отдельно.`)) return;
    setBusy("restore"); setMessage(null);
    try { await restoreBackup(selectedBackup); window.location.reload(); }
    catch (error) { setMessage({ text: error instanceof Error ? error.message : "Не удалось восстановить базу", error: true }); setBusy(null); }
  };

  return (
    <>
      <PageHeading eyebrow="Управление" title="Данные и сервис" subtitle="Синхронизация, курсы, снимки, экспорт, резервные копии и граница истории" />
      {message && <div className={`notice ${message.error ? "error" : "success"}`}>{message.text}</div>}
      <section className="service-grid">
        <ServiceCard icon="⇄" title="T‑Invest" text={status.tinvest.configured ? "Read-only подключение настроено" : "Токен не настроен"} tone={status.tinvest.configured ? "good" : "muted"}><button className="primary-button" disabled={!status.tinvest.configured || busy !== null} onClick={() => void perform("sync", () => runAction("/sync/tinvest?days=3650"), "Операции и цены синхронизированы")}>{busy === "sync" ? "Импортируем…" : "Импортировать всё"}</button><button className="secondary-button" disabled={!status.tinvest.configured || busy !== null} onClick={() => void perform("prices", () => runAction("/fetch/prices"), "Цены обновлены")}>Только цены</button></ServiceCard>
        <ServiceCard icon="◉" title="Снимок" text={`${status.data.snapshots} сохранённых точек истории`} tone="good"><button className="primary-button" disabled={busy !== null} onClick={() => void perform("snapshot", () => runAction("/snapshot"), "Снимок портфеля создан")}>{busy === "snapshot" ? "Сохраняем…" : "Создать снимок"}</button><a className="secondary-button button-link" href="/api/export/excel">Скачать Excel</a></ServiceCard>
        <ServiceCard icon="₽" title="Курсы валют" text={`Текущий источник: ${sourceName(status.fx_source)}`} tone="good"><form className="inline-form" onSubmit={fxSubmit}><SelectField label="Источник" name="source" defaultValue={status.fx_source}><option value="cbr">ЦБ РФ</option><option value="bank_buy">Банк покупает</option><option value="bank_sell">Банк продаёт</option></SelectField><SubmitButton busy={busy === "fx"}>Обновить курсы</SubmitButton></form></ServiceCard>
      </section>
      <div className="data-settings-grid">
        <section className="panel settings-panel">
          <div className="panel-heading"><div><p className="panel-kicker">Граница истории</p><h2>Начало учёта</h2></div></div>
          <p className="settings-copy">Операции T‑Invest до выбранной даты будут исключены. Ручные активы сохранятся, перед изменением создастся резервная копия.</p>
          <form className="single-form" onSubmit={trackingSubmit}><Field label="Учитывать портфель начиная с" name="start_date" type="date" defaultValue={status.tracking_start_date ?? ""} required /><SubmitButton busy={busy === "tracking"}>Применить дату</SubmitButton></form>
          <div className="jobs-list"><span>Автоснимки <b>{jobLabel(status.background_jobs_minutes.snapshots)}</b></span><span>Цены T‑Invest <b>{jobLabel(status.background_jobs_minutes.tinvest_prices)}</b></span><span>Курсы валют <b>{jobLabel(status.background_jobs_minutes.currency_rates)}</b></span></div>
        </section>
        <section className="panel settings-panel backup-panel">
          <div className="panel-heading"><div><p className="panel-kicker">Приватное хранилище</p><h2>Резервные копии</h2></div><button className="secondary-button" disabled={busy !== null} onClick={() => void perform("backup", createBackup, "Новый бэкап отправлен в приватный репозиторий", false).then(loadBackups)}>{busy === "backup" ? "Создаём…" : "Создать"}</button></div>
          {backupError ? <div className="backup-error">{backupError}</div> : backups.length ? <><div className="backup-list">{backups.slice(0, 6).map((backup) => <label className={selectedBackup === backup.name ? "selected" : ""} key={backup.name}><input type="radio" name="backup" value={backup.name} checked={selectedBackup === backup.name} onChange={() => setSelectedBackup(backup.name)} /><span><strong>{backup.created_at ? formatDate(backup.created_at.slice(0, 10)) : backup.name}</strong><small>{backup.name} · {formatBytes(backup.size_bytes)}</small></span></label>)}</div><button className="danger-button" disabled={!selectedBackup || busy !== null} onClick={() => void doRestore()}>{busy === "restore" ? "Восстанавливаем…" : "Восстановить выбранную копию"}</button></> : <div className="empty-state compact"><strong>Резервных копий пока нет</strong><p>Создайте первую копию в приватном репозитории.</p></div>}
        </section>
      </div>
    </>
  );
}

function ServiceCard({ icon, title, text, tone, children }: { icon: string; title: string; text: string; tone: string; children: ReactNode }) { return <article className="service-card"><span className={`service-icon ${tone}`}>{icon}</span><div><h2>{title}</h2><p>{text}</p></div><div className="service-actions">{children}</div></article>; }
function sourceName(source: string) { return ({ cbr: "ЦБ РФ", bank_buy: "банк покупает", bank_sell: "банк продаёт" } as Record<string, string>)[source] || source; }
function jobLabel(minutes: number) { return minutes ? `каждые ${minutes} мин.` : "выключено"; }
function formatBytes(bytes: number) { return `${(bytes / 1024 / 1024).toFixed(1)} МБ`; }
