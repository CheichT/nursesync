import { useEffect, useId, useRef, useState } from "react";
import { Palette } from "lucide-react";
import { PALETTES } from "./themes";

const MODES = [
  ["light", "Light"],
  ["dark", "Dark"],
  ["auto", "Match my device"],
];

/** "Choose your look": palette and brightness. Changes apply to the whole app straight away. */
export default function AppearanceMenu({ palette, mode, onPalette, onMode, corner = false }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const buttonRef = useRef(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    const onDown = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  return (
    <div className={`appearance ${corner ? "corner" : ""}`} ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className="theme-toggle"
        aria-label="Choose your look"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        title="Choose your look"
        onClick={() => setOpen((v) => !v)}
      >
        <Palette size={16} />
      </button>
      {open && (
        <div className="appearance-panel" id={panelId} role="dialog" aria-label="Choose your look">
          <p className="appearance-title">Choose your look</p>
          <p className="muted small">Saved on this device.</p>
          <fieldset className="appearance-group">
            <legend>Color</legend>
            {PALETTES.map((p) => (
              <label key={p.id} className={`appearance-option ${palette === p.id ? "on" : ""}`}>
                <input type="radio" name="palette" value={p.id} checked={palette === p.id} onChange={() => onPalette(p.id)} />
                <span className="appearance-dots" aria-hidden="true">
                  <i style={{ background: p.light.primary }} />
                  <i style={{ background: p.light.primaryBg }} />
                  <i style={{ background: p.light.warm }} />
                </span>
                <span>
                  {p.name}
                  <span className="muted small"> · {p.note}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <fieldset className="appearance-group">
            <legend>Brightness</legend>
            <div className="appearance-modes">
              {MODES.map(([id, label]) => (
                <label key={id} className={`appearance-mode ${mode === id ? "on" : ""}`}>
                  <input type="radio" name="mode" value={id} checked={mode === id} onChange={() => onMode(id)} />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>
        </div>
      )}
    </div>
  );
}
