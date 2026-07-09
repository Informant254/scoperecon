import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { useAuth } from "../lib/auth";

export function Login() {
  const { signIn } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await signIn(email.trim(), password);
      nav("/app");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "login_failed");
      setBusy(false);
    }
  }

  return (
    <Shell>
      <main className="container" style={{ maxWidth: 440, padding: "3rem 0" }}>
        <h1>Welcome back</h1>
        <p className="muted">Your programs, scans, and payout queue are waiting.</p>
        <form onSubmit={onSubmit} className="card" style={{ display: "grid", gap: "0.9rem", marginTop: "1.5rem" }}>
          <div>
            <label className="label">Email</label>
            <input className="input" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="label">Password</label>
            <input className="input" type="password" required minLength={8} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          {err && <p className="error">{err}</p>}
          <button className="btn btn-primary" disabled={busy} type="submit">
            {busy ? "Signing in…" : "Enter dashboard"}
          </button>
        </form>
        <p className="muted" style={{ marginTop: "1rem" }}>
          New here? <Link to="/signup">Create free account</Link>
        </p>
      </main>
    </Shell>
  );
}
