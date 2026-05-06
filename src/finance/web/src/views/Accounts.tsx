import { useEffect, useState } from "react";
import { api, Account, formatMinor } from "../api";

export function Accounts() {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [balances, setBalances] = useState<Record<number, { minor: number; currency: string }>>({});
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("GBP");
  const [opening, setOpening] = useState(0);

  async function load() {
    setError(null);
    try {
      const accs = await api.listAccounts();
      setAccounts(accs.accounts);
      const snap = await api.accountBalanceSnapshot();
      const map: Record<number, { minor: number; currency: string }> = {};
      for (const row of snap.accounts) {
        map[row.account_id] = { minor: row.balance_minor, currency: row.currency };
      }
      setBalances(map);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <section>
      <h2>Accounts</h2>
      {error && <div className="error">{error}</div>}
      <form
        className="newform"
        onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          try {
            await api.createAccount(name, currency, opening);
            setName("");
            setCurrency("GBP");
            setOpening(0);
            await load();
          } catch (e) {
            setError(String((e as Error).message ?? e));
          }
        }}
      >
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          Currency
          <input
            value={currency}
            onChange={(e) => setCurrency(e.target.value.toUpperCase())}
            maxLength={3}
            required
          />
        </label>
        <label>
          Opening balance (minor units)
          <input
            type="number"
            value={opening}
            onChange={(e) => setOpening(parseInt(e.target.value || "0", 10))}
          />
        </label>
        <button type="submit">Add account</button>
      </form>

      {!accounts && <p>Loading…</p>}
      {accounts && accounts.length === 0 && <p>No accounts yet.</p>}
      {accounts && accounts.length > 0 && (
        <>
          <table className="hide-on-mobile">
            <thead>
              <tr>
                <th>Name</th>
                <th>Currency</th>
                <th>Balance</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((a) => (
                <tr key={a.id}>
                  <td>{a.name}</td>
                  <td>{a.currency}</td>
                  <td>
                    {balances[a.id]
                      ? formatMinor(balances[a.id].minor, balances[a.id].currency)
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="cards mobile-only">
            {accounts.map((a) => (
              <li key={a.id} className="card">
                <strong>{a.name}</strong>
                <div>{a.currency}</div>
                <div>
                  {balances[a.id]
                    ? formatMinor(balances[a.id].minor, balances[a.id].currency)
                    : "—"}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
