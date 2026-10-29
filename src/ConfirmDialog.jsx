import { useEffect, useRef } from "react";
import { XCircle } from "lucide-react";

/** In-app replacement for window.confirm, which some browsers block. Used before anything that spends money. */
export default function ConfirmDialog({ title, message, confirmLabel, onConfirm, onCancel }) {
  const cancelRef = useRef(null);

  useEffect(() => {
    const opener = document.activeElement;
    cancelRef.current?.focus(); // Cancel is focused first so Enter never spends by accident
    return () => opener?.focus?.();
  }, []);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return (
    <div className="modal-backdrop" onClick={onCancel} role="presentation">
      <div className="modal-card" role="alertdialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button type="button" className="icon-btn" onClick={onCancel} aria-label="Close">
            <XCircle size={18} />
          </button>
        </div>
        <div className="modal-body">
          <p>{message}</p>
          <div className="ticket-actions">
            <button type="button" className="primary-btn" onClick={onConfirm}>{confirmLabel}</button>
            <button type="button" className="ghost-btn" ref={cancelRef} onClick={onCancel}>Cancel</button>
          </div>
        </div>
      </div>
    </div>
  );
}
