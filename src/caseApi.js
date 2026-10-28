/**
 * Local case API client (Cheich). Proxied in dev to http://127.0.0.1:8000.
 * No login — local only. Do not describe as secure.
 * Every POST must send Content-Type: application/json.
 */

const JSON_HEADERS = { "Content-Type": "application/json", Accept: "application/json" };

export class CaseApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "CaseApiError";
    this.status = status;
  }
}

async function parseError(res) {
  let message = `Request failed (${res.status})`;
  try {
    const body = await res.json();
    if (body?.message) message = body.message;
  } catch {
    /* keep status message */
  }
  return new CaseApiError(message, res.status);
}

async function request(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return null;
  return res.json();
}

export async function checkHealth() {
  try {
    const data = await request("/api/health");
    return { ok: Boolean(data?.ok), live_agents: Boolean(data?.live_agents), error: null };
  } catch (err) {
    return { ok: false, live_agents: false, error: err.message || "API unreachable" };
  }
}

export async function listCases() {
  return request("/api/cases");
}

export async function getCase(caseId) {
  return request(`/api/cases/${encodeURIComponent(caseId)}`);
}

export async function approveCase(caseId, acknowledgeOpenIssues = false) {
  return request(`/api/cases/${encodeURIComponent(caseId)}/approve`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ acknowledge_open_issues: Boolean(acknowledgeOpenIssues) }),
  });
}

export async function rejectCase(caseId) {
  return request(`/api/cases/${encodeURIComponent(caseId)}/reject`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({}),
  });
}

export async function changeDemand(caseId, changes, newCaseId = null) {
  const body = { changes };
  if (newCaseId) body.new_case_id = newCaseId;
  return request(`/api/cases/${encodeURIComponent(caseId)}/change-demand`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

/** Report call-outs on a case waiting for approval. Needs NURSESYNC_LIVE=1. Costs money (~$0.15–$1.20). */
export async function reportCallOut(caseId, callOuts) {
  return request(`/api/cases/${encodeURIComponent(caseId)}/call-out`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ call_outs: callOuts }),
  });
}

/** Nurse ids and names, so the view can show names. Free. */
export async function getRoster() {
  return request("/api/roster");
}

/** Start a weekly run (background). Needs NURSESYNC_LIVE=1. Costs money (~$0.50–$1.50). */
export async function startWeeklyRun(unit, weekStart, caseId = null) {
  const body = { unit, week_start: weekStart };
  if (caseId) body.case_id = caseId;
  return request("/api/runs", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

export async function getRun(runId) {
  return request(`/api/runs/${encodeURIComponent(runId)}`);
}

/** Daily paid-ops remaining. Returns null fields when the server has no cap. */
export async function getUsage() {
  return request("/api/usage");
}

export function formatCaseOption(summary) {
  const status = (summary.status || "").replace(/_/g, " ");
  const outcome = summary.outcome ? ` · ${summary.outcome.replace(/_/g, " ")}` : "";
  return `${summary.case_id} — ${status}${outcome}`;
}
