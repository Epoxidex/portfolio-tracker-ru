import type { ReactNode } from "react";

type Line = { values: number[]; color: string };

export function LineChart({ lines, labels, empty }: { lines: Line[]; labels: string[]; empty: string }) {
  const values = lines.flatMap((line) => line.values).filter(Number.isFinite);
  if (!values.length || labels.length < 2) return <ChartEmpty>{empty}</ChartEmpty>;
  const width = 900;
  const height = 260;
  const padding = 18;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = (line: Line) => line.values.map((value, index) => {
    const x = padding + index / Math.max(1, line.values.length - 1) * (width - padding * 2);
    const y = height - padding - (value - min) / range * (height - padding * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <div className="chart-shell">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Линейный график">
        {[0.25, 0.5, 0.75].map((part) => <line key={part} x1="0" x2={width} y1={height * part} y2={height * part} className="chart-grid" />)}
        {lines.map((line, index) => <polyline key={index} points={points(line)} fill="none" stroke={line.color} strokeWidth="3" vectorEffect="non-scaling-stroke" />)}
      </svg>
      <div className="chart-axis"><span>{labels[0]}</span><span>{labels[Math.floor(labels.length / 2)]}</span><span>{labels.at(-1)}</span></div>
    </div>
  );
}

export function BarChart({ values, labels, empty }: { values: number[]; labels: string[]; empty: string }) {
  if (!values.length) return <ChartEmpty>{empty}</ChartEmpty>;
  const max = Math.max(...values.map(Math.abs), 0.001);
  return (
    <div className="bar-chart" role="img" aria-label="Столбчатый график доходности">
      {values.map((value, index) => (
        <div className="bar-column" key={`${labels[index]}-${index}`} title={`${labels[index]}: ${(value * 100).toFixed(2)}%`}>
          <div className="bar-stage"><span className={value >= 0 ? "bar positive-bar" : "bar negative-bar"} style={{ height: `${Math.max(3, Math.abs(value) / max * 46)}%` }} /></div>
          {values.length <= 18 && <small>{labels[index]}</small>}
        </div>
      ))}
    </div>
  );
}

function ChartEmpty({ children }: { children: ReactNode }) {
  return <div className="chart-empty">{children}</div>;
}
