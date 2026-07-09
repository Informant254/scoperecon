import { Link } from "react-router-dom";
import { Shell } from "../components/Shell";

export function Landing() {
  return (
    <Shell showUrgency>
      <main className="hero-glow">
        <section className="container" style={{ padding: "4rem 0 2rem" }}>
          <p className="mono muted" style={{ marginBottom: "1rem" }}>
            // bug bounty recon OS for paid hunters
          </p>
          <h1
            style={{
              fontSize: "clamp(2.4rem, 6vw, 4.2rem)",
              lineHeight: 1.05,
              letterSpacing: "-0.04em",
              maxWidth: "14ch",
              margin: "0 0 1.25rem",
            }}
          >
            Ship recon in minutes.
            <br />
            <span style={{ color: "var(--accent)" }}>Cash bounties faster.</span>
          </h1>
          <p className="muted" style={{ maxWidth: 560, fontSize: "1.1rem", lineHeight: 1.55 }}>
            ScopeRecon maps in-scope assets, fingerprints tech, flags takeover candidates, and ranks
            payout potential — so you spend time on reports, not dig + curl soup.
          </p>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginTop: "1.75rem" }}>
            <Link to="/signup" className="btn btn-primary">
              Run free recon →
            </Link>
            <Link to="/pricing" className="btn btn-ghost">
              See plans
            </Link>
          </div>
          <p className="mono muted" style={{ marginTop: "1rem", fontSize: "0.8rem" }}>
            Free: 5 scans/mo · No card · Cancel anytime on Pro
          </p>
        </section>

        <section className="container grid-3" style={{ padding: "1rem 0 3rem" }}>
          {[
            ["Asset graph", "Domains, subs, tech stack, risk scores — one program board."],
            ["Takeover radar", "Dangling CNAMEs + HTTP fingerprints before someone else files."],
            ["Payout estimate", "Severity-weighted bounty estimates so you prioritize ROI."],
          ].map(([t, d]) => (
            <div key={t} className="card">
              <h3 style={{ margin: "0 0 0.5rem" }}>{t}</h3>
              <p className="muted" style={{ margin: 0, lineHeight: 1.5 }}>
                {d}
              </p>
            </div>
          ))}
        </section>

        <section className="container" style={{ paddingBottom: "5rem" }}>
          <div className="card" style={{ display: "grid", gap: "1rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
              <div>
                <h2 style={{ margin: 0 }}>Average hunter waste</h2>
                <p className="muted" style={{ margin: "0.4rem 0 0" }}>
                  Manual recon before first valid asset map
                </p>
              </div>
              <div className="mono" style={{ fontSize: "2rem", color: "var(--danger)" }}>
                4–12 hrs
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
              <div>
                <h2 style={{ margin: 0 }}>With ScopeRecon</h2>
                <p className="muted" style={{ margin: "0.4rem 0 0" }}>
                  Passive recon pass + ranked findings queue
                </p>
              </div>
              <div className="mono" style={{ fontSize: "2rem", color: "var(--accent)" }}>
                &lt; 3 min
              </div>
            </div>
            <Link to="/signup" className="btn btn-primary" style={{ width: "fit-content" }}>
              Claim my free scans
            </Link>
          </div>
        </section>
      </main>

      <div className="sticky-cta">
        <Link to="/signup" className="btn btn-primary">
          Start free — 5 scans
        </Link>
        <Link to="/pricing" className="btn btn-ghost">
          Upgrade later
        </Link>
      </div>
    </Shell>
  );
}
