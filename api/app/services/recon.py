from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import dns.resolver
import httpx

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$"
)

# Block SSRF: private, link-local, metadata endpoints
BLOCKED_HOSTS = {
    "localhost",
    "metadata.google.internal",
    "metadata",
}
BLOCKED_SUFFIXES = (".local", ".internal", ".localhost")


@dataclass
class ReconResult:
    assets: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def normalize_seed(seed: str) -> str:
    seed = seed.strip().lower()
    if "://" in seed:
        parsed = urlparse(seed)
        host = parsed.hostname or ""
        return host.strip(".")
    return seed.strip().strip(".").split("/")[0]


def is_safe_public_host(host: str) -> bool:
    host = host.lower().strip(".")
    if not host or host in BLOCKED_HOSTS:
        return False
    if any(host.endswith(s) for s in BLOCKED_SUFFIXES):
        return False
    if host == "0.0.0.0" or host.startswith("127."):
        return False
    # IP literal
    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
        # Cloud metadata ranges
        if ip in ipaddress.ip_network("169.254.0.0/16"):
            return False
        return True
    except ValueError:
        pass
    if not DOMAIN_RE.match(host):
        return False
    # Resolve and re-check (DNS rebinding defense: resolve once, verify all A/AAAA)
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True  # allow queue; recon will record NXDOMAIN-style finding later
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
                or ip in ipaddress.ip_network("169.254.0.0/16")
            ):
                return False
        except ValueError:
            return False
    return True


COMMON_SUBDOMAINS = [
    "www",
    "api",
    "app",
    "admin",
    "staging",
    "dev",
    "test",
    "portal",
    "mail",
    "vpn",
    "cdn",
    "static",
    "assets",
    "auth",
    "sso",
    "dashboard",
    "beta",
    "status",
    "docs",
    "git",
    "gitlab",
    "jenkins",
    "ci",
    "grafana",
    "kibana",
    "prometheus",
    "sentry",
]


TAKEOVER_FINGERPRINTS = [
    ("NoSuchBucket", "aws_s3", "high"),
    ("No Such Account", "github_pages", "high"),
    ("There's nothing here", "heroku", "medium"),
    ("do you want to register", "unclaimed", "medium"),
    ("The specified bucket does not exist", "aws_s3", "high"),
    ("Repository not found", "github", "medium"),
    ("project not found", "gitlab", "medium"),
]


class PassiveReconEngine:
    """High-signal passive recon. No active exploitation. SSRF-hardened."""

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout
        self.resolver = dns.resolver.Resolver()
        self.resolver.lifetime = timeout
        self.resolver.timeout = timeout

    async def run(self, seed: str) -> ReconResult:
        domain = normalize_seed(seed)
        result = ReconResult()
        if not domain or not is_safe_public_host(domain):
            result.errors.append("unsafe_or_invalid_target")
            return result

        result.assets.append(
            {
                "asset_type": "domain",
                "value": domain,
                "risk_score": 10,
                "tech_stack": [],
                "metadata": {"source": "seed"},
            }
        )

        # DNS records
        for rtype in ("A", "AAAA", "MX", "NS", "TXT", "CNAME"):
            try:
                answers = await asyncio.to_thread(self._resolve, domain, rtype)
                for ans in answers:
                    result.findings.append(
                        {
                            "title": f"DNS {rtype}: {ans[:120]}",
                            "description": f"{domain} {rtype} record",
                            "severity": "info",
                            "category": "dns",
                            "evidence": {"type": rtype, "value": ans},
                        }
                    )
            except Exception:
                continue

        # Subdomain candidates (passive dictionary + DNS only)
        discovered = await self._enum_subdomains(domain)
        for sub in discovered:
            if not is_safe_public_host(sub):
                continue
            result.assets.append(
                {
                    "asset_type": "subdomain",
                    "value": sub,
                    "risk_score": 25,
                    "tech_stack": [],
                    "metadata": {"source": "dns_bruteforce_passive"},
                }
            )
            takeover = await self._check_takeover_signals(sub)
            if takeover:
                result.findings.append(takeover)

        # HTTP fingerprint root + www
        for host in {domain, f"www.{domain}"} | set(discovered[:15]):
            if not is_safe_public_host(host):
                continue
            fp = await self._http_fingerprint(host)
            if fp:
                tech = fp.get("tech") or []
                for a in result.assets:
                    if a["value"] == host:
                        a["tech_stack"] = tech
                        a["risk_score"] = max(float(a["risk_score"]), float(fp.get("risk", 20)))
                result.findings.extend(fp.get("findings") or [])

        return result

    def _resolve(self, name: str, rtype: str) -> list[str]:
        try:
            answers = self.resolver.resolve(name, rtype)
            return [r.to_text() for r in answers]
        except Exception as exc:
            raise exc

    async def _enum_subdomains(self, domain: str) -> list[str]:
        found: list[str] = []

        async def check(sub: str) -> None:
            fqdn = f"{sub}.{domain}"
            try:
                await asyncio.to_thread(self._resolve, fqdn, "A")
                found.append(fqdn)
            except Exception:
                try:
                    await asyncio.to_thread(self._resolve, fqdn, "CNAME")
                    found.append(fqdn)
                except Exception:
                    return

        await asyncio.gather(*(check(s) for s in COMMON_SUBDOMAINS))
        return sorted(set(found))

    async def _http_fingerprint(self, host: str) -> dict[str, Any] | None:
        # Force HTTPS first; no redirects to private IPs (httpx default follows — disable)
        urls = [f"https://{host}/", f"http://{host}/"]
        tech: list[str] = []
        findings: list[dict[str, Any]] = []
        risk = 15.0

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=False,
            headers={"User-Agent": "ScopeReconBot/1.0 (+https://scoperecon.app/bot)"},
            verify=True,
        ) as client:
            for url in urls:
                try:
                    resp = await client.get(url)
                except Exception:
                    continue
                server = resp.headers.get("server")
                powered = resp.headers.get("x-powered-by")
                if server:
                    tech.append(f"server:{server[:80]}")
                if powered:
                    tech.append(f"powered_by:{powered[:80]}")
                    risk = max(risk, 30)
                    findings.append(
                        {
                            "title": f"X-Powered-By exposed on {host}",
                            "description": powered[:200],
                            "severity": "low",
                            "category": "tech",
                            "evidence": {"header": "x-powered-by", "value": powered[:200]},
                        }
                    )
                # Security headers missing
                if "strict-transport-security" not in {k.lower() for k in resp.headers.keys()}:
                    if url.startswith("https://"):
                        findings.append(
                            {
                                "title": f"Missing HSTS on {host}",
                                "description": "Strict-Transport-Security header not present",
                                "severity": "low",
                                "category": "tech",
                                "evidence": {"url": url, "status": resp.status_code},
                            }
                        )
                if resp.status_code in (401, 403) and any(
                    x in host for x in ("admin", "jenkins", "grafana", "kibana", "prometheus")
                ):
                    findings.append(
                        {
                            "title": f"Exposed admin/tooling surface: {host}",
                            "description": f"HTTP {resp.status_code} on sensitive hostname",
                            "severity": "medium",
                            "category": "exposed_panel",
                            "evidence": {"url": url, "status": resp.status_code},
                            "bounty_estimate_usd": 250,
                        }
                    )
                    risk = max(risk, 55)
                body = resp.text[:4000] if resp.text else ""
                for needle, vendor, sev in TAKEOVER_FINGERPRINTS:
                    if needle.lower() in body.lower():
                        findings.append(
                            {
                                "title": f"Possible subdomain takeover ({vendor}) on {host}",
                                "description": f"Fingerprint matched: {needle}",
                                "severity": sev,
                                "category": "takeover",
                                "evidence": {"url": url, "fingerprint": needle, "vendor": vendor},
                                "bounty_estimate_usd": 500 if sev == "high" else 200,
                            }
                        )
                        risk = max(risk, 80 if sev == "high" else 60)
                break  # one successful scheme enough
        if not tech and not findings:
            return {"tech": tech, "findings": findings, "risk": risk}
        return {"tech": tech, "findings": findings, "risk": risk}

    async def _check_takeover_signals(self, host: str) -> dict[str, Any] | None:
        try:
            cnames = await asyncio.to_thread(self._resolve, host, "CNAME")
        except Exception:
            return None
        dangling_providers = (
            "github.io",
            "herokuapp.com",
            "s3.amazonaws.com",
            "cloudfront.net",
            "azurewebsites.net",
            "ghost.io",
            "pantheonsite.io",
        )
        for c in cnames:
            c_clean = c.rstrip(".")
            if any(p in c_clean for p in dangling_providers):
                return {
                    "title": f"Dangling CNAME on {host}",
                    "description": f"CNAME → {c_clean} (verify takeover)",
                    "severity": "medium",
                    "category": "takeover",
                    "evidence": {"cname": c_clean},
                    "bounty_estimate_usd": 300,
                }
        return None
