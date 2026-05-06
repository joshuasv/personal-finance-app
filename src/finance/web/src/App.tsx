import { useEffect, useState } from "react";
import { KeyEntry } from "./KeyEntry";
import { Accounts } from "./views/Accounts";
import { Transactions } from "./views/Transactions";
import { Drafts } from "./views/Drafts";
import { Summary } from "./views/Summary";
import { clearApiKey, getApiKey } from "./api";

type View = "accounts" | "transactions" | "drafts" | "summary";

export function App() {
  const [hasKey, setHasKey] = useState<boolean>(() => Boolean(getApiKey()));
  const [view, setView] = useState<View>("summary");
  const [navOpen, setNavOpen] = useState(false);

  // The key-entry screen is shown whenever no key is stored. Each view also
  // listens for `unauthorized` events from the api client and clears state.
  useEffect(() => {
    function onUnauthorized() {
      clearApiKey();
      setHasKey(false);
    }
    window.addEventListener("finance:unauthorized", onUnauthorized);
    return () => window.removeEventListener("finance:unauthorized", onUnauthorized);
  }, []);

  if (!hasKey) {
    return <KeyEntry onSubmit={() => setHasKey(true)} />;
  }

  return (
    <div className="app">
      <header className="topbar">
        <button
          className="navtoggle"
          onClick={() => setNavOpen((v) => !v)}
          aria-expanded={navOpen}
          aria-controls="primary-nav"
        >
          ☰ <span className="visually-hidden">menu</span>
        </button>
        <h1>finance</h1>
        <button
          className="logout"
          onClick={() => {
            clearApiKey();
            setHasKey(false);
          }}
        >
          Log out
        </button>
      </header>
      <nav id="primary-nav" className={`nav ${navOpen ? "open" : ""}`}>
        <NavButton label="Summary" active={view === "summary"} onClick={() => setView("summary")} />
        <NavButton label="Accounts" active={view === "accounts"} onClick={() => setView("accounts")} />
        <NavButton label="Transactions" active={view === "transactions"} onClick={() => setView("transactions")} />
        <NavButton label="Drafts" active={view === "drafts"} onClick={() => setView("drafts")} />
      </nav>
      <main className="content">
        {view === "summary" && <Summary />}
        {view === "accounts" && <Accounts />}
        {view === "transactions" && <Transactions />}
        {view === "drafts" && <Drafts />}
      </main>
    </div>
  );
}

function NavButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className={`navbtn ${active ? "active" : ""}`}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
    >
      {label}
    </button>
  );
}
