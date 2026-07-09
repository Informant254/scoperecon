import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { ApiError, Program, programs, scans } from "../lib/api";

export function NewScan() {
  const nav = useNavigate();
  const [items, setItems] = useState<Program[]>([]);
  const [programId, setProgramId] = useState("");
  const [newProgram, setNewProgram] = useState("");
  const [target, setTarget] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    programs
      .list()
      .then((r) => {
        setItems(r.items);
        if (r.items[0]) setProgramId(r.items[0].id);
      })
      .catch((e) => setErr(e instanceof ApiError ? e.message : "load_failed"));
  }, []);

  async function ensureProgram(): Promise<string> {
    if (programId) return programId;
    if (!newProgram.trim()) throw new Error("program_required");
    const p = await programs.create({ name: newProgram.trim(), platform: "private" });
    setItems((prev) => [p, ...prev]);
    setProgramId(p.id);
    return p.id;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const pid = await ensureProgram();
      const idem = `scan_${pid}_${target.trim().toLowerCase()}_${Date.now()}`;
      await scans.create({
        program_id: pid,
        target_seed: target.trim(),
        idempotency_key: idem,
      });
      nav("/app");
    } catch (ex) {
      const msg = ex instanceof ApiError ? ex.message : ex instanceof Error ? ex.message : "failed";
      if (msg === "quota_exceeded") {
        setErr("Scan quota exceeded — upgrade to keep hunting.");
      } else {
        setErr(msg);
      }
      setBusy(false);
    }
  }

  return (
    <Shell>
      <main className="container" style={{ maxWidth: 560, padding: "2rem 0 4rem" }}>
        <Link to="/app" className="muted mono" style={{ fontSize: "0.85rem" }}>
          ← dashboard
        </Link>
        <h1 style={{ marginTop: "0.75rem" }}>Launch passive recon</h1>
        <p className="muted">Authorized scope only. We block private IPs & metadata endpoints.</p>

        <form className="card" style={{ display: "grid", gap: "1rem", marginTop: "1.25rem" }} onSubmit={onSubmit}>
          <div>
            <label className="label">Program</label>
            {items.length > 0 ? (
              <select className="input" value={programId} onChange={(e) => setProgramId(e.target.value)}>
                {items.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            ) : (
              <input
                className="input"
                placeholder="e.g. Acme BB Private"
                value={newProgram}
                onChange={(e) => setNewProgram(e.target.value)}
                required
              />
            )}
          </div>
          {items.length > 0 && (
            <div>
              <label className="label">Or create new program</label>
              <input
                className="input"
                placeholder="Optional new program name"
                value={newProgram}
                onChange={(e) => {
                  setNewProgram(e.target.value);
                  if (e.target.value) setProgramId("");
                }}
              />
            </div>
          )}
          <div>
            <label className="label">Root domain / seed</label>
            <input
              className="input"
              placeholder="example.com"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              required
              pattern="^[A-Za-z0-9.-]+$"
              title="Domain only"
            />
          </div>
          {err && (
            <div>
              <p className="error">{err}</p>
              {err.includes("quota") && (
                <Link to="/pricing" className="btn btn-primary" style={{ marginTop: "0.5rem" }}>
                  Upgrade now
                </Link>
              )}
            </div>
          )}
          <button className="btn btn-primary" type="submit" disabled={busy}>
            {busy ? "Queueing…" : "Start scan"}
          </button>
        </form>
      </main>
    </Shell>
  );
}
