import { useEffect, useRef } from "react";
import { XCircle } from "lucide-react";

/** Popup for one date and shift of the AI draft: who is working, with name and nurse id. */
export default function DayDetail({ title, shiftLabel, nurses, needed, gap, onClose }) {
  const closeRef = useRef(null);
  const sorted = [...nurses].sort((a, b) => (a.name || a.id).localeCompare(b.name || b.id));

  useEffect(() => {
    const opener = document.activeElement; // give focus back to the cell that opened this
    closeRef.current?.focus();
    return () => opener?.focus?.();
  }, []);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal-card day-detail" role="dialog" aria-modal="true" aria-label={`${title}, ${shiftLabel}`} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h3>{title}</h3>
            <p className="muted small day-detail-sub">{shiftLabel}</p>
          </div>
          <button type="button" className="icon-btn" ref={closeRef} onClick={onClose} aria-label="Close">
            <XCircle size={18} />
          </button>
        </div>
        <div className="modal-body">
          <p className="day-detail-count">
            <strong>{sorted.length === 1 ? "1 nurse working" : `${sorted.length} nurses working`}</strong>
            {needed != null && <span className="muted"> · {needed} needed</span>}
          </p>
          {gap && (
            <p className="approval-error" role="note">
              Short by {Math.max((gap.nurses_needed ?? 0) - (gap.nurses_assigned ?? 0), 0)}
              {gap.gap_reason ? `: ${String(gap.gap_reason).replace(/_/g, " ")}` : "."}
            </p>
          )}
          {sorted.length === 0 ? (
            <p className="muted">Nobody is scheduled for this shift.</p>
          ) : (
            <ul className="day-detail-list">
              {sorted.map((n) => (
                <li key={n.id}>
                  <span>{n.name || "Name not available"}</span>
                  <code>{n.id}</code>
                </li>
              ))}
            </ul>
          )}
          <div className="ticket-actions">
            <button type="button" className="ghost-btn" onClick={onClose}>Close</button>
          </div>
        </div>
      </div>
    </div>
  );
}
