import { apiRequest } from "./client";

export type CashBalance = { broker: number; manual: number; total: number };
export type Transaction = {
  id: number;
  date: string;
  instrument: string | null;
  ticker: string | null;
  instrument_kind: string | null;
  kind: string;
  quantity: number;
  price: number;
  amount: number;
  commission: number;
  note?: string;
};
export type Reconciliation = {
  instrument_id: number;
  name: string;
  ticker?: string;
  kind: string;
  maturity_date: string;
  status: string;
  estimated_payout_rub?: number;
};
export type BackupItem = { name: string; created_at: string | null; size_bytes: number };

export function requestId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export async function getCash() { return apiRequest<CashBalance>("/ledger/cash"); }
export async function getTransactions() { return apiRequest<Transaction[]>("/transactions"); }
export async function getReconciliations() {
  return apiRequest<{ as_of: string; items: Reconciliation[]; total: number }>("/ledger/reconciliations");
}
export async function mutate(path: string, payload: Record<string, unknown>, method = "POST") {
  return apiRequest<Record<string, unknown>>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
export async function runAction(path: string) { return apiRequest<Record<string, unknown>>(path, { method: "POST" }); }
export async function getBackups() { return apiRequest<{ ok: true; items: BackupItem[] }>("/backups"); }
export async function createBackup() { return apiRequest<{ ok: true; backup: BackupItem }>("/backups", { method: "POST" }); }
export async function restoreBackup(filename: string) {
  return mutate("/backups/restore", { filename, confirm: true });
}
