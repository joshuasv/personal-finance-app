import { useEffect, useState } from "react";
import { api, Account, Transaction, formatMinor } from "../api";

export function Transactions() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState<number | null>(null);
  const [month, setMonth] = useState<string>(""); // YYYY-MM
  const [transactions, setTransactions] = useState<Transaction[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api
      .listAccounts()
      .then((res) => {
        setAccounts(res.accounts);
        if (res.accounts.length > 0) setAccountId(res.accounts[0].id);
      })
      .catch((e) => setError(String((e as Error).message ?? e)));
  }, []);

  useEffect(() => {
    if (accountId == null) return;
    let start: string | null = null;
    let end: string | null = null;
    if (month) {
      const [y, m] = month.split("-").map(Number);
      const lastDay = new Date(y, m, 0).getDate();
      start = `${y}-${String(m).padStart(2, "0")}-01`;
      end = `${y}-${String(m).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`;
    }
    void api
      .listTransactions(accountId, start, end)
      .then((res) => setTransactions(res.transactions))
      .catch((e) => setError(String((e as Error).message ?? e)));
  }, [accountId, month]);

  return (
    <section>
      <h2>Transactions</h2>
      {error && <div className="error">{error}</div>}
      <div className="filters">
        <label>
          Account
          <select
            value={accountId ?? ""}
            onChange={(e) => setAccountId(e.target.value ? parseInt(e.target.value) : null)}
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} ({a.currency})
              </option>
            ))}
          </select>
        </label>
        <label>
          Month
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          />
        </label>
        {month && <button onClick={() => setMonth("")}>Clear</button>}
      </div>

      {!transactions && <p>Loading…</p>}
      {transactions && transactions.length === 0 && (
        <p>No transactions match the active filters. Try clearing them or import a statement.</p>
      )}
      {transactions && transactions.length > 0 && (
        <>
          <table className="hide-on-mobile">
            <thead>
              <tr>
                <th>Date</th>
                <th>Payee</th>
                <th>Amount</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((t) => (
                <tr key={t.id}>
                  <td>{t.posted_date}</td>
                  <td>{t.payee}</td>
                  <td>{formatMinor(t.amount_minor, t.currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="cards mobile-only">
            {transactions.map((t) => (
              <li key={t.id} className="card">
                <div className="card-row">
                  <span>{t.posted_date}</span>
                  <strong>{formatMinor(t.amount_minor, t.currency)}</strong>
                </div>
                <div>{t.payee}</div>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
