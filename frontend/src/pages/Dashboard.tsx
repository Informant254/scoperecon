import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Shell } from "../components/Shell";
import { ApiError, Dashboard as Dash, me } from "../lib/api";

export function Dashboard() {
  const [data, setData] = useState<Dash | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    me.dashboard()
      .then(setData)
      .catch((e) => setErr(e instanceof ApiError ? e.message : "load_failed"));
  }, []);

  const remaining =
    data ? Math.max(0, data.profile.scan_quota_monthly - data.profile.scans_used_this_month) : 0;
  const lowQuota = data && remaining <= 2 && data.profile.plan === "free";

  return (
    <Shell>
      <main className="container" style={{ padding: "2rem 0 4rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
          <div>
            <h1 style={{ marginBottom: 0 }}>Command center</h1>
            <p className="muted mono" style={{ marginTop: "0.35rem" }}>
              plan={data?.profile.plan ?? "…"} · scans left={remaining}
            </p>
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <Link to="/app/scan" className="btn btn-primary">
              New scan
            </Link>
            <Link to="/app/billing" className="btn btn-ghost">
              Billing
            </Link>
          </div>
        </div>

        {lowQuota && (
          <div className="card" style={{ marginTop: "1rem", borderColor: "rgba(61,255,154,0.4)" }}>
            <strong>Quota almost gone.</strong>{" "}
            <span className="muted">Hunters on Pro run 200 scans/mo — don't stall mid-program.</span>
            <div style={{ marginTop: "0.75rem" }}>
              <Link to="/pricing" className="btn btn-primary">
                Upgrade to Hunter — $29
              </Link>
            </div>
          </div>
        )}

        {err && <p className="error">{err}</p>}

        <div className="grid-3" style={{ marginTop: "1.25rem" }}>
          <Stat label="Assets mapped" value={data?.stats.assets ?? "—"} />
          <Stat label="Findings" value={data?.stats.findings ?? "—"} />
          <Stat
            label="Est. bounty pipeline"
            value={
              data ? `$${Math.round(data.stats.bounty_estimate_usd).toLocaleString()}` : "—"
            }
            accent
          />
        </div>

        <div className="grid-2" style={{ marginTop: "1.25rem" }}>
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Top risk assets</h3>
            <table className="table">
              <thead>
                <tr>
                  <th>Asset</th>
                  <th>Type</th>
                  <th>Risk</th>
                </tr>
              </thead>
              <tbody>
                {(data?.assets || []).slice(0, 8).map((a) => (
                  <tr key={a.id}>
                    <td>{a.value}</td>
                    <td>{a.asset_type}</td>
                    <td>{Number(a.risk_score).toFixed(0)}</td>
                  </tr>
                ))}
                {!data?.assets?.length && (
                  <tr>
                    <td colSpan={3} className="muted">
                      No assets yet — run your first scan.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>Latest findings</h3>
            <table className="table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Sev</th>
                  <th>$ est</th>
                </tr>
              </thead>
              <tbody>
                {(data?.findings || []).slice(0, 8).map((f) => (
                  <tr key={f.id}>
                    <td>{f.title}</td>
                    <td>
                      <span className={`badge badge-${f.severity}`}>{f.severity}</span>
                    </td>
                    <td>{f.bounty_estimate_usd ? `$${f.bounty_estimate_usd}` : "—"}</td>
                  </tr>
                ))}
                {!data?.findings?.length && (
                  <tr>
                    <td colSpan={3} className="muted">
                      Findings land here after recon completes.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card" style={{ marginTop: "1.25rem" }}>
          <h3 style={{ marginTop: 0 }}>Recent scans</h3>
          <table className="table">
            <thead>
              <tr>
                <th>Target</th>
                <th>Status</th>
                <th>Progress</th>
                <th>Assets</th>
                <th>Findings</th>
              </tr>
            </thead>
            <tbody>
              {(data?.scans || []).map((s) => (
                <tr key={s.id}>
                  <td>{s.target_seed}</td>
                  <td>{s.status}</td>
                  <td>{s.progress}%</td>
                  <td>{s.assets_discovered}</td>
                  <td>{s.findings_count}</td>
                </tr>
              ))}
              {!data?.scans?.length && (
                <tr>
                  <td colSpan={5} className="muted">
                    No scans yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </main>
    </Shell>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string | number;
  accent?: boolean;
}) {
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className="mono" style={{ fontSize: "1.8rem", color: accent ? "var(--accent)" : undefined }}>
        {value}
      </div>
    </div>
  );
}
