import { supabase } from "./supabase";

const API_URL = (import.meta.env.VITE_API_URL as string)?.replace(/\/$/, "") || "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function authHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new ApiError(401, "not_authenticated");
  return { Authorization: `Bearer ${token}` };
}

export async function api<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  Object.assign(headers, await authHeader());

  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    credentials: "omit",
  });

  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = { detail: text };
  }

  if (!res.ok) {
    const detail =
      typeof body === "object" && body && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : res.statusText;
    throw new ApiError(res.status, detail);
  }
  return body as T;
}

export const billing = {
  checkout: (plan: "pro" | "team") =>
    api<{ checkout_url: string; session_id: string }>("/v1/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ plan }),
    }),
  portal: () =>
    api<{ portal_url: string }>("/v1/billing/portal", { method: "POST" }),
};

export const programs = {
  list: () => api<{ items: Program[] }>("/v1/programs"),
  create: (payload: Partial<Program> & { name: string }) =>
    api<Program>("/v1/programs", { method: "POST", body: JSON.stringify(payload) }),
};

export const scans = {
  create: (payload: {
    program_id: string;
    target_seed: string;
    idempotency_key?: string;
  }) => api<Scan>("/v1/scans", { method: "POST", body: JSON.stringify(payload) }),
  get: (id: string) => api<Scan>(`/v1/scans/${id}`),
};

export const me = {
  get: () => api<Me>("/v1/me"),
  dashboard: () => api<Dashboard>("/v1/dashboard"),
};

export type Me = {
  id: string;
  email: string;
  plan: string;
  subscription_status: string;
  scan_quota_monthly: number;
  scans_used_this_month: number;
  current_period_end: string | null;
  onboarding_completed: boolean;
};

export type Program = {
  id: string;
  name: string;
  platform?: string | null;
  program_url?: string | null;
  handle?: string | null;
};

export type Scan = {
  id: string;
  status: string;
  target_seed: string;
  progress: number;
  assets_discovered: number;
  findings_count: number;
  created_at: string;
  error_message?: string | null;
};

export type Dashboard = {
  profile: {
    plan: string;
    scans_used_this_month: number;
    scan_quota_monthly: number;
  };
  stats: {
    assets: number;
    findings: number;
    bounty_estimate_usd: number;
    critical_high: number;
  };
  assets: Array<{
    id: string;
    value: string;
    asset_type: string;
    risk_score: number;
    last_seen_at?: string;
  }>;
  findings: Array<{
    id: string;
    title: string;
    severity: string;
    status: string;
    category?: string;
    bounty_estimate_usd?: number;
    created_at: string;
  }>;
  scans: Scan[];
};
