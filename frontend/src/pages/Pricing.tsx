import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { useAuth } from "../lib/auth";
import { billing, ApiError } from "../lib/api";

const PLANS = [
  {
    id: "free" as const,
    name: "Scout",
    price: "$0",
    blurb: "Prove the workflow on real targets.",
    features: ["5 passive scans / month", "3 programs", "Asset + finding board", "Community support"],
    cta: "Start free",
    featured: false,
  },
  {
    id: "pro" as const,
    name: "Hunter",
    price: "$29",
    blurb: "For hunters shipping weekly reports.",
    features: [
      "200 scans / month",
      "50 programs",
      "API key access",
      "Takeover priority scoring",
      "Email digest",
    ],
    cta: "Go Pro — ship faster",
    featured: true,
  },
  {
    id: "team" as const,
    name: "Crew",
    price: "$99",
    blurb: "Small teams splitting scope & payouts.",
    features: ["1000 scans / month", "500 programs", "Shared workspace*", "Priority queue", "SSO-ready*"],
    cta: "Scale the crew",
    featured: false,
  },
];

export function Pricing() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function choose(plan: "free" | "pro" | "team") {
    setErr(null);
    if (plan === "free") {
      nav(user ? "/app" : "/signup");
      return;
    }
    if (!user) {
      nav(`/signup?plan=${plan}`);
      return;
    }
    setBusy(plan);
    try {
      const { checkout_url } = await billing.checkout(plan);
      window.location.href = checkout_url;
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "checkout_failed");
      setBusy(null);
    }
  }

  return (
    <Shell showUrgency>
      <main className="container" style={{ padding: "3rem 0 6rem" }}>
        <h1 style={{ letterSpacing: "-0.03em", marginBottom: "0.5rem" }}>Pricing that pays for itself</h1>
        <p className="muted" style={{ maxWidth: 520, marginBottom: "2rem" }}>
          One medium bounty covers months of Pro. Cancel in the customer portal — no dark patterns on
          the way out.
        </p>
        {err && <p className="error">{err}</p>}
        <div className="grid-3">
          {PLANS.map((p) => (
            <div key={p.id} className={`card price-card ${p.featured ? "featured" : ""}`}>
              {p.featured && (
                <div className="badge badge-low" style={{ marginBottom: "0.75rem" }}>
                  most popular
                </div>
              )}
              <h2 style={{ margin: "0 0 0.25rem" }}>{p.name}</h2>
              <div className="mono" style={{ fontSize: "2rem", marginBottom: "0.25rem" }}>
                {p.price}
                <span className="muted" style={{ fontSize: "0.9rem" }}>
                  /mo
                </span>
              </div>
              <p className="muted" style={{ minHeight: 44 }}>
                {p.blurb}
              </p>
              <ul style={{ paddingLeft: "1.1rem", lineHeight: 1.7, margin: "1rem 0 1.25rem" }}>
                {p.features.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
              <button
                className={`btn ${p.featured ? "btn-primary" : "btn-ghost"}`}
                style={{ width: "100%" }}
                disabled={busy === p.id}
                onClick={() => choose(p.id)}
              >
                {busy === p.id ? "Redirecting…" : p.cta}
              </button>
            </div>
          ))}
        </div>
        <p className="mono muted" style={{ marginTop: "1.5rem", fontSize: "0.75rem" }}>
          * Crew multi-seat & SSO rolling out; billed as Team tier now. Prices in USD via Stripe.
        </p>
        <p style={{ marginTop: "1rem" }}>
          <Link to="/login" className="muted">
            Already hunting? Log in →
          </Link>
        </p>
      </main>
    </Shell>
  );
}
