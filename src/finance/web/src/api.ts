// Tiny API client. All operations live under `/api/<op-name>` and accept a
// JSON body matching the operation's Pydantic input model. The bearer key is
// read from localStorage. A 401 clears the key and notifies callers via a
// thrown `UnauthorizedError`, which the App-level effect handles by showing
// the key-entry screen again.

export class UnauthorizedError extends Error {
  constructor() {
    super("unauthorized");
  }
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(`api error ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

const KEY_STORAGE = "finance.apiKey";

export function getApiKey(): string | null {
  return localStorage.getItem(KEY_STORAGE);
}

export function setApiKey(key: string): void {
  localStorage.setItem(KEY_STORAGE, key);
}

export function clearApiKey(): void {
  localStorage.removeItem(KEY_STORAGE);
}

export async function callOp<TIn, TOut>(
  name: string,
  payload: TIn,
): Promise<TOut> {
  const key = getApiKey();
  if (!key) {
    throw new UnauthorizedError();
  }
  const res = await fetch(`/api/${name}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${key}`,
    },
    body: JSON.stringify(payload ?? {}),
  });
  if (res.status === 401) {
    clearApiKey();
    throw new UnauthorizedError();
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  if (!res.ok) {
    throw new ApiError(res.status, body);
  }
  return body as TOut;
}

// --- Operation typings (mirror core.operations.models) ----------------------

export type Account = {
  id: number;
  name: string;
  currency: string;
  opening_balance_minor: number;
  archived: boolean;
  created_at: string;
  updated_at: string;
};

export type Transaction = {
  id: number;
  account_id: number;
  posted_date: string;
  amount_minor: number;
  currency: string;
  payee: string;
  memo: string | null;
  entered_by: string;
  content_hash: string;
  created_at: string;
  updated_at: string;
};

export type Draft = {
  id: number;
  batch_id: number;
  account_id: number;
  posted_date: string;
  amount_minor: number;
  currency: string;
  payee: string;
  memo: string | null;
  status: "pending" | "confirmed" | "rejected";
  content_hash: string;
  confirmed_transaction_id: number | null;
  created_at: string;
  updated_at: string;
};

export type SummaryBlock = {
  currency: string;
  income_minor: number;
  expense_minor: number;
  net_savings_minor: number;
  savings_rate: number | null;
  transaction_count: number;
};

export type MonthlySummary = {
  year: number;
  month: number;
  start: string;
  end: string;
  blocks: SummaryBlock[];
};

export const api = {
  listAccounts: () =>
    callOp<{ include_archived: boolean }, { accounts: Account[] }>(
      "list_accounts",
      { include_archived: false },
    ),
  createAccount: (name: string, currency: string, openingMinor = 0) =>
    callOp<
      { name: string; currency: string; opening_balance_minor: number },
      { account: Account }
    >("create_account", {
      name,
      currency,
      opening_balance_minor: openingMinor,
    }),
  listTransactions: (
    accountId: number,
    start?: string | null,
    end?: string | null,
  ) =>
    callOp<
      { account_id: number; start: string | null; end: string | null },
      { transactions: Transaction[] }
    >("list_transactions", {
      account_id: accountId,
      start: start ?? null,
      end: end ?? null,
    }),
  listDrafts: () =>
    callOp<
      {
        account_id: number | null;
        batch_id: number | null;
        status: "pending";
        limit: number | null;
      },
      { drafts: Draft[] }
    >("list_drafts", {
      account_id: null,
      batch_id: null,
      status: "pending",
      limit: null,
    }),
  confirmDraft: (id: number) =>
    callOp<{ draft_id: number }, { transaction: Transaction; draft_id: number }>(
      "confirm_draft",
      { draft_id: id },
    ),
  rejectDraft: (id: number) =>
    callOp<{ draft_id: number }, { draft: Draft }>("reject_draft", {
      draft_id: id,
    }),
  monthlySummary: (year: number, month: number) =>
    callOp<{ year: number; month: number }, MonthlySummary>("monthly_summary", {
      year,
      month,
    }),
  accountBalanceSnapshot: () =>
    callOp<
      Record<string, never>,
      {
        accounts: Array<{
          account_id: number;
          name: string;
          currency: string;
          balance_minor: number;
        }>;
      }
    >("account_balance_snapshot", {}),
};

// --- Money formatting -------------------------------------------------------

const ZERO_DECIMAL = new Set(["JPY", "KRW", "VND", "CLP", "ISK"]);
const THREE_DECIMAL = new Set(["BHD", "JOD", "KWD", "OMR", "TND"]);

export function decimalsFor(currency: string): number {
  const code = currency.toUpperCase();
  if (ZERO_DECIMAL.has(code)) return 0;
  if (THREE_DECIMAL.has(code)) return 3;
  return 2;
}

export function formatMinor(minor: number, currency: string): string {
  const d = decimalsFor(currency);
  if (d === 0) return `${minor} ${currency}`;
  const sign = minor < 0 ? "-" : "";
  const mag = Math.abs(minor);
  const factor = Math.pow(10, d);
  const major = Math.floor(mag / factor);
  const frac = mag % factor;
  return `${sign}${major}.${frac.toString().padStart(d, "0")} ${currency}`;
}
