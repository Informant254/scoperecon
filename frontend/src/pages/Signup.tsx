import { FormEvent, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Shell } from "../components/Shell";
import { useAuth } from "../lib/auth";

export function Signup() {
  const { signUp, signIn } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const plan = params.get("plan");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const headline = useMemo(() => {
    if (plan === "pro") return "Create account → unlock Hunter";
    if (plan === "team") return "Create account → unlock Crew";
    return "Create your free recon seat";
  }, [plan]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await signUp(email.trim(), password, fullName.trim());
      try {
        await signIn(email.trim(), password);
      } catch {
        /* email confirm may be required */
      }
      if (plan === "pro" || plan === "team") {
        nav(`/pricing`);
        return;
      }
      nav("/app");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "signup_failed");
      setBusy(false);
    }
  }

  return (
    <Shell showUrgency>
      <main className="container" style={{ maxWidth: 460, padding: "3rem 0" }}>
        <h1>{headline}</h1>
        <p className="muted">5 free scans. No card. Upgrade only when the queue is full of money.</p>
        <form onSubmit={onSubmit} className="card" style={{ display: "grid", gap: "0.9rem", marginTop: "1.5rem" }}>
          <div>
            <label className="label">Name</label>
            <input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Hunter handle" />
          </div>
          <div>
            <label className="label">Email</label>
            <input className="input" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="label">Password</label>
            <input className="input" type="password" required minLength={10} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          {err && <p className="error">{err}</p>}
          <button className="btn btn-primary" disabled={busy} type="submit">
            {busy ? "Creating…" : "Start free recon"}
          </button>
          <p className="mono muted" style={{ fontSize: "0.72rem", margin: 0 }}>
            By continuing you agree to lawful use of recon tools against authorized scopes only.
          </p>
        </form>
        <p className="muted" style={{ marginTop: "1rem" }}>
          Have an account? <Link to="/login">Log in</Link>
        </p>
      </main>
    </Shell>
  );
}
