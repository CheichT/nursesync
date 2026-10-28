import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle, XCircle } from "lucide-react";
import {
  SAMPLE_CATALOG,
  loadSampleCase,
  sampleKeyForCaseId,
  demandChangeChildCaseId,
  hasOpenIssues,
  canTryApprove,
  canReject,
  canChangeDemand,
  approveLocal,
  rejectLocal,
} from "./sampleCases";
import {
  checkHealth,
  listCases,
  getCase,
  approveCase,
  rejectCase,
  changeDemand,
  reportCallOut,
  getRoster,
  startWeeklyRun,
  getRun,
  getUsage,
  formatCaseOption,
  CaseApiError,
} from "./caseApi";

const SHIFT_LABEL = { day: "Day 07:00–19:00", night: "Night 19:00–07:00" };
/** Mock data only for now (Cheich #46). */
const DEFAULT_RUN_UNIT = "7W";
const DEFAULT_RUN_WEEK = "2026-11-02";
const RUN_POLL_MS = 5000;

function addDays(iso, n) {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

function fmtDay(iso) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function StatusStamp({ status, outcome }) {
  const text = outcome ? `${status} · ${outcome}` : status;
  return <span className="stamp">{text.replace(/_/g, " ")}</span>;
}

function AttentionList({ title, children, empty }) {
  if (empty) return null;
  return (
    <section className="card approval-block" aria-labelledby={`attn-${title}`}>
      <h3 className="section-label" id={`attn-${title}`} style={{ marginTop: 0 }}>
        {title}
      </h3>
      <ul className="approval-list">{children}</ul>
    </section>
  );
}

function DemandChangeModal({ record, onClose, onSubmit, busy, useApi, liveAgents }) {
  const flagged = (record.demand_result?.rows || []).filter((r) => r.status !== "ok");
  const starters = flagged.length
    ? flagged
    : (record.demand_result?.rows || []).slice(0, 3);
  const [rows, setRows] = useState(() =>
    starters.map((r) => ({
      unit: r.unit,
      date: r.date,
      shift: r.shift,
      nurses_needed: r.nurses_needed ?? 4,
      was: r.nurses_needed,
      status: r.status,
      note: r.note,
    }))
  );

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, busy]);

  return (
    <div className="modal-backdrop" onClick={busy ? undefined : onClose} role="presentation">
      <div
        className="modal-card approval-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="demand-change-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h3 id="demand-change-title">Change demand</h3>
          <button
            type="button"
            className="icon-btn"
            onClick={onClose}
            aria-label="Close"
            disabled={busy}
          >
            <XCircle size={18} />
          </button>
        </div>
        <div className="modal-body stack">
          <p className="muted small">
            {useApi
              ? "Sets nurses needed, retires this case, and starts a child run on the local API. Not secure — this computer only, no login."
              : "Sample mode: submit jumps to the sample child case when one exists (API is offline)."}
          </p>
          {useApi && !liveAgents && (
            <p className="approval-error" role="note">
              Live agents are off on the server. Change demand will be refused (503) until you start the API with
              NURSESYNC_LIVE=1 and an API key. That costs money and can take a few minutes.
            </p>
          )}
          {(record.availability_result?.rows || []).some((r) => r.status === "missing") && (
            <p className="approval-error" role="note">
              Availability rows are also missing on this case. Changing demand alone will not fill those;
              the new case may stop again until a new run supplies availability.
            </p>
          )}
          {rows.map((r, i) => (
            <label key={`${r.date}-${r.shift}`}>
              {r.date} {r.shift}
              {r.status && r.status !== "ok" ? ` (${r.status})` : ""}
              <input
                type="number"
                min={0}
                disabled={busy}
                value={r.nurses_needed}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  setRows((prev) =>
                    prev.map((row, j) => (j === i ? { ...row, nurses_needed: v } : row))
                  );
                }}
              />
              {r.note ? <span className="muted small">{r.note}</span> : null}
            </label>
          ))}
          <div className="ticket-actions">
            <button
              type="button"
              className="primary-btn"
              disabled={busy}
              onClick={() =>
                onSubmit(
                  rows.map(({ unit, date, shift, nurses_needed }) => ({
                    unit,
                    date,
                    shift,
                    nurses_needed,
                  }))
                )
              }
            >
              {busy ? "Working…" : "Submit change"}
            </button>
            <button type="button" className="ghost-btn" disabled={busy} onClick={onClose}>
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ApprovalView({ showToast }) {
  const [source, setSource] = useState("api"); // "api" | "samples"
  const [liveAgents, setLiveAgents] = useState(false);
  const [apiNote, setApiNote] = useState("");
  const [caseList, setCaseList] = useState([]);
  const [caseId, setCaseId] = useState("");
  const [sampleKey, setSampleKey] = useState("passed");
  const [record, setRecord] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [ackOpenIssues, setAckOpenIssues] = useState(false);
  const [actionError, setActionError] = useState("");
  const [demandOpen, setDemandOpen] = useState(false);
  const [runUnit, setRunUnit] = useState(DEFAULT_RUN_UNIT);
  const [runWeekStart, setRunWeekStart] = useState(DEFAULT_RUN_WEEK);
  const [usage, setUsage] = useState(null);
  const [runStatus, setRunStatus] = useState(null);
  const [runError, setRunError] = useState("");
  const [names, setNames] = useState({});
  const [callOutOpen, setCallOutOpen] = useState(false);
  const [callOutPick, setCallOutPick] = useState("");
  const runPollRef = useRef(null);

  const resetDecisionUi = () => {
    setAckOpenIssues(false);
    setActionError("");
    setDemandOpen(false);
    setCallOutOpen(false);
  };

  const refreshUsage = useCallback(async () => {
    try {
      setUsage(await getUsage());
    } catch {
      setUsage(null);
    }
  }, []);

  /** Name with id, for sentences. Falls back to the id when the roster is not loaded. */
  const who = (id) => (names[id] ? `${names[id]} (${id})` : id);

  const loadNames = async () => {
    try {
      const data = await getRoster();
      setNames(Object.fromEntries((data.nurses || []).map((n) => [n.nurse_id, n.name])));
    } catch {
      setNames({}); // the view still works with ids
    }
  };

  const stopRunPoll = useCallback(() => {
    if (runPollRef.current) {
      clearInterval(runPollRef.current);
      runPollRef.current = null;
    }
  }, []);

  const loadApiCase = useCallback(async (id) => {
    setLoading(true);
    setLoadError("");
    resetDecisionUi();
    setCaseId(id);
    try {
      const next = await getCase(id);
      setRecord(next);
    } catch (err) {
      setLoadError(err.message || "Could not load case");
      setRecord(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshCaseList = useCallback(async (preferId) => {
    const data = await listCases();
    const cases = data.cases || [];
    setCaseList(cases);
    const pick =
      (preferId && cases.find((c) => c.case_id === preferId)?.case_id) ||
      cases[0]?.case_id ||
      "";
    if (pick) await loadApiCase(pick);
    else {
      setCaseId("");
      setRecord(null);
      setLoadError("No cases in the store. Start the API with --seed-samples.");
      setLoading(false);
    }
  }, [loadApiCase]);

  const loadSample = async (key) => {
    setLoading(true);
    setLoadError("");
    resetDecisionUi();
    setSampleKey(key);
    try {
      const next = await loadSampleCase(key);
      setRecord(next);
    } catch (err) {
      setLoadError(err.message || "Could not load sample case");
      setRecord(null);
    } finally {
      setLoading(false);
    }
  };

  const boot = async () => {
    stopRunPoll();
    setRunStatus(null);
    setLoading(true);
    setLoadError("");
    setRunError("");
    setBusy(false);
    const health = await checkHealth();
    if (!health.ok) {
      setSource("samples");
      setUsage(null);
      setApiNote(
        `Local API not reachable (${health.error}). Start: cd backend && ../.venv/bin/python -m app.serve --seed-samples`
      );
      await loadSample("passed");
      return;
    }
    setSource("api");
    setLiveAgents(health.live_agents);
    setApiNote(
      health.live_agents
        ? "Connected to local case API. Live agents ON — weekly runs and change demand cost money."
        : "Connected to local case API. Live agents off — approve/reject work; weekly run and change demand need NURSESYNC_LIVE=1."
    );
    await refreshUsage();
    try {
      await refreshCaseList();
    } catch (err) {
      setSource("samples");
      setApiNote(`API health ok but listing cases failed: ${err.message}`);
      await loadSample("passed");
    }
  };

  useEffect(() => {
    loadNames();
  }, []);

  useEffect(() => {
    boot();
    return () => stopRunPoll();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- connect once on mount
  }, []);

  const onRunFinished = useCallback(
    async (status) => {
      stopRunPoll();
      setRunStatus(status);
      setBusy(false);
      await refreshUsage();
      if (status.state === "done" && status.case_id) {
        try {
          await refreshCaseList(status.case_id);
          showToast?.(status.message || `Weekly run finished (${status.outcome || "done"})`);
        } catch (err) {
          setRunError(err.message || "Run finished but could not load the case");
        }
      } else if (status.state === "failed") {
        setRunError(status.message || "Weekly run failed");
        showToast?.(status.message || "Weekly run failed");
        try {
          await refreshCaseList();
        } catch {
          /* list refresh is best-effort after failure */
        }
      }
    },
    [refreshCaseList, refreshUsage, showToast, stopRunPoll]
  );

  const startRunPoll = useCallback(
    (runId) => {
      stopRunPoll();
      runPollRef.current = setInterval(async () => {
        try {
          const status = await getRun(runId);
          setRunStatus(status);
          if (status.state === "done" || status.state === "failed") {
            await onRunFinished(status);
          }
        } catch (err) {
          stopRunPoll();
          setBusy(false);
          setRunError(err.message || "Lost contact while polling the run");
        }
      }, RUN_POLL_MS);
    },
    [onRunFinished, stopRunPoll]
  );

  const onStartWeeklyRun = async () => {
    setRunError("");
    setActionError("");
    if (source !== "api") {
      setRunError("Start the local API to run a week. Sample mode cannot start paid runs.");
      return;
    }
    const unit = runUnit.trim();
    const week = runWeekStart.trim();
    if (!unit || !week) {
      setRunError("Unit and week start (Monday) are required.");
      return;
    }
    const remaining =
      usage?.capped && usage.remaining != null ? ` ${usage.remaining} paid operation(s) left today.` : "";
    const confirmed = window.confirm(
      `Start a weekly run for unit ${unit}, week of ${week}? This calls live agents, costs about $0.50–$1.50, and can take a few minutes.${remaining}`
    );
    if (!confirmed) return;
    setBusy(true);
    setRunStatus(null);
    try {
      const status = await startWeeklyRun(unit, week);
      setRunStatus(status);
      showToast?.(`Weekly run started (${status.case_id}). This costs money and can take a few minutes.`);
      await refreshUsage();
      try {
        await refreshCaseList(status.case_id);
      } catch {
        /* case may still be building; poll will open it when done */
      }
      if (status.state === "running") startRunPoll(status.run_id);
      else await onRunFinished(status);
    } catch (err) {
      setBusy(false);
      setRunError(err.message || "Could not start weekly run");
      await refreshUsage();
      if (err instanceof CaseApiError && err.status === 503) {
        showToast?.("Live agents are off — restart API with NURSESYNC_LIVE=1 to start a weekly run");
      } else if (err instanceof CaseApiError && err.status === 429) {
        showToast?.("Daily paid-operation limit reached");
      }
    }
  };

  const runInProgress = runStatus?.state === "running";
  const startRunDisabled =
    busy || runInProgress || source !== "api" || !runUnit.trim() || !runWeekStart.trim();

  const openIssues = record ? hasOpenIssues(record) : false;
  const draft = record?.final_draft;
  const demandFlags = (record?.demand_result?.rows || []).filter((r) => r.status !== "ok");
  const availFlags = (record?.availability_result?.rows || []).filter((r) => r.status !== "ok");
  const nmr = record?.needs_manual_review || [];
  const unusual = (record?.unusual || []).filter((n) => typeof n === "string" && n.trim());
  const gaps = draft?.open_gaps || [];
  const soft = record?.soft_tradeoffs || [];
  const hard = record?.open_violations || [];
  const unfixable = record?.unfixable || [];

  const weekDates = useMemo(() => {
    if (!record?.week_start) return [];
    return Array.from({ length: 7 }, (_, i) => addDays(record.week_start, i));
  }, [record?.week_start]);

  const nursesByCell = useMemo(() => {
    const map = {};
    for (const a of draft?.assignments || []) {
      const key = `${a.date}|${a.shift}`;
      if (!map[key]) map[key] = [];
      map[key].push(a.nurse_id);
    }
    return map;
  }, [draft]);

  const goToNewer = async () => {
    const newer = record?.newer_case_id;
    if (!newer) return;
    if (source === "api") {
      try {
        await refreshCaseList(newer);
      } catch (err) {
        setActionError(err.message);
      }
      return;
    }
    const key = await sampleKeyForCaseId(newer);
    if (key) loadSample(key);
    else showToast?.(`No sample file for ${newer}`);
  };

  const onApprove = async () => {
    setActionError("");
    if (source === "samples") {
      const result = approveLocal(record, ackOpenIssues);
      if (!result.ok) {
        setActionError(result.message);
        return;
      }
      setRecord(result.record);
      showToast?.("Draft approved (sample mode — not saved to API)");
      return;
    }
    setBusy(true);
    try {
      const next = await approveCase(record.case_id, ackOpenIssues);
      setRecord(next);
      await refreshCaseList(next.case_id);
      showToast?.("Draft approved (local API — no login)");
    } catch (err) {
      setActionError(err.message || "Approve failed");
    } finally {
      setBusy(false);
    }
  };

  const onReject = async () => {
    setActionError("");
    if (source === "samples") {
      const result = rejectLocal(record);
      if (!result.ok) {
        setActionError(result.message);
        return;
      }
      setRecord(result.record);
      showToast?.("Draft rejected (sample mode — not saved to API)");
      return;
    }
    setBusy(true);
    try {
      const next = await rejectCase(record.case_id);
      setRecord(next);
      await refreshCaseList(next.case_id);
      showToast?.("Draft rejected (local API — no login)");
    } catch (err) {
      setActionError(err.message || "Reject failed");
    } finally {
      setBusy(false);
    }
  };

  const onDemandSubmit = async (changes) => {
    setActionError("");
    if (source === "samples") {
      setDemandOpen(false);
      if (
        sampleKey === "demand_change_old" ||
        sampleKey === "stopped_missing_input" ||
        sampleKey === "demand_change_child"
      ) {
        await loadSample("demand_change_child");
        showToast?.("Sample mode: opened child case");
        return;
      }
      const childId = await demandChangeChildCaseId();
      setRecord((prev) => ({
        ...prev,
        status: "out_of_date",
        newer_case_id: childId,
        decision_time: new Date().toISOString().slice(0, 19),
        decision_details: {
          action: "change_demand",
          demand_changes: changes,
          acknowledged_open_issues: false,
          new_case_id: childId,
        },
      }));
      showToast?.("Sample mode: marked out of date");
      return;
    }

    setBusy(true);
    try {
      const { child } = await changeDemand(record.case_id, changes);
      setDemandOpen(false);
      setRecord(child);
      setAckOpenIssues(false);
      await refreshCaseList(child.case_id);
      showToast?.(`Opened child case ${child.case_id}`);
    } catch (err) {
      setActionError(err.message || "Change demand failed");
      if (err instanceof CaseApiError && err.status === 503) {
        showToast?.("Live agents are off — restart API with NURSESYNC_LIVE=1 to change demand");
      }
    } finally {
      setBusy(false);
    }
  };

  const onCallOutSubmit = async () => {
    setActionError("");
    const [nurseId, date, shift] = callOutPick.split("|");
    if (!nurseId) {
      setActionError("Pick the nurse and shift that were called out.");
      return;
    }
    const left =
      usage?.capped && usage.remaining != null ? ` ${usage.remaining} paid operation(s) left today.` : "";
    const ok = window.confirm(
      `Report a call-out for ${who(nurseId)} on ${date} ${shift}? This reruns the live Scheduler, costs about $0.15–$1.20, and takes a few minutes. This case becomes out of date.${left}`
    );
    if (!ok) return;
    setBusy(true);
    try {
      const { child } = await reportCallOut(record.case_id, [{ nurse_id: nurseId, date, shift }]);
      setCallOutOpen(false);
      setCallOutPick("");
      setRecord(child);
      setAckOpenIssues(false);
      await refreshCaseList(child.case_id);
      await refreshUsage();
      showToast?.(`Opened new case ${child.case_id} after the call-out`);
    } catch (err) {
      setActionError(err.message || "Call-out failed");
      await refreshUsage();
    } finally {
      setBusy(false);
    }
  };

  const approveDisabled =
    busy || !record || !canTryApprove(record) || (openIssues && !ackOpenIssues);
  const rejectDisabled = busy || !record || !canReject(record);
  const demandDisabled = busy || !record || !canChangeDemand(record);
  const noRunsLeft = Boolean(usage?.capped && usage.remaining === 0);
  const callOutDisabled =
    busy || source !== "api" || !liveAgents || noRunsLeft || !record || !draft || !canChangeDemand(record);

  return (
    <div className="panel approval-panel">
      <div className="panel-head" style={{ flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2>Approve AI draft</h2>
          <p className="muted">
            Review a case, then approve, change demand, or reject. Local only — no login; not secure.
          </p>
        </div>
        <div className="approval-source-controls">
          {source === "api" ? (
            <label className="approval-sample">
              Case
              <select
                value={caseId}
                onChange={(e) => loadApiCase(e.target.value)}
                aria-label="Case"
                disabled={loading || busy || !caseList.length}
              >
                {caseList.map((c) => (
                  <option key={c.case_id} value={c.case_id}>
                    {formatCaseOption(c)}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <label className="approval-sample">
              Sample case
              <select
                value={sampleKey}
                onChange={(e) => loadSample(e.target.value)}
                aria-label="Sample case"
                disabled={loading || busy}
              >
                {SAMPLE_CATALOG.map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="ticket-actions">
            <button type="button" className="ghost-btn small" disabled={busy} onClick={() => boot()}>
              Reconnect API
            </button>
            {source === "api" ? (
              <button
                type="button"
                className="ghost-btn small"
                disabled={busy}
                onClick={async () => {
                  stopRunPoll();
                  setRunStatus(null);
                  setBusy(false);
                  setSource("samples");
                  setUsage(null);
                  setApiNote("Switched to bundled samples.");
                  await loadSample(sampleKey || "passed");
                }}
              >
                Use samples
              </button>
            ) : null}
          </div>
        </div>
      </div>

      {apiNote && (
        <div className={`approval-banner ${source === "api" ? "soft" : ""}`} role="status">
          {apiNote}
        </div>
      )}

      <section className="card approval-run" aria-labelledby="weekly-run-title">
        <h3 className="section-label" id="weekly-run-title" style={{ marginTop: 0 }}>
          Start weekly run
        </h3>
        <p className="muted small">
          Posts to the local API, then polls until the draft is ready. Mock data only: unit {DEFAULT_RUN_UNIT},
          week of {DEFAULT_RUN_WEEK}. Costs about $0.50–$1.50 and needs NURSESYNC_LIVE=1. One run at a time;
          daily paid-ops cap applies. Not secure — this computer only.
        </p>
        <div className="approval-run-row">
          <label className="approval-sample">
            Unit
            <input
              type="text"
              value={runUnit}
              onChange={(e) => setRunUnit(e.target.value)}
              disabled={runInProgress}
              aria-label="Unit for weekly run"
              autoComplete="off"
            />
          </label>
          <label className="approval-sample">
            Week start (Monday)
            <input
              type="date"
              value={runWeekStart}
              onChange={(e) => setRunWeekStart(e.target.value)}
              disabled={runInProgress}
              aria-label="Week start Monday for weekly run"
            />
          </label>
          <button
            type="button"
            className="primary-btn"
            disabled={startRunDisabled}
            onClick={onStartWeeklyRun}
            title={
              source !== "api"
                ? "Connect to the local API first"
                : !liveAgents
                  ? "Server needs NURSESYNC_LIVE=1"
                  : runInProgress
                    ? "A run is already in progress"
                    : "Start weekly run"
            }
          >
            {runInProgress ? "Running…" : "Start weekly run"}
          </button>
        </div>
        {usage && (
          <p className="muted small" role="status">
            {usage.capped
              ? `Paid operations today: ${usage.used_today} used, ${usage.remaining} left (cap ${usage.max_per_day}${
                  usage.date ? ` · ${usage.date}` : ""
                }).`
              : "No daily paid-ops cap on this server."}
          </p>
        )}
        {source === "api" && !liveAgents && (
          <p className="approval-error" role="note">
            Live agents are off. Starting a run will be refused (503) until the API is started with
            NURSESYNC_LIVE=1 and an API key.
          </p>
        )}
        {runStatus && (
          <p className="muted small" role="status">
            Run <code>{runStatus.run_id}</code>: {runStatus.state}
            {runStatus.outcome ? ` · ${runStatus.outcome.replace(/_/g, " ")}` : ""}
            {runStatus.message ? ` — ${runStatus.message}` : ""}
          </p>
        )}
        {runError && (
          <p className="approval-error" role="alert">
            {runError}
          </p>
        )}
      </section>

      {loading && <p className="loader">Loading…</p>}
      {loadError && (
        <p className="approval-error" role="alert">
          {loadError}
        </p>
      )}
      {!loading && record && (
        <>
          <div className="card approval-meta">
            <div className="approval-meta-row">
              <StatusStamp status={record.status} outcome={record.outcome} />
              <span className="muted small">
                {record.unit} · week of {fmtDay(record.week_start)} · {record.trigger}
                {record.rounds_used ? ` · ${record.rounds_used} round(s)` : ""}
              </span>
            </div>
            <dl className="approval-dl">
              <div>
                <dt>Case</dt>
                <dd>
                  <code>{record.case_id}</code>
                </dd>
              </div>
              <div>
                <dt>Snapshot</dt>
                <dd>
                  <code>{record.snapshot_id}</code>
                </dd>
              </div>
              <div>
                <dt>Started</dt>
                <dd>{record.start_time}</dd>
              </div>
              {draft ? (
                <div>
                  <dt>Draft version</dt>
                  <dd>{draft.version}</dd>
                </div>
              ) : null}
              {record.parent_case_id ? (
                <div>
                  <dt>Parent</dt>
                  <dd>
                    <code>{record.parent_case_id}</code>
                  </dd>
                </div>
              ) : null}
            </dl>
            {record.status === "out_of_date" && (
              <div className="approval-banner" role="status">
                This case is out of date
                {record.newer_case_id ? (
                  <>
                    {" "}
                    — newer case <code>{record.newer_case_id}</code>.{" "}
                    <button type="button" className="ghost-btn small" onClick={goToNewer}>
                      Open newer case
                    </button>
                  </>
                ) : (
                  "."
                )}{" "}
                Approve is disabled.
              </div>
            )}
            {record.outcome === "stopped_missing_input" && (
              <div className="approval-banner" role="status">
                {record.stop_reason || "Stopped for missing required input. No draft to approve."}
              </div>
            )}
            {record.trigger === "call_out" && (record.callouts || []).length > 0 && (
              <div className="approval-banner soft" role="status">
                Call-out:{" "}
                {(record.callouts || [])
                  .map((c) => `${who(c.nurse_id)} on ${c.date} ${c.shift}`)
                  .join("; ")}
              </div>
            )}
            {record.manager_decision && (
              <p className="muted small">
                Decision: {record.manager_decision}
                {record.decision_time ? ` at ${record.decision_time}` : ""}
                {record.decision_details?.acknowledged_open_issues
                  ? " (open issues acknowledged)"
                  : ""}
              </p>
            )}
          </div>

          <h3 className="section-label">Attention</h3>
          <AttentionList title="Agent notes" empty={!unusual.length}>
            {unusual.map((note, i) => (
              <li key={`unusual-${i}`}>{note}</li>
            ))}
          </AttentionList>
          {unusual.length > 0 && (
            <p className="muted small">
              Agent notes are advisory plain text only. They do not decide pass or fail.
            </p>
          )}
          <AttentionList title="Demand flags" empty={!demandFlags.length}>
            {demandFlags.map((r) => (
              <li key={`d-${r.date}-${r.shift}`}>
                <strong>
                  {r.status} — {r.date} {r.shift}
                </strong>
                : nurses_needed {r.nurses_needed ?? "—"}
                {r.note ? `. ${r.note}` : ""}
              </li>
            ))}
          </AttentionList>
          <AttentionList title="Availability flags" empty={!availFlags.length}>
            {availFlags.map((r) => (
              <li key={`a-${r.nurse_id}-${r.date}-${r.shift}`}>
                <strong>
                  {r.status} — {who(r.nurse_id)} {r.date} {r.shift}
                </strong>
                : available {String(r.available)}
                {r.reason && r.reason !== "none" ? ` (${r.reason})` : ""}
                {r.note ? `. ${r.note}` : ""}
              </li>
            ))}
          </AttentionList>
          <AttentionList title="Needs manual review" empty={!nmr.length}>
            {nmr.map((r, i) => (
              <li key={`nmr-${r.item_type}-${r.id}-${i}`}>
                <strong>
                  {r.item_type} {r.id}
                </strong>
                {r.note ? `: ${r.note}` : ""}
              </li>
            ))}
          </AttentionList>
          <AttentionList title="Open gaps" empty={!gaps.length}>
            {gaps.map((g) => (
              <li key={`g-${g.date}-${g.shift}`}>
                <strong>
                  {g.date} {g.shift}
                </strong>
                : {g.nurses_assigned}/{g.nurses_needed} — {g.gap_reason}
              </li>
            ))}
          </AttentionList>
          <AttentionList title="Unresolved hard issues" empty={!hard.length && !unfixable.length}>
            {hard.map((v, i) => (
              <li key={`h-${v.rule}-${v.date}-${v.shift}-${i}`}>
                <strong>Hard — {v.rule}</strong>
                {v.nurse_id ? ` (${who(v.nurse_id)})` : ""} — {v.date} {v.shift}
                {v.found || v.limit ? `: found ${v.found}, limit ${v.limit}` : ""}
              </li>
            ))}
            {unfixable.map((u, i) => (
              <li key={`u-${u.rule}-${u.date}-${u.shift}-${i}`}>
                <strong>Unfixable — {u.rule}</strong>
                {u.nurse_id ? ` (${who(u.nurse_id)})` : ""} — {u.date} {u.shift}: {u.reason}
              </li>
            ))}
          </AttentionList>
          <AttentionList title="Soft tradeoffs" empty={!soft.length}>
            {soft.map((s, i) => (
              <li key={`s-${i}`}>
                Soft — {s.rule || "fairness"}
                {s.note ? `: ${s.note}` : ""}
              </li>
            ))}
          </AttentionList>
          {!unusual.length &&
            !demandFlags.length &&
            !availFlags.length &&
            !nmr.length &&
            !gaps.length &&
            !hard.length &&
            !unfixable.length &&
            !soft.length && <p className="muted small">Nothing flagged above the schedule.</p>}

          <h3 className="section-label">Schedule</h3>
          {!draft ? (
            <p className="muted">No draft on this case.</p>
          ) : (
            <div className="card approval-grid-wrap" tabIndex={0} aria-label="Week schedule grid">
              <table className="approval-grid">
                <thead>
                  <tr>
                    <th scope="col">Shift</th>
                    {weekDates.map((d) => (
                      <th key={d} scope="col">
                        {fmtDay(d)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {["day", "night"].map((shift) => (
                    <tr key={shift}>
                      <th scope="row">{SHIFT_LABEL[shift]}</th>
                      {weekDates.map((d) => {
                        const nurses = nursesByCell[`${d}|${shift}`] || [];
                        const gap = gaps.find((g) => g.date === d && g.shift === shift);
                        return (
                          <td key={`${d}|${shift}`}>
                            {nurses.length ? (
                              <span className="approval-nurses">
                                {nurses.map((id) => names[id] || id).join(", ")}
                              </span>
                            ) : (
                              <span className="muted">—</span>
                            )}
                            {gap ? (
                              <div className="approval-gap-tag">
                                Gap {gap.nurses_assigned}/{gap.nurses_needed}
                              </div>
                            ) : null}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h3 className="section-label">Notes</h3>
          {(draft?.notes || []).length === 0 ? (
            <p className="muted small">No scheduler notes.</p>
          ) : (
            <ul className="approval-list">
              {draft.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          )}

          <h3 className="section-label">Actions</h3>
          <div className="card form-card">
            {openIssues && canTryApprove(record) && (
              <label className="approval-ack">
                <input
                  type="checkbox"
                  checked={ackOpenIssues}
                  disabled={busy}
                  onChange={(e) => setAckOpenIssues(e.target.checked)}
                />
                I accept the open issues on this draft
              </label>
            )}
            {actionError && (
              <p className="approval-error" role="alert">
                {actionError}
              </p>
            )}
            <div className="ticket-actions">
              <button
                type="button"
                className="primary-btn"
                disabled={approveDisabled}
                onClick={onApprove}
                title={
                  record.status === "out_of_date"
                    ? "Out of date — open the newer case"
                    : !draft
                      ? "No draft to approve"
                      : openIssues && !ackOpenIssues
                        ? "Acknowledge open issues first"
                        : "Approve draft"
                }
              >
                <CheckCircle size={14} /> Approve
              </button>
              <button
                type="button"
                className="ghost-btn"
                disabled={demandDisabled}
                onClick={() => setDemandOpen(true)}
              >
                Change demand
              </button>
              <button
                type="button"
                className="ghost-btn"
                disabled={callOutDisabled}
                aria-expanded={callOutOpen}
                onClick={() => setCallOutOpen((v) => !v)}
                title={
                  source !== "api" || !liveAgents
                    ? "Needs the API with live agents (NURSESYNC_LIVE=1)"
                    : noRunsLeft
                      ? "No paid runs left today"
                      : "Report a nurse call-out"
                }
              >
                Report call-out
              </button>
              <button type="button" className="ghost-btn" disabled={rejectDisabled} onClick={onReject}>
                <XCircle size={14} /> Reject
              </button>
            </div>
            {callOutOpen && !callOutDisabled && (
              <div
                className="approval-banner soft"
                role="group"
                aria-label="Report a call-out"
                onKeyDown={(e) => e.key === "Escape" && !busy && setCallOutOpen(false)}
              >
                <label className="approval-sample">
                  Who called out, and for which shift
                  <select value={callOutPick} onChange={(e) => setCallOutPick(e.target.value)} disabled={busy}>
                    <option value="">Pick a nurse and shift…</option>
                    {[...(draft.assignments || [])]
                      .sort((a, b) => `${a.date}${a.shift}`.localeCompare(`${b.date}${b.shift}`))
                      .map((a) => (
                        <option key={`${a.nurse_id}|${a.date}|${a.shift}`} value={`${a.nurse_id}|${a.date}|${a.shift}`}>
                          {names[a.nurse_id] || a.nurse_id} — {fmtDay(a.date)} {a.shift}
                        </option>
                      ))}
                  </select>
                </label>
                <button type="button" className="primary-btn" disabled={busy || !callOutPick} onClick={onCallOutSubmit}>
                  Send call-out
                </button>
                <button type="button" className="ghost-btn" disabled={busy} onClick={() => setCallOutOpen(false)}>
                  Cancel
                </button>
                <p className="muted small">
                  Reruns the live Scheduler (about $0.15–$1.20). The rest of the week stays locked. This case becomes
                  out of date.
                </p>
              </div>
            )}
            <p className="muted small">
              Decisions save to the local case store when the API is connected. Posting to nurses is out of
              scope for v1.
            </p>
          </div>

          {demandOpen && (
            <DemandChangeModal
              record={record}
              onClose={() => !busy && setDemandOpen(false)}
              onSubmit={onDemandSubmit}
              busy={busy}
              useApi={source === "api"}
              liveAgents={liveAgents}
            />
          )}
        </>
      )}
    </div>
  );
}
