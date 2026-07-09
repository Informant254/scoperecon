import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";

export function Shell({
  children,
  showUrgency = false,
}: {
  children: React.ReactNode;
  showUrgency?: boolean;
}) {
  const { user, signOut } = useAuth();
  const nav = useNavigate();

  return (
    <>
      {showUrgency && (
        <div className="urgency-bar">
          Founders week: <strong>20% off Pro</strong> ends in <Countdown /> — hunters are shipping
          reports while you read this.
        </div>
      )}
      <header className="container">
        <nav className="nav">
          <Link to="/" className="logo">
            Scope<span>Recon</span>
          </Link>
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            <Link to="/pricing" className="muted" style={{ fontSize: "0.9rem" }}>
              Pricing
            </Link>
            {user ? (
              <>
                <Link to="/app" className="btn btn-ghost" style={{ padding: "0.5rem 0.9rem" }}>
                  Dashboard
                </Link>
                <button
                  className="btn btn-ghost"
                  style={{ padding: "0.5rem 0.9rem" }}
                  onClick={async () => {
                    await signOut();
                    nav("/");
                  }}
                >
                  Sign out
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="btn btn-ghost" style={{ padding: "0.5rem 0.9rem" }}>
                  Log in
                </Link>
                <Link to="/signup" className="btn btn-primary" style={{ padding: "0.5rem 0.9rem" }}>
                  Start free
                </Link>
              </>
            )}
          </div>
        </nav>
      </header>
      {children}
    </>
  );
}

function Countdown() {
  const [label, setLabel] = useState(() => fmt(endOfWeek()));
  useEffect(() => {
    const id = setInterval(() => setLabel(fmt(endOfWeek())), 1000);
    return () => clearInterval(id);
  }, []);
  return <strong className="mono">{label}</strong>;
}

function endOfWeek() {
  const d = new Date();
  const day = d.getUTCDay();
  const diff = (7 - day) % 7 || 7;
  d.setUTCDate(d.getUTCDate() + diff);
  d.setUTCHours(23, 59, 59, 0);
  return d;
}

function fmt(end: Date) {
  const ms = Math.max(0, end.getTime() - Date.now());
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  return `${h}h ${m}m ${s}s`;
}
