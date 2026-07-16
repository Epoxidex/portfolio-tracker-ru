import { apiRequest } from "./client";

export type PortfolioClassSummary = {
  cost_basis: number;
  invested: number;
  value: number;
  pnl: number;
  pnl_pct: number;
};

export type PortfolioSummary = {
  as_of: string;
  invested: number;
  external_withdrawals: number;
  net_external_capital: number;
  capital_inferred: number;
  cost_basis: number;
  value: number;
  pnl: number;
  pnl_pct: number;
  income_received: number;
  xirr: number | null;
  streak: number;
  by_class: Record<string, PortfolioClassSummary>;
};

export type PortfolioStatus = {
  tinvest: {
    configured: boolean;
    account_selected: boolean;
  };
  fx_source: "cbr" | "bank_buy" | "bank_sell";
  portfolio_goal: number;
  tracking_start_date: string | null;
  background_jobs_minutes: {
    snapshots: number;
    tinvest_prices: number;
    currency_rates: number;
  };
  data: {
    instruments: number;
    transactions: number;
    price_points: number;
    snapshots: number;
  };
};

export async function getPortfolioOverview() {
  const [summary, status] = await Promise.all([
    apiRequest<PortfolioSummary>("/summary"),
    apiRequest<PortfolioStatus>("/status"),
  ]);
  return { summary, status };
}
