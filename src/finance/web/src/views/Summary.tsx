import { useEffect, useState } from "react";
import { api, MonthlySummary, formatMinor } from "../api";

function defaultMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function Summary() {
  const [month, setMonth] = useState<string>(defaultMonth());
  const [summary, setSummary] = useState<MonthlySummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    setSummary(null);
    const [y, m] = month.split("-").map(Number);
    void api
      .monthlySummary(y, m)
      .then(setSummary)
      .catch((e) => setError(String((e as Error).message ?? e)));
  }, [month]);

  return (
    <section>
      <h2>Monthly summary</h2>
      <label>
        Month
        <input
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
        />
      </label>
      {error && <div className="error">{error}</div>}
      {!summary && !error && <p>Loading…</p>}
      {summary && summary.blocks.length === 0 && (
        <p>No transactions in {month}.</p>
      )}
      {summary &&
        summary.blocks.map((b) => (
          <div className="summary-block" key={b.currency}>
            <h3>{b.currency}</h3>
            <table>
              <tbody>
                <tr>
                  <th>Income</th>
                  <td>{formatMinor(b.income_minor, b.currency)}</td>
                </tr>
                <tr>
                  <th>Expense</th>
                  <td>{formatMinor(b.expense_minor, b.currency)}</td>
                </tr>
                <tr>
                  <th>Net savings</th>
                  <td>{formatMinor(b.net_savings_minor, b.currency)}</td>
                </tr>
                <tr>
                  <th>Savings rate</th>
                  <td>{b.savings_rate == null ? "—" : `${b.savings_rate}%`}</td>
                </tr>
                <tr>
                  <th>Transactions</th>
                  <td>{b.transaction_count}</td>
                </tr>
              </tbody>
            </table>
          </div>
        ))}
    </section>
  );
}
