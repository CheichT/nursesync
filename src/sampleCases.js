/**
 * Sample CaseRecords from docs/sample-cases/ (Cheich).
 * Fallback when the local case API is offline. Prefer src/caseApi.js in the approval UI.
 */

const loaders = import.meta.glob("../docs/sample-cases/*.json");

export const SAMPLE_CATALOG = [
  { key: "passed", label: "Passed — clean week" },
  { key: "needs_review", label: "Needs review — flags, still built" },
  { key: "open_issues", label: "Open issues — after 3 rounds" },
  { key: "stopped_missing_input", label: "Stopped — missing input (no draft)" },
  { key: "approved", label: "Approved" },
  { key: "approved_with_open_issues", label: "Approved with open issues" },
  { key: "rejected", label: "Rejected" },
  { key: "demand_change_old", label: "Demand change — old (out of date)" },
  { key: "demand_change_child", label: "Demand change — child" },
  { key: "call_out_old", label: "Call-out — old (out of date)" },
  { key: "call_out_child", label: "Call-out — child" },
];

const cache = {};

function pathFor(key) {
  return `../docs/sample-cases/${key}.json`;
}

export async function loadSampleCase(key) {
  if (cache[key]) return cloneCase(cache[key]);
  const loader = loaders[pathFor(key)];
  if (!loader) throw new Error(`Unknown sample case: ${key}`);
  const mod = await loader();
  cache[key] = mod.default ?? mod;
  return cloneCase(cache[key]);
}

export function cloneCase(record) {
  return JSON.parse(JSON.stringify(record));
}

export async function sampleKeyForCaseId(caseId) {
  if (!caseId) return null;
  for (const { key } of SAMPLE_CATALOG) {
    const rec = cache[key] || (await loadSampleCase(key));
    if (rec.case_id === caseId) return key;
  }
  return null;
}

/** Mirrors backend/app/decisions.py has_open_issues. */
export function hasOpenIssues(record) {
  return Boolean(
    (record.open_violations && record.open_violations.length) ||
      (record.unfixable && record.unfixable.length) ||
      (record.final_draft && record.final_draft.open_gaps && record.final_draft.open_gaps.length)
  );
}

function stamp() {
  return new Date().toISOString().slice(0, 19);
}

export function canTryApprove(record) {
  return record.status === "waiting_approval" && record.final_draft != null;
}

export function canReject(record) {
  return record.status === "waiting_approval";
}

export function canChangeDemand(record) {
  return record.status === "waiting_approval";
}

/**
 * Local approve (no API). Same refuse rules as decisions.approve.
 * Returns { ok, record?, message? }.
 */
export function approveLocal(record, acknowledgeOpenIssues = false) {
  if (record.status === "out_of_date") {
    const newer = record.newer_case_id ? ` Review case ${record.newer_case_id} instead.` : "";
    return { ok: false, message: `This draft is out of date: a newer one exists.${newer}` };
  }
  if (record.status !== "waiting_approval") {
    return { ok: false, message: `This case is already ${record.status}. A decided case cannot be changed.` };
  }
  if (record.final_draft == null) {
    return {
      ok: false,
      message:
        record.stop_reason ||
        "No valid draft was produced, so there is nothing to approve. Change a demand number, or reject and build the week by hand.",
    };
  }
  if (hasOpenIssues(record) && !acknowledgeOpenIssues) {
    return {
      ok: false,
      message:
        "This draft still has open issues (rule violations, unfixable rows or unstaffed shifts). Approve only after confirming you accept them.",
    };
  }
  const open = hasOpenIssues(record);
  return {
    ok: true,
    record: {
      ...record,
      status: "approved",
      manager_decision: "approved",
      decision_time: stamp(),
      decision_details: {
        action: "approve",
        demand_changes: [],
        acknowledged_open_issues: open,
        new_case_id: null,
      },
    },
  };
}

export function rejectLocal(record) {
  if (record.status === "out_of_date") {
    const newer = record.newer_case_id ? ` Review case ${record.newer_case_id} instead.` : "";
    return { ok: false, message: `This draft is out of date: a newer one exists.${newer}` };
  }
  if (record.status !== "waiting_approval") {
    return { ok: false, message: `This case is already ${record.status}. A decided case cannot be changed.` };
  }
  return {
    ok: true,
    record: {
      ...record,
      status: "rejected",
      outcome: "rejected",
      manager_decision: "rejected",
      decision_time: stamp(),
      decision_details: {
        action: "reject",
        demand_changes: [],
        acknowledged_open_issues: false,
        new_case_id: null,
      },
    },
  };
}

export async function demandChangeChildCaseId() {
  const child = await loadSampleCase("demand_change_child");
  return child.case_id;
}
