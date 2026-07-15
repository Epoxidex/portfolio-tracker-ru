import type { ReturnDelta } from "../api/dashboard";
import { formatMoney, formatPercent } from "../lib/format";

export function PerformanceStrip({ values }: { values: Array<{ label: string; delta?: ReturnDelta }> }) {
  return <section className="performance-strip">{values.map(({ label, delta }) => {
    const available = delta?.change != null && delta.pct != null;
    const positive = (delta?.change ?? 0) >= 0;
    return <article key={label}><span>{label}</span><strong className={available ? positive ? "positive" : "negative" : "neutral"}>{available ? formatMoney(delta.change!, true) : "—"}</strong><small className={available ? positive ? "positive" : "negative" : "neutral"}>{available ? formatPercent(delta.pct!) : "нет опорного снимка"}</small></article>;
  })}</section>;
}
