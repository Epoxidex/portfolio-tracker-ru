import { formatMoney } from "../lib/format";

type GoalCardProps = {
  current: number;
  goal: number;
  streak: number;
};

export function GoalCard({ current, goal, streak }: GoalCardProps) {
  const safeGoal = Math.max(goal, 1);
  const progress = Math.min(100, Math.max(0, current / safeGoal * 100));
  const remaining = Math.max(0, goal - current);

  return (
    <article className="panel goal-panel">
      <div className="panel-heading">
        <div>
          <p className="panel-kicker">Большая цель</p>
          <h2>{formatMoney(goal)}</h2>
        </div>
        <span className="streak-pill" title="Дней подряд со снимками">
          <span aria-hidden="true">◇</span> {streak} дн.
        </span>
      </div>

      <div className="progress-copy">
        <strong>{progress.toFixed(1)}%</strong>
        <span>Осталось {formatMoney(remaining)}</span>
      </div>
      <div
        className="progress-track"
        role="progressbar"
        aria-label="Прогресс к цели"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(progress)}
      >
        <span style={{ width: `${progress}%` }} />
      </div>
      <p className="goal-caption">
        Сейчас накоплено <strong>{formatMoney(current)}</strong>. Цель берётся из
        локальной настройки портфеля.
      </p>
    </article>
  );
}
