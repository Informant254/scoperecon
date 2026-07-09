import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Shell } from "../components/Shell";
import { ApiError, Me, billing, me } from "../lib/api";

export function Billing() {
  const [profile, setProfile] = useState<Me | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [params] = useSearchParams();

  useEffect(() => {
    if (params.get("checkout") === "success") {
      setOk(
        "Payment received. Entitlements sync via Stripe webhook (usually <10s). Refresh if plan still free."
      );
    }
    me.get()
      .then(setProfile)
      .catch((e) => setErr(e instanceof ApiError ? e.message : "load_failed"));
  }, [params]);

  async function openPortal() {
    setBusy(true);
    setErr(null);
    try {
      const { portal_url } = await billing.portal();
      window.location.href = portal_url;
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "portal_failed");
      setBusy(false);
    }
  }

  async function upgrade(plan: "pro" | "team") {
    setBusy(true);
    setErr(null);
    try {
      const { checkout_url } = await billing.checkout(plan);
      window.location.href = checkout_url;
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "checkout_failed");
      setBusy(false);
    }
  }

  return (
    <Shell>
      <main className="container" style={{ maxWidth: 640, padding: "2rem 0 4rem" }}>
        <Link to="/app" className="muted mono" style={{ fontSize: "0.85rem" }}>
          ← dashboard
        </Link>
        <h1 style={{ marginTop: "0.75rem" }}>Billing</h1>
        {ok && <p className="success">{ok}</p>}
        {err && <p className="error">{err}</p>}

        <div className="card" style={{ marginTop: "1rem" }}>
          <div className="label">Current plan</div>
          <div className="mono" style={{ fontSize: "1.6rem" }}>
            {profile?.plan ?? "…"}
          </div>
          <p className="muted mono">
            status={profile?.subscription_status ?? "—"} · quota={profile?.scans_used_this_month}/
            {profile?.scan_quota_monthly}
          </p>
          {profile?.current_period_end && (
            <p className="muted">Period ends {new Date(profile.current_period_end).toLocaleString()}</p>
          )}
        </div>

        <div className="grid-2" style={{ marginTop: "1rem" }}>
          <button className="btn btn-primary" disabled={busy} onClick={() => upgrade("pro")}>
            Upgrade Pro $29
          </button>
          <button className="btn btn-ghost" disabled={busy} onClick={() => upgrade("team")}>
            Upgrade Team $99
          </button>
        </div>
        <button
          className="btn btn-ghost"
          style={{ marginTop: "0.75rem", width: "100%" }}
          disabled={busy || !profile?.plan || profile.plan === "free"}
          onClick={openPortal}
        >
          Manage subscription (Stripe portal)
        </button>
        <p className="mono muted" style={{ fontSize: "0.75rem", marginTop: "1rem" }}>
          Plan changes are applied only after verified Stripe webhooks. Client cannot self-elevate.
        </p>
      </main>
    </Shell>
  );
}
