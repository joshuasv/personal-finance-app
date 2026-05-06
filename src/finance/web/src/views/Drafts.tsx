import { useEffect, useState } from "react";
import { api, Draft, formatMinor } from "../api";

export function Drafts() {
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  async function load() {
    setError(null);
    try {
      const res = await api.listDrafts();
      setDrafts(res.drafts);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function confirm(id: number) {
    setBusy(id);
    try {
      await api.confirmDraft(id);
      setDrafts((prev) => (prev ? prev.filter((d) => d.id !== id) : prev));
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  }

  async function reject(id: number) {
    setBusy(id);
    try {
      await api.rejectDraft(id);
      setDrafts((prev) => (prev ? prev.filter((d) => d.id !== id) : prev));
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  }

  async function confirmBatch(batchId: number) {
    if (!drafts) return;
    const ids = drafts.filter((d) => d.batch_id === batchId).map((d) => d.id);
    for (const id of ids) {
      await confirm(id);
    }
  }

  if (drafts && drafts.length === 0) {
    return (
      <section>
        <h2>Drafts</h2>
        <p>No pending drafts. Import a statement to see drafts here.</p>
      </section>
    );
  }

  // Group by batch.
  const byBatch = new Map<number, Draft[]>();
  for (const d of drafts ?? []) {
    if (!byBatch.has(d.batch_id)) byBatch.set(d.batch_id, []);
    byBatch.get(d.batch_id)!.push(d);
  }

  return (
    <section>
      <h2>Drafts</h2>
      {error && <div className="error">{error}</div>}
      {!drafts && <p>Loading…</p>}
      {Array.from(byBatch.entries()).map(([batchId, items]) => (
        <div className="batch" key={batchId}>
          <div className="batch-header">
            <h3>Batch #{batchId}</h3>
            <button onClick={() => confirmBatch(batchId)}>
              Confirm all in this batch
            </button>
          </div>
          <ul className="cards">
            {items.map((d) => (
              <li key={d.id} className="card">
                <div className="card-row">
                  <span>{d.posted_date}</span>
                  <strong>{formatMinor(d.amount_minor, d.currency)}</strong>
                </div>
                <div>{d.payee}</div>
                <div className="actions">
                  <button disabled={busy === d.id} onClick={() => confirm(d.id)}>
                    Confirm
                  </button>
                  <button disabled={busy === d.id} onClick={() => reject(d.id)}>
                    Reject
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
