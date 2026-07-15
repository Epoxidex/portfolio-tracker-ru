import { apiRequest } from "./client";

export type Position = {
  id: number;
  kind: string;
  name: string;
  ticker: string | null;
  currency: string;
  qty: number;
  invested: number;
  value: number;
  income: number;
  pnl: number;
  pnl_pct: number;
  last_price: number;
  meta: Record<string, unknown>;
};

export type HistoryPoint = {
  ts: string;
  day?: string;
  value: number;
  invested: number;
  pnl: number;
  income: number;
};

export type ReturnPoint = { label: string; pct: number; change: number };
export type ReturnDelta = { pct: number | null; change: number | null };
export type ReturnsData = {
  points: ReturnPoint[];
  today?: ReturnDelta;
  week?: ReturnDelta;
  month?: ReturnDelta;
  ytd?: ReturnDelta;
};

export type Leader = {
  id?: number;
  name: string;
  ticker: string | null;
  change: number;
  change_pct: number | null;
  impact_pct: number;
  value: number;
};

export type LeadersData = {
  from: string | null;
  to: string | null;
  complete: boolean;
  items: Leader[];
};

export type CalendarEvent = {
  date: string;
  instrument: string;
  type: string;
  amount: number;
  ticker: string | null;
};

export type PassiveIncome = {
  annual: number;
  monthly: number;
  detail: Array<{ name: string; annual: number }>;
};

export type PriceSeries = {
  id: number;
  name: string;
  ticker: string | null;
  kind: string;
  currency: string;
  history: Array<{ ts: string; price: number }>;
};

export async function getPositions() {
  return apiRequest<Position[]>("/positions");
}

export async function getHistory() {
  return apiRequest<HistoryPoint[]>("/history");
}

export async function getReturns(period: "daily" | "monthly" | "yearly") {
  return apiRequest<ReturnsData>(`/returns?period=${period}`);
}

export async function getLeaders(period: "day" | "week" | "month") {
  return apiRequest<LeadersData>(`/leaders?period=${period}`);
}

export async function getCalendar() {
  return apiRequest<CalendarEvent[]>("/calendar?months=36&past=true");
}

export async function getPassiveIncome() {
  return apiRequest<PassiveIncome>("/income");
}

export async function getPriceHistory(days: number) {
  return apiRequest<PriceSeries[]>(`/prices/history?days=${days}`);
}
