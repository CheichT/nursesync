import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, XCircle } from "lucide-react";

const DOW = ["S", "M", "T", "W", "T", "F", "S"];
const pad = (n) => String(n).padStart(2, "0");
const iso = (y, m, d) => `${y}-${pad(m + 1)}-${pad(d)}`;
const hoursOf = (s) => {
  const mins = (t) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
  let len = mins(s.end) - mins(s.start);
  if (len <= 0) len += 24 * 60; // overnight
  return len / 60;
};
const kindLabel = (s) => (s.start === "07:00" && s.end === "19:00" ? "Day" : s.start === "19:00" && s.end === "07:00" ? "Night" : "Shift");

/** Popup: one nurse's whole month at a glance. Read-only. Work, approved time off and unavailable days all use words, not color alone. */
export default function NurseMonth({ nurse, data, onClose, onPick }) {
  const closeRef = useRef(null);
  const firstShift = data.shifts.filter((s) => s.employeeId === nurse.id).map((s) => s.date).sort().find((d) => d >= new Date().toISOString().slice(0, 10));
  const start = (firstShift || new Date().toISOString().slice(0, 10)).split("-").map(Number);
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
  const mine = data.shifts.filter((s) => s.employeeId === nurse.id && !s.open);
  const avail = data.availability[nurse.id] || {};
  const leaves = data.leave.filter((l) => l.employeeId === nurse.id && l.status === "approved" && l.type !== "overtime");
  const monthKey = `${y}-${pad(m + 1)}`;
  const monthShifts = mine.filter((s) => s.date.startsWith(monthKey));
  const hours = monthShifts.reduce((t, s) => t + hoursOf(s), 0);
  const step = (delta) => setYm(({ y: yy, m: mm }) => {
    const d = new Date(yy, mm + delta, 1);
    return { y: d.getFullYear(), m: d.getMonth() };
  });

  const cells = [];
  for (let i = 0; i < first; i++) cells.push(<div key={`e${i}`} className="nm-cell empty" aria-hidden="true" />);
  for (let d = 1; d <= days; d++) {
    const date = iso(y, m, d);
    const todays = mine.filter((s) => s.date === date);
    const leave = leaves.find((l) => l.start <= date && date <= l.end);
    const off = avail[date]?.status === "unavailable";
    const parts = [
      ...todays.map((s) => `${kindLabel(s)} ${s.start}–${s.end}`),
      ...(leave ? ["Approved time off"] : []),
      ...(off ? ["Marked unavailable"] : []),
    ];
    const clash = todays.length > 1 || (todays.length > 0 && (leave || off));
    const label = new Date(y, m, d).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
    cells.push(
      <div key={date} className={`nm-cell ${todays.length ? "work" : ""} ${clash ? "clash" : ""}`} role="group"
        aria-label={`${label}: ${parts.length ? parts.join("; ") : "nothing scheduled"}${clash ? ". Conflict." : ""}`}>
        <span className="nm-day">{d}</span>
        {todays.map((s) => <span key={s.id} className="nm-tag">{kindLabel(s)}</span>)}
        {leave && <span className="nm-tag off">Time off</span>}
        {off && !leave && <span className="nm-tag off">Unavail.</span>}
        {clash && <span className="nm-tag bad">Conflict</span>}
      </div>
    );
  }

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal-card nurse-month" role="dialog" aria-modal="true" aria-label={`${nurse.name}, month overview`} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h3>{nurse.name}</h3>
            <p className="muted small day-detail-sub">
              {monthShifts.length === 1 ? "1 shift" : `${monthShifts.length} shifts`} · {hours} hours in {monthLabel}
            </p>
          </div>
          <button type="button" className="icon-btn" ref={closeRef} onClick={onClose} aria-label="Close">
            <XCircle size={18} />
          </button>
        </div>
        <div className="modal-body">
          <div className="cal-head">
            <button type="button" className="icon-btn" onClick={() => step(-1)} aria-label="Previous month"><ChevronLeft size={18} /></button>
            <strong aria-live="polite">{monthLabel}</strong>
            <button type="button" className="icon-btn" onClick={() => step(1)} aria-label="Next month"><ChevronRight size={18} /></button>
          </div>
          <div className="nm-grid nm-dow" aria-hidden="true">{DOW.map((d, i) => <div key={i} className="cal-dow-cell">{d}</div>)}</div>
          <div className="nm-grid">{cells}</div>
          <div className="ticket-actions">
            {onPick && <button type="button" className="primary-btn" onClick={() => { onPick(nurse.id); onClose(); }}>Schedule {nurse.name}</button>}
            <button type="button" className="ghost-btn" onClick={onClose}>Close</button>
          </div>
        </div>
      </div>
    </div>
  );
}
