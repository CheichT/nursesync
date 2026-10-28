import { useEffect, useMemo, useState } from "react";
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

const SHIFT_LABEL = { day: "Day 07:00–19:00", night: "Night 19:00–07:00" };

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

function DemandChangeModal({ record, onClose, onSubmit }) {
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
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal-card approval-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="demand-change-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h3 id="demand-change-title">Change demand</h3>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            <XCircle size={18} />
          </button>
        </div>
        <div className="modal-body stack">
          <p className="muted small">
            Set nurses needed for one or more shifts. With a real API this retires this case and opens a
            child run. In this demo, submit jumps to the sample child case when one exists.
          </p>
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
              Submit change
            </button>
            <button type="button" className="ghost-btn" onClick={onClose}>
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ApprovalView({ showToast }) {
  const [sampleKey, setSampleKey] = useState("passed");
  const [record, setRecord] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [ackOpenIssues, setAckOpenIssues] = useState(false);
  const [actionError, setActionError] = useState("");
  const [demandOpen, setDemandOpen] = useState(false);

  const loadSample = async (key) => {
    setLoading(true);
    setLoadError("");
    setAckOpenIssues(false);
    setActionError("");
    setDemandOpen(false);
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

  useEffect(() => {
    loadSample("passed");
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initial sample only
  }, []);

  const openIssues = record ? hasOpenIssues(record) : false;
  const draft = record?.final_draft;
  const demandFlags = (record?.demand_result?.rows || []).filter((r) => r.status !== "ok");
  const availFlags = (record?.availability_result?.rows || []).filter((r) => r.status !== "ok");
  const nmr = record?.needs_manual_review || [];
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
    const key = await sampleKeyForCaseId(record.newer_case_id);
    if (key) loadSample(key);
    else showToast?.(`No sample file for ${record.newer_case_id}`);
  };

  const onApprove = () => {
    setActionError("");
    const result = approveLocal(record, ackOpenIssues);
    if (!result.ok) {
      setActionError(result.message);
      return;
    }
    setRecord(result.record);
    showToast?.("Draft approved (local only — no API yet)");
  };

  const onReject = () => {
    setActionError("");
    const result = rejectLocal(record);
    if (!result.ok) {
      setActionError(result.message);
      return;
    }
    setRecord(result.record);
    showToast?.("Draft rejected (local only — no API yet)");
  };

  const onDemandSubmit = async (changes) => {
    setDemandOpen(false);
    // Demo path: jump to Cheich's child sample when this is the demand-change parent or the stopped case.
    if (sampleKey === "demand_change_old" || sampleKey === "stopped_missing_input" || sampleKey === "demand_change_child") {
      await loadSample("demand_change_child");
      showToast?.("Demo: opened child case after demand change (API will rerun Scheduler)");
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
    showToast?.("Demo: no API — marked out of date. Open the demand-change child sample to continue.");
  };

  const approveDisabled = !record || !canTryApprove(record) || (openIssues && !ackOpenIssues);
  const rejectDisabled = !record || !canReject(record);
  const demandDisabled = !record || !canChangeDemand(record);

  return (
    <div className="panel approval-panel">
      <div className="panel-head" style={{ flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2>Approve AI draft</h2>
          <p className="muted">
            Review a case record, then approve, change demand, or reject. Sample data only — no backend API yet.
          </p>
        </div>
        <label className="approval-sample">
          Sample case
          <select
            value={sampleKey}
            onChange={(e) => loadSample(e.target.value)}
            aria-label="Sample case"
          >
            {SAMPLE_CATALOG.map((c) => (
              <option key={c.key} value={c.key}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && <p className="loader">Loading sample…</p>}
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
                  Open newer sample
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
              .map((c) => `${c.nurse_id} on ${c.date} ${c.shift}`)
              .join("; ")}
          </div>
        )}
        {record.manager_decision && (
          <p className="muted small">
            Decision: {record.manager_decision}
            {record.decision_time ? ` at ${record.decision_time}` : ""}
            {record.decision_details?.acknowledged_open_issues ? " (open issues acknowledged)" : ""}
          </p>
        )}
      </div>

      <h3 className="section-label">Attention</h3>
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
              {r.status} — {r.nurse_id} {r.date} {r.shift}
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
            <strong>
              Hard — {v.rule}
            </strong>
            {v.nurse_id ? ` (${v.nurse_id})` : ""} — {v.date} {v.shift}
            {v.found || v.limit ? `: found ${v.found}, limit ${v.limit}` : ""}
          </li>
        ))}
        {unfixable.map((u, i) => (
          <li key={`u-${u.rule}-${u.date}-${u.shift}-${i}`}>
            <strong>Unfixable — {u.rule}</strong>
            {u.nurse_id ? ` (${u.nurse_id})` : ""} — {u.date} {u.shift}: {u.reason}
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
      {!demandFlags.length &&
        !availFlags.length &&
        !nmr.length &&
        !gaps.length &&
        !hard.length &&
        !unfixable.length &&
        !soft.length && (
          <p className="muted small">Nothing flagged above the schedule.</p>
        )}

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
                          <span className="approval-nurses">{nurses.join(", ")}</span>
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
          <button type="button" className="ghost-btn" disabled={rejectDisabled} onClick={onReject}>
            <XCircle size={14} /> Reject
          </button>
        </div>
        <p className="muted small">
          Decisions update this screen only. Posting to nurses is out of scope for v1.
        </p>
      </div>

      {demandOpen && (
        <DemandChangeModal
          record={record}
          onClose={() => setDemandOpen(false)}
          onSubmit={onDemandSubmit}
        />
      )}
        </>
      )}
    </div>
  );
}
