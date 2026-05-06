import { useState } from "react";
import { setApiKey } from "./api";

export function KeyEntry({ onSubmit }: { onSubmit: () => void }) {
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="key-entry">
      <h1>finance</h1>
      <p>Enter your API key to continue.</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!key.trim()) {
            setError("API key is required.");
            return;
          }
          setApiKey(key.trim());
          onSubmit();
        }}
      >
        <label>
          API key
          <input
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            autoFocus
            autoComplete="off"
          />
        </label>
        {error && <div className="error">{error}</div>}
        <button type="submit">Save key</button>
      </form>
      <p className="hint">
        The key is stored in this browser's local storage. Use “Log out” to clear it.
      </p>
    </div>
  );
}
