const moneyFormatter = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  maximumFractionDigits: 0,
});

const dateFormatter = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "long",
  year: "numeric",
});

export function formatMoney(value: number, showSign = false) {
  const formatted = moneyFormatter.format(Math.abs(value));
  if (!showSign || value === 0) return value < 0 ? `−${formatted}` : formatted;
  return `${value > 0 ? "+" : "−"}${formatted}`;
}

export function formatPercent(value: number, showSign = true) {
  const number = `${(Math.abs(value) * 100).toFixed(2)}%`;
  if (!showSign || value === 0) return value < 0 ? `−${number}` : number;
  return `${value > 0 ? "+" : "−"}${number}`;
}

export function formatDate(value: string) {
  return dateFormatter.format(new Date(`${value}T00:00:00`));
}
