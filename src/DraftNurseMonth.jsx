import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, XCircle } from "lucide-react";

const DOW = ["S", "M", "T", "W", "T", "F", "S"];
const pad = (n) => String(n).padStart(2, "0");
const iso = (y, m, d) => `${y}-${pad(m + 1)}-${pad(d)}`;
const SHIFT_LABEL = { day: "Day", night: "Night" };

/**
 * Month overview for one nurse on an AI draft. Read-only.
 * Uses the case's assignments and availability rows (mock roster ids like N001), not the browser schedule board.
 */
export default function DraftNurseMonth({ nurseId, name, assignments, availabilityRows, weekStart, onClose }) {
  const closeRef = useRef(null);
  const start = (weekStart || new Date().toISOString().slice(0, 10)).split("-").map(Number);
  const [ym, setYm] = useState({ y: start[0], m: start[1] - 1 });

  useEffect(() => {
    const opener = document.activeElement;
    closeRef.current?.focus();
    return () => opener?.focus?.();
  }, []);
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const { y, m } = ym;
  const first = new Date(y, m, 1).getDay();
  const days = new Date(y, m + 1, 0).getDate();
  const monthLabel = new Date(y, m, 1).toLocaleDateString("en-US", { month: "long", year: "numeric" });
  const mine = (assignments || []).filter((a) => a.nurse_id === nurseId);
  const monthKey = `${y}-${pad(m + 1)}`;
  const monthShifts = mine.filter((a) => a.date.startsWith(monthKey));
  const offByDate = {};
  for (const r of availabilityRows || []) {
    if (r.nurse_id !== nurseId || r.available !== false) continue;
    if (!offByDate[r.date]) offByDate[r.date] = r.reason || "unavailable";
  }
  const step = (delta) => setYm(({ y: yy, m: mm }) => {
    const d = new Date(yy, mm + delta, 1);
    return { y: d.getFullYear(), m: d.getMonth() };
  });

  const cells = [];
  for (let i = 0; i < first; i++) cells.push(<div key={`e${i}`} className="nm-cell empty" aria-hidden="true" />);
  for (let d = 1; d <= days; d++) {
    const date = iso(y, m, d);
    const todays = mine.filter((a) => a.date === date);
    const offReason = offByDate[date];
    const timeOff = offReason === "approved_time_off";
    const callOut = offReason === "call_out";
    const parts = [
      ...todays.map((a) => `${SHIFT_LABEL[a.shift] || a.shift} ${a.shift_start}–${a.shift_end}`),
      ...(timeOff ? ["Approved time off"] : []),
      ...(callOut ? ["Call-out"] : []),
      ...(offReason && !timeOff && !callOut ? ["Unavailable"] : []),
    ];
    const clash = todays.length > 1 || (todays.length > 0 && offReason);
    const label = new Date(y, m, d).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
    cells.push(
      <div
        key={date}
        className={`nm-cell ${todays.length ? "work" : ""} ${clash ? "clash" : ""}`}
        role="group"
        aria-label={`${label}: ${parts.length ? parts.join("; ") : "nothing scheduled"}${clash ? ". Conflict." : ""}`}
      >
        <span className="nm-day">{d}</span>
        {todays.map((a) => (
          <span key={`${a.date}-${a.shift}`} className="nm-tag">{SHIFT_LABEL[a.shift] || a.shift}</span>
        ))}
        {timeOff && <span className="nm-tag off">Time off</span>}
        {callOut && <span className="nm-tag off">Call-out</span>}
        {offReason && !timeOff && !callOut && <span className="nm-tag off">Unavail.</span>}
        {clash && <span className="nm-tag bad">Conflict</span>}
      </div>
    );
  }

  const displayName = name || nurseId;

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal-card nurse-month"
        role="dialog"
        aria-modal="true"
        aria-label={`${displayName}, month on this AI draft`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <div>
            <h3>{displayName}</h3>
            <p className="muted small day-detail-sub">
              {monthShifts.length === 1 ? "1 shift" : `${monthShifts.length} shifts`} on this draft in {monthLabel}
              {nurseId ? ` · ${nurseId}` : ""}
            </p>
          </div>
          <button type="button" className="icon-btn" ref={closeRef} onClick={onClose} aria-label="Close">
            <XCircle size={18} />
          </button>
        </div>
        <div className="modal-body">
          <p className="muted small">
            From the AI draft only. Days outside this week may be empty until another run covers them.
          </p>
          <div className="cal-head">
            <button type="button" className="icon-btn" onClick={() => step(-1)} aria-label="Previous month">
              <ChevronLeft size={18} />
            </button>
            <strong aria-live="polite">{monthLabel}</strong>
            <button type="button" className="icon-btn" onClick={() => step(1)} aria-label="Next month">
              <ChevronRight size={18} />
            </button>
          </div>
          <div className="nm-grid nm-dow" aria-hidden="true">
            {DOW.map((d, i) => (
              <div key={i} className="cal-dow-cell">
                {d}
              </div>
            ))}
          </div>
          <div className="nm-grid">{cells}</div>
          <div className="ticket-actions">
            <button type="button" className="ghost-btn" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
