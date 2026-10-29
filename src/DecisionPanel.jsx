/**
 * "How the agents decided": a recommendation up top, then one step per agent with what it did and why.
 * Read-only. Everything shown is already saved on the case record; nothing here decides pass or fail (code does).
 */
const plural = (n, one, many) => `${n} ${n === 1 ? one : many || `${one}s`}`;

export default function DecisionPanel({ record, names }) {
  if (!record) return null;
  const draft = record.final_draft;
  const demandRows = record.demand_result?.rows || [];
  const availRows = record.availability_result?.rows || [];
  const rounds = record.rounds || [];
  const hard = record.open_violations || [];
  const unfixable = record.unfixable || [];
  const gaps = draft?.open_gaps || [];
  const review = record.needs_manual_review || [];
  const flagged = [...demandRows, ...availRows].filter((r) => r.status !== "ok");
  const withNames = (text) => String(text).replace(/\bN\d{3}\b/g, (id) => (names[id] ? `${names[id]} (${id})` : id));

  const todo = [];
  if (hard.length) todo.push(`${plural(hard.length, "rule problem")} the agents could not fix`);
  if (unfixable.length) todo.push(`${plural(unfixable.length, "problem")} marked unfixable`);
  if (gaps.length) todo.push(`${plural(gaps.length, "shift")} left short-staffed`);
  if (review.length) todo.push(`${plural(review.length, "item")} flagged for a human look`);
  if (flagged.length) todo.push(`${plural(flagged.length, "input row")} with a warning`);

  const canJudge = Boolean(draft) && record.status === "waiting_approval";
  const ready = canJudge && record.outcome === "passed" && todo.length === 0;

  const canWork = availRows.filter((r) => r.available === true).length;
  const cannotWork = availRows.filter((r) => r.available === false);
  const timeOff = cannotWork.filter((r) => r.reason === "approved_time_off").length;
  const callOuts = cannotWork.filter((r) => r.reason === "call_out").length;
  const nurses = new Set((draft?.assignments || []).map((a) => a.nurse_id)).size;
  const shiftsNeeded = demandRows.filter((r) => r.nurses_needed != null).length;

  return (
    <section aria-labelledby="decision-title" className="decision">
      <h3 className="section-label" id="decision-title">How the agents decided</h3>

      {canJudge && (
        <div className={`approval-banner ${ready ? "soft" : ""}`} role="status">
          {ready ? (
            <>
              <strong>Ready for your review.</strong> Every shift is covered and the rules check found no problems.
              It is still your decision.
            </>
          ) : (
            <>
              <strong>Look at these first:</strong> {todo.join("; ")}. Details are listed below.
            </>
          )}
        </div>
      )}

      <ol className="decision-steps">
        <li>
          <strong>Demand agent</strong>: worked out how many nurses each shift needs.
          <div className="muted small">
            {shiftsNeeded ? `${plural(shiftsNeeded, "shift")} sized` : "No shifts sized"}
            {demandRows.some((r) => r.status !== "ok") ? `, ${demandRows.filter((r) => r.status !== "ok").length} with a warning` : ", none flagged"}.
          </div>
        </li>
        <li>
          <strong>Availability agent</strong>: worked out who can work each shift.
          <div className="muted small">
            {canWork} can work, {cannotWork.length} cannot
            {cannotWork.length ? ` (${timeOff} approved time off, ${callOuts} call-outs)` : ""}.
          </div>
        </li>
        {draft ? (
          <li>
            <strong>Scheduler</strong>: built version {draft.version} with {plural(draft.assignments.length, "assignment")}{" "}
            across {plural(nurses, "nurse")}.
            {(draft.notes || []).length > 0 && (
              <>
                <div className="muted small">Its reasoning, in its own words:</div>
                <ul className="approval-list">
                  {draft.notes.map((n, i) => <li key={i}>{withNames(n)}</li>)}
                </ul>
              </>
            )}
          </li>
        ) : (
          <li>
            <strong>Scheduler</strong>: did not run. {record.stop_reason || "Required input was missing."}
          </li>
        )}
        <li>
          <strong>Rules check (plain code, not AI)</strong>: decides if the draft is safe.
          <div className="muted small">
            {rounds.length
              ? rounds.map((r) => `Round ${r.version}: ${plural(r.hard_violations, "hard problem")}`).join(" → ")
              : record.rounds_used
                ? `${plural(record.rounds_used, "round")} used`
                : "No rounds recorded"}
            {record.outcome === "passed" ? ". Passed." : record.outcome === "stopped_after_3_rounds" ? ". Stopped after 3 rounds with problems left." : "."}
          </div>
        </li>
      </ol>
    </section>
  );
}
