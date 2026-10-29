import { useState, useEffect, useCallback } from "react";
import {
  Calendar, AlertTriangle, Bell, CheckCircle, XCircle, Repeat,
  Clock, User, Shield, Plus, LogOut, Trash2, ChevronRight, Send, Pencil, ClipboardCheck, Home, Inbox
} from "lucide-react";
import ApprovalView from "./ApprovalView";
import AppearanceMenu from "./AppearanceMenu";
import NurseHome from "./NurseHome";
import ManagerHome from "./ManagerHome";
import { DEFAULT_PALETTE, isPalette, paletteCss } from "./themes";

const STORAGE_KEY = "scheduler-data";
const REASONS = ["Sick", "Appointment", "Family emergency", "Running late", "Other"];
const LEAVE_TYPES = [
  { key: "vacation", label: "Vacation" },
  { key: "pto", label: "PTO" },
  { key: "fmla", label: "FMLA" },
  { key: "overtime", label: "Overtime request" },
];

const uid = () => `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const today = () => new Date().toISOString().slice(0, 10);
const fmtDate = (d) => {
  if (!d) return "";
  const dt = new Date(d + "T00:00:00");
  return dt.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
};

const emptyData = () => ({
  roster: [{ id: "admin-1", name: "Acting Supervisor", isAdmin: true }],
  availability: {},
  shifts: [],
  swaps: [],
  leave: [],
  notifications: [],
});

function StatusPill({ status }) {
  const map = {
    scheduled: ["Scheduled", "var(--teal)", "var(--teal-bg)"],
    conflict: ["Conflict", "var(--brick)", "var(--brick-bg)"],
    pending: ["Pending", "var(--indigo)", "var(--indigo-bg)"],
    open: ["Open", "var(--indigo)", "var(--indigo-bg)"],
    accepted: ["Accepted", "var(--teal)", "var(--teal-bg)"],
    declined: ["Declined", "var(--brick)", "var(--brick-bg)"],
    approved: ["Approved", "var(--teal)", "var(--teal-bg)"],
    denied: ["Denied", "var(--brick)", "var(--brick-bg)"],
  };
  const [label, color, bg] = map[status] || [status, "var(--ink)", "var(--line)"];
  return (
    <span style={{ color, background: bg }} className="stamp">
      {label}
    </span>
  );
}

const pad2 = (n) => String(n).padStart(2, "0");
const dateKey = (y, m, d) => `${y}-${pad2(m + 1)}-${pad2(d)}`;
const shiftMonth = (y, m, delta) => {
  const dt = new Date(y, m + delta, 1);
  return { year: dt.getFullYear(), month: dt.getMonth() };
};

function MonthCalendar({ year, month, onPrev, onNext, selectedDate, onSelectDate, dayContent, dayLabel }) {
  const first = new Date(year, month, 1);
  const startWeekday = first.getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < startWeekday; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  const monthLabel = first.toLocaleDateString("en-US", { month: "long", year: "numeric" });
  const todayStr = today();

  return (
    <div className="cal">
      <div className="cal-head">
        <button type="button" className="icon-btn" onClick={onPrev} aria-label="Previous month">‹</button>
        <strong>{monthLabel}</strong>
        <button type="button" className="icon-btn" onClick={onNext} aria-label="Next month">›</button>
      </div>
      <div className="cal-grid cal-dow">
        {["S", "M", "T", "W", "T", "F", "S"].map((d, i) => <div key={i} className="cal-dow-cell">{d}</div>)}
      </div>
      <div className="cal-grid">
        {cells.map((d, i) => {
          if (d === null) return <div key={i} className="cal-cell empty" />;
          const ds = dateKey(year, month, d);
          return (
            <button
              type="button"
              key={i}
              className={`cal-cell ${selectedDate === ds ? "selected" : ""} ${ds === todayStr ? "is-today" : ""}`}
              onClick={() => onSelectDate(ds)}
              aria-label={`${fmtDate(ds)}${dayLabel && dayLabel(ds) ? `, ${dayLabel(ds)}` : ""}`}
              aria-pressed={selectedDate === ds}
            >
              <span className="cal-daynum">{d}</span>
              {dayContent ? dayContent(ds) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function App() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);
  const [newName, setNewName] = useState("");
  const [tab, setTab] = useState("");
  const [toast, setToast] = useState("");
  const [mode, setMode] = useState("light"); // "light" | "dark" | "auto"
  const [systemDark, setSystemDark] = useState(false);
  const isDark = mode === "dark" || (mode === "auto" && systemDark);
  const [palette, setPalette] = useState(DEFAULT_PALETTE);
  const [confirmReset, setConfirmReset] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const res = await window.storage.get("theme-pref", false);
        if (res?.value && ["light", "dark", "auto"].includes(res.value)) setMode(res.value);
        const pal = await window.storage.get("palette-pref", false);
        if (pal?.value && isPalette(pal.value)) setPalette(pal.value);
      } catch {}
    })();
  }, []);

  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return undefined;
    setSystemDark(mq.matches);
    const onChange = (e) => setSystemDark(e.matches);
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, []);

  const chooseMode = async (next) => {
    setMode(next);
    try {
      await window.storage.set("theme-pref", next, false);
    } catch {}
  };

  const choosePalette = async (next) => {
    if (!isPalette(next)) return;
    setPalette(next);
    try {
      await window.storage.set("palette-pref", next, false);
    } catch {}
  };

  useEffect(() => {
    (async () => {
      try {
        const res = await window.storage.get(STORAGE_KEY, true);
        setData(res ? JSON.parse(res.value) : emptyData());
      } catch {
        setData(emptyData());
      }
      setLoading(false);
    })();
  }, []);

  const persist = useCallback(async (next) => {
    setData(next);
    setSaving(true);
    try {
      await window.storage.set(STORAGE_KEY, JSON.stringify(next), true);
    } catch {
      showToast("Couldn't save — check your connection.");
    }
    setSaving(false);
  }, []);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(""), 3000);
  };

  const notify = (list, audience, message, relatedId) => {
    list.push({ id: uid(), audience, message, relatedId, ts: Date.now(), read: false });
  };

  const resetRoster = async () => {
    await persist(emptyData());
    setConfirmReset(false);
    showToast("Roster cleared.");
  };

  const saveNameEdit = async () => {
    const trimmed = nameInput.trim();
    if (!trimmed) return;
    const roster = data.roster.map((u) => u.id === currentUser.id ? { ...u, name: trimmed } : u);
    await persist({ ...data, roster });
    setCurrentUser({ ...currentUser, name: trimmed });
    setEditingName(false);
    showToast("Name updated.");
  };

  if (loading || !data) {
    return (
      <div className={`scheduler-root pal-${palette} center-screen ${isDark ? "dark" : ""}`}>
        <style>{GLOBAL_CSS}</style>
        <div className="loader">Loading schedule board…</div>
      </div>
    );
  }

  if (!currentUser) {
    return (
      <div className={`scheduler-root pal-${palette} center-screen ${isDark ? "dark" : ""}`}>
        <style>{GLOBAL_CSS}</style>
        <AppearanceMenu corner palette={palette} mode={mode} onPalette={choosePalette} onMode={chooseMode} />
        <LoginScreen
          data={data}
          persist={persist}
          newName={newName}
          setNewName={setNewName}
          onSelect={(u) => { setCurrentUser(u); setTab("home"); }}
        />
      </div>
    );
  }

  const myNotifs = data.notifications
    .filter((n) => n.audience === (currentUser.isAdmin ? "admin" : currentUser.id))
    .sort((a, b) => b.ts - a.ts);
  const unread = myNotifs.filter((n) => !n.read).length;
  const groups = currentUser.isAdmin ? ADMIN_GROUPS : EMP_GROUPS;
  const group = groups.find((g) => g.leaves.some((l) => l.key === tab)) || groups[0];

  return (
    <div className={`scheduler-root pal-${palette} ${isDark ? "dark" : ""}`}>
      <style>{GLOBAL_CSS}</style>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">NS</span>
          <span className="brand-name">NurseSync</span>
        </div>
        <div className="topbar-right">
          <AppearanceMenu palette={palette} mode={mode} onPalette={choosePalette} onMode={chooseMode} />
          <span className="who">
            {currentUser.isAdmin ? <Shield size={14} /> : <User size={14} />}
            {currentUser.name}
            <button className="icon-btn" onClick={() => { setNameInput(currentUser.name); setEditingName(true); }} title="Edit name" aria-label="Edit name">
              <Pencil size={13} />
            </button>
          </span>
          {currentUser.isAdmin && (
            <button className="ghost-btn small" onClick={() => setConfirmReset(true)} title="Clear all names and reset data">
              <Trash2 size={13} /> Clear names
            </button>
          )}
          <button className="ghost-btn" onClick={() => { setCurrentUser(null); setTab(""); }}>
            <LogOut size={14} /> Switch
          </button>
        </div>
      </header>

      <nav className="tabbar tabbar-bottom" aria-label="Main">
        {groups.map((g) => {
          const active = group.key === g.key;
          return (
            <button
              key={g.key}
              className={`tab ${active ? "tab-active" : ""}`}
              aria-current={active ? "page" : undefined}
              onClick={() => !active && setTab(g.leaves[0].key)}
            >
              {g.icon}
              {g.label}
              {g.key === "notifications" && unread > 0 && <span className="badge">{unread}</span>}
            </button>
          );
        })}
      </nav>
      {group.leaves.length > 1 && (
        <nav className="subtabs" aria-label={`${group.label} sections`}>
          {group.leaves.map((l) => (
            <button
              key={l.key}
              className={`subtab ${tab === l.key ? "on" : ""}`}
              aria-current={tab === l.key ? "page" : undefined}
              onClick={() => setTab(l.key)}
            >
              {l.label}
            </button>
          ))}
        </nav>
      )}

      <main className="content">
        {currentUser.isAdmin ? (
          <AdminPanels tab={tab} data={data} persist={persist} notify={notify} showToast={showToast} goTo={setTab} unreadAlerts={unread} />
        ) : (
          <EmployeePanels
            tab={tab}
            data={data}
            persist={persist}
            notify={notify}
            currentUser={currentUser}
            showToast={showToast}
            goTo={setTab}
            unreadAlerts={unread}
          />
        )}
      </main>

      {editingName && (
        <Modal title="Edit your name" onClose={() => setEditingName(false)}>
          <label>Name
            <input
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && saveNameEdit()}
              autoFocus
            />
          </label>
          <button className="primary-btn" onClick={saveNameEdit}><CheckCircle size={14} /> Save</button>
        </Modal>
      )}
      {confirmReset && (
        <Modal title="Clear all names?" onClose={() => setConfirmReset(false)}>
          <p className="muted">This removes every employee, shift, availability entry, swap, and leave request — back to just the admin account. It can't be undone.</p>
          <button className="primary-btn" onClick={resetRoster}><Trash2 size={14} /> Yes, clear everything</button>
        </Modal>
      )}
      {toast && <div className="toast">{toast}</div>}
      {saving && <div className="saving-dot" title="Saving…" />}
    </div>
  );
}

// Nurse navigation: four top-level tabs. Schedule and Requests hold the older screens as sections.
const EMP_GROUPS = [
  { key: "home", label: "Home", icon: <Home size={15} />, leaves: [{ key: "home", label: "Home" }] },
  {
    key: "schedule", label: "Schedule", icon: <Calendar size={15} />,
    leaves: [{ key: "week", label: "My week" }, { key: "shifts", label: "My shifts" }, { key: "availability", label: "Availability" }],
  },
  { key: "requests", label: "Requests", icon: <Inbox size={15} />, leaves: [{ key: "swaps", label: "Swaps" }, { key: "leave", label: "Leave" }] },
  { key: "notifications", label: "Alerts", icon: <Bell size={15} />, leaves: [{ key: "notifications", label: "Alerts" }] },
];
const ADMIN_GROUPS = [
  { key: "home", label: "Home", icon: <Home size={15} />, leaves: [{ key: "home", label: "Home" }] },
  {
    key: "schedule", label: "Schedule", icon: <Calendar size={15} />,
    leaves: [{ key: "builder", label: "Build" }, { key: "daily", label: "Daily breakdown" }, { key: "approve", label: "AI draft" }],
  },
  { key: "requests", label: "Requests", icon: <Inbox size={15} />, leaves: [{ key: "swapapprovals", label: "Swaps" }, { key: "leaveapprovals", label: "Leave" }] },
  { key: "team", label: "Team", icon: <User size={15} />, leaves: [{ key: "team", label: "Availability" }] },
  { key: "notifications", label: "Alerts", icon: <Bell size={15} />, leaves: [{ key: "notifications", label: "Alerts" }] },
];

function LoginScreen({ data, persist, newName, setNewName, onSelect }) {
  const addEmployee = async () => {
    const name = newName.trim();
    if (!name) return;
    const u = { id: uid(), name, isAdmin: false };
    await persist({ ...data, roster: [...data.roster, u] });
    setNewName("");
    onSelect(u);
  };
  return (
    <div className="login-card">
      <span className="brand-mark big">NS</span>
      <h1>NurseSync</h1>
      <p className="muted">Who's clocking in?</p>
      <div className="roster-list">
        {data.roster.map((u) => (
          <button key={u.id} className="roster-item" onClick={() => onSelect(u)}>
            <span>
              {u.isAdmin ? <Shield size={14} /> : <User size={14} />} {u.name}
            </span>
            <ChevronRight size={16} />
          </button>
        ))}
      </div>
      <div className="add-row">
        <input
          aria-label="Your name, to join the team"
          placeholder="Add your name to join the team…"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addEmployee()}
        />
        <button className="primary-btn" onClick={addEmployee}>
          <Plus size={15} /> Join
        </button>
      </div>
    </div>
  );
}

/* ---------- EMPLOYEE PANELS ---------- */
function EmployeePanels({ tab, data, persist, notify, currentUser, showToast, goTo, unreadAlerts }) {
  if (tab === "home") return <NurseHome data={data} currentUser={currentUser} goTo={goTo} unreadAlerts={unreadAlerts} />;
  if (tab === "week") return <MyWeekTab data={data} currentUser={currentUser} />;
  if (tab === "availability") return <AvailabilityTab data={data} persist={persist} currentUser={currentUser} showToast={showToast} />;
  if (tab === "shifts") return <MyShiftsTab data={data} persist={persist} notify={notify} currentUser={currentUser} showToast={showToast} />;
  if (tab === "swaps") return <SwapsTab data={data} persist={persist} notify={notify} currentUser={currentUser} showToast={showToast} />;
  if (tab === "leave") return <LeaveTab data={data} persist={persist} notify={notify} currentUser={currentUser} showToast={showToast} />;
  if (tab === "notifications") return <NotificationsTab data={data} persist={persist} audience={currentUser.id} />;
  return null;
}

function MyWeekTab({ data, currentUser }) {
  const [weekOffset, setWeekOffset] = useState(0);

  const base = new Date();
  base.setDate(base.getDate() + weekOffset * 7);
  const sunday = new Date(base);
  sunday.setDate(base.getDate() - base.getDay());
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(sunday);
    d.setDate(sunday.getDate() + i);
    return d;
  });
  const toKey = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  const mine = data.shifts.filter((s) => s.employeeId === currentUser.id && !s.open);
  const rangeLabel = `${days[0].toLocaleDateString("en-US", { month: "short", day: "numeric" })} – ${days[6].toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
  const isThisWeek = weekOffset === 0;

  return (
    <div className="panel">
      <h2>My week</h2>
      <p className="muted">Your shifts for {isThisWeek ? "this week" : "the week of"} {rangeLabel}.</p>
      <div className="cal-head" style={{ marginBottom: 14 }}>
        <button type="button" className="icon-btn" onClick={() => setWeekOffset((o) => o - 1)} aria-label="Previous week">‹</button>
        <strong>{rangeLabel}</strong>
        <button type="button" className="icon-btn" onClick={() => setWeekOffset((o) => o + 1)} aria-label="Next week">›</button>
      </div>
      <div className="stack">
        {days.map((d, i) => {
          const ds = toKey(d);
          const shiftsForDay = mine.filter((s) => s.date === ds).sort((a, b) => a.start.localeCompare(b.start));
          const isToday = ds === today();
          return (
            <div className={`row-card ${isToday ? "unread" : ""}`} key={i}>
              <div>
                <strong>{d.toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" })}</strong>
                {shiftsForDay.length === 0 ? (
                  <div className="muted small">Off</div>
                ) : (
                  shiftsForDay.map((s) => <div className="muted small" key={s.id}>{s.start} – {s.end}</div>)
                )}
              </div>
              <div className="ticket-actions">
                {shiftsForDay.map((s) => <StatusPill key={s.id} status={s.status} />)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AvailabilityTab({ data, persist, currentUser, showToast }) {
  const now = new Date();
  const [viewYear, setViewYear] = useState(now.getFullYear());
  const [viewMonth, setViewMonth] = useState(now.getMonth());
  const [date, setDate] = useState(today());
  const [open, setOpen] = useState(false); // the day popup
  const [status, setStatus] = useState(""); // "available" | "unavailable" | "" (not chosen yet)
  const [reason, setReason] = useState(""); // "" shows the "Reason" placeholder
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  const mine = data.availability[currentUser.id] || {};
  const entries = Object.entries(mine).sort((a, b) => a[0].localeCompare(b[0]));

  const pickDay = (ds) => {
    setDate(ds);
    const existing = mine[ds];
    setStatus(existing ? existing.status : "");
    setReason(existing?.reason || "");
    setNote(existing?.note || "");
    setError("");
    setOpen(true);
  };

  const dayContent = (ds) => {
    const v = mine[ds];
    if (!v) return null;
    return v.status === "unavailable"
      ? <span className="cal-mark no" aria-hidden="true">✕</span>
      : <span className="cal-mark ok" aria-hidden="true">✓</span>;
  };

  const dayLabel = (ds) => {
    const v = mine[ds];
    if (!v) return "";
    return v.status === "unavailable" ? `unavailable${v.reason ? ` (${v.reason})` : ""}` : "available";
  };

  const save = async () => {
    if (!status) {
      setError("Choose Available or Unavailable.");
      return;
    }
    if (status === "unavailable" && !reason) {
      setError("Choose a reason.");
      return;
    }
    const nextMine = { ...mine, [date]: { status, reason: status === "unavailable" ? reason : null, note: status === "unavailable" ? note : "" } };
    await persist({ ...data, availability: { ...data.availability, [currentUser.id]: nextMine } });
    setOpen(false);
    showToast("Availability saved.");
  };

  const remove = async (d) => {
    const nextMine = { ...mine };
    delete nextMine[d];
    await persist({ ...data, availability: { ...data.availability, [currentUser.id]: nextMine } });
  };

  const clearDay = async () => {
    await remove(date);
    setOpen(false);
    showToast("Day cleared.");
  };

  return (
    <div className="panel">
      <h2>Mark your availability</h2>
      <p className="muted">Tap a day to mark it. ✓ means available, ✕ means unavailable.</p>
      <div className="card">
        <MonthCalendar
          year={viewYear}
          month={viewMonth}
          onPrev={() => { const s = shiftMonth(viewYear, viewMonth, -1); setViewYear(s.year); setViewMonth(s.month); }}
          onNext={() => { const s = shiftMonth(viewYear, viewMonth, 1); setViewYear(s.year); setViewMonth(s.month); }}
          selectedDate={date}
          onSelectDate={pickDay}
          dayContent={dayContent}
          dayLabel={dayLabel}
        />
      </div>

      {open && (
        <Modal title={fmtDate(date)} onClose={() => setOpen(false)}>
          <fieldset className="choice-group">
            <legend>Are you available?</legend>
            <div className="choice-row">
              <label className={`choice ${status === "available" ? "on" : ""}`}>
                <input type="radio" name="avail-status" value="available" autoFocus checked={status === "available"} onChange={() => { setStatus("available"); setError(""); }} />
                <span className="choice-mark ok" aria-hidden="true">✓</span> Available
              </label>
              <label className={`choice ${status === "unavailable" ? "on" : ""}`}>
                <input type="radio" name="avail-status" value="unavailable" checked={status === "unavailable"} onChange={() => { setStatus("unavailable"); setError(""); }} />
                <span className="choice-mark no" aria-hidden="true">✕</span> Not available
              </label>
            </div>
          </fieldset>
          {status === "unavailable" && (
            <>
              <label>Reason
                <select value={reason} onChange={(e) => { setReason(e.target.value); setError(""); }} aria-label="Reason">
                  <option value="" disabled>Reason</option>
                  {REASONS.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </label>
              <label>Note (optional)
                <input placeholder="e.g. dentist at 2pm" value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
            </>
          )}
          {error && <p className="approval-error" role="alert">{error}</p>}
          <div className="ticket-actions">
            <button type="button" className="primary-btn" onClick={save}><CheckCircle size={15} /> Save</button>
            <button type="button" className="ghost-btn" onClick={() => setOpen(false)}>Cancel</button>
            {mine[date] && <button type="button" className="ghost-btn" onClick={clearDay}>Clear this day</button>}
          </div>
        </Modal>
      )}

      <h3 className="section-label">Your marked days</h3>
      {entries.length === 0 && <p className="muted">Nothing marked yet.</p>}
      <div className="stack">
        {entries.map(([d, v]) => (
          <div className="row-card" key={d}>
            <div>
              <strong>{fmtDate(d)}</strong>
              <div className="muted small">
                {v.status === "unavailable" ? `Unavailable · ${v.reason}${v.note ? " — " + v.note : ""}` : "Available"}
              </div>
            </div>
            <button className="icon-btn" onClick={() => remove(d)} aria-label={`Remove availability for ${fmtDate(d)}`}><Trash2 size={15} /></button>
          </div>
        ))}
      </div>
    </div>
  );
}

function MyShiftsTab({ data, persist, notify, currentUser, showToast }) {
  const [issueFor, setIssueFor] = useState(null);
  const [reason, setReason] = useState(REASONS[0]);
  const [note, setNote] = useState("");
  const [swapFor, setSwapFor] = useState(null);
  const [swapTo, setSwapTo] = useState("");

  const mine = data.shifts.filter((s) => s.employeeId === currentUser.id).sort((a, b) => a.date.localeCompare(b.date));
  const others = data.roster.filter((u) => u.id !== currentUser.id && !u.isAdmin);

  const reportIssue = async () => {
    const shifts = data.shifts.map((s) => s.id === issueFor ? { ...s, status: "conflict" } : s);
    const notifs = [...data.notifications];
    const shift = data.shifts.find((s) => s.id === issueFor);
    notify(notifs, "admin", `${currentUser.name} can't make ${fmtDate(shift.date)} (${shift.start}-${shift.end}) — ${reason}${note ? ": " + note : ""}. Needs rescheduling.`, shift.id);
    notify(notifs, currentUser.id, `You flagged a conflict for ${fmtDate(shift.date)}. Admin has been notified.`, shift.id);
    await persist({ ...data, shifts, notifications: notifs });
    setIssueFor(null); setNote(""); showToast("Admin notified.");
  };

  const requestSwap = async () => {
    const shift = data.shifts.find((s) => s.id === swapFor);
    const partner = data.roster.find((u) => u.id === swapTo);
    if (!partner) return;
    const swap = { id: uid(), shiftId: shift.id, fromId: currentUser.id, toId: partner.id, status: "pending", createdAt: Date.now() };
    const notifs = [...data.notifications];
    notify(notifs, partner.id, `${currentUser.name} wants to swap their ${fmtDate(shift.date)} shift with you.`, swap.id);
    await persist({ ...data, swaps: [...data.swaps, swap], notifications: notifs });
    setSwapFor(null); setSwapTo(""); showToast("Swap request sent.");
  };

  const giveAway = async (shiftId) => {
    const shift = data.shifts.find((s) => s.id === shiftId);
    const shifts = data.shifts.map((s) => s.id === shiftId ? { ...s, open: true } : s);
    const notifs = [...data.notifications];
    others.forEach((o) => notify(notifs, o.id, `${currentUser.name} put their ${fmtDate(shift.date)} shift (${shift.start}-${shift.end}) up for grabs.`, shift.id));
    await persist({ ...data, shifts, notifications: notifs });
    showToast("Shift posted to the open board.");
  };

  const coworkersOn = (dateStr, shiftId) =>
    data.shifts
      .filter((s) => s.id !== shiftId && s.date === dateStr && s.employeeId !== currentUser.id && !s.open)
      .map((s) => data.roster.find((u) => u.id === s.employeeId)?.name)
      .filter(Boolean);

  return (
    <div className="panel">
      <h2>My upcoming shifts</h2>
      {mine.length === 0 && <p className="muted">No shifts assigned yet.</p>}
      <div className="stack">
        {mine.map((s) => {
          const coworkers = coworkersOn(s.date, s.id);
          return (
            <div className="row-card ticket" key={s.id}>
              <div>
                <strong>{fmtDate(s.date)}</strong>
                <div className="muted small">{s.start} – {s.end}</div>
                <div className="muted small">
                  {s.open ? "Posted to open board — waiting for someone to claim" : coworkers.length > 0 ? `Working with ${coworkers.join(", ")}` : "Working solo that day"}
                </div>
              </div>
              <div className="ticket-actions">
                <StatusPill status={s.open ? "open" : s.status} />
                {!s.open && (
                  <>
                    <button className="ghost-btn small" onClick={() => setIssueFor(s.id)}><AlertTriangle size={13} /> Report issue</button>
                    <button className="ghost-btn small" onClick={() => setSwapFor(s.id)}><Repeat size={13} /> Swap</button>
                    <button className="ghost-btn small" onClick={() => giveAway(s.id)}><Send size={13} /> Give away</button>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {issueFor && (
        <Modal title="Report a scheduling issue" onClose={() => setIssueFor(null)}>
          <label>Reason
            <select value={reason} onChange={(e) => setReason(e.target.value)}>
              {REASONS.map((r) => <option key={r}>{r}</option>)}
            </select>
          </label>
          <label>Note (optional)<input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add detail…" /></label>
          <button className="primary-btn" onClick={reportIssue}><Send size={14} /> Notify admin</button>
        </Modal>
      )}

      {swapFor && (
        <Modal title="Request a shift swap" onClose={() => setSwapFor(null)}>
          <label>Swap with
            <select value={swapTo} onChange={(e) => setSwapTo(e.target.value)}>
              <option value="">Choose a coworker…</option>
              {others.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          </label>
          <button className="primary-btn" disabled={!swapTo} onClick={requestSwap}><Send size={14} /> Send request</button>
        </Modal>
      )}
    </div>
  );
}

function SwapsTab({ data, persist, notify, currentUser, showToast }) {
  const incoming = data.swaps.filter((s) => s.toId === currentUser.id && s.status === "pending");
  const mine = data.swaps.filter((s) => s.fromId === currentUser.id);
  const openShifts = data.shifts.filter((s) => s.open && s.employeeId !== currentUser.id).sort((a, b) => a.date.localeCompare(b.date));

  const respond = async (swapId, accept) => {
    const swaps = data.swaps.map((s) => s.id === swapId ? { ...s, status: accept ? "accepted" : "declined" } : s);
    const swap = data.swaps.find((s) => s.id === swapId);
    const notifs = [...data.notifications];
    if (accept) {
      notify(notifs, "admin", `Swap accepted between coworkers — needs your approval to finalize.`, swap.id);
    }
    notify(notifs, swap.fromId, `Your swap request was ${accept ? "accepted — pending admin approval" : "declined"}.`, swap.id);
    await persist({ ...data, swaps, notifications: notifs });
    showToast(accept ? "Sent to admin for approval." : "Declined.");
  };

  const claim = async (shiftId) => {
    const shift = data.shifts.find((s) => s.id === shiftId);
    const originalOwnerId = shift.employeeId;
    const avail = data.availability[currentUser.id]?.[shift.date];
    const conflict = avail?.status === "unavailable";
    const shifts = data.shifts.map((s) => s.id === shiftId ? { ...s, employeeId: currentUser.id, open: false, status: conflict ? "conflict" : "scheduled" } : s);
    const notifs = [...data.notifications];
    notify(notifs, "admin", `${currentUser.name} claimed the open shift on ${fmtDate(shift.date)} (previously ${data.roster.find(u => u.id === originalOwnerId)?.name || "unassigned"}).${conflict ? " Heads up — this conflicts with their marked availability." : ""}`, shift.id);
    notify(notifs, originalOwnerId, `${currentUser.name} picked up your ${fmtDate(shift.date)} shift.`, shift.id);
    await persist({ ...data, shifts, notifications: notifs });
    showToast("Shift claimed.");
  };

  const shiftInfo = (id) => data.shifts.find((s) => s.id === id);
  const nameOf = (id) => data.roster.find((u) => u.id === id)?.name || "—";

  return (
    <div className="panel">
      <h2>Open shifts</h2>
      <p className="muted">Shifts coworkers have put up for grabs — first to claim gets it, pending admin's ok if it creates a conflict.</p>
      {openShifts.length === 0 && <p className="muted">No open shifts right now.</p>}
      <div className="stack">
        {openShifts.map((s) => (
          <div className="row-card ticket" key={s.id}>
            <div>
              <strong>{fmtDate(s.date)}</strong>
              <div className="muted small">{s.start} – {s.end} · was {nameOf(s.employeeId)}'s</div>
            </div>
            <button className="ghost-btn small" onClick={() => claim(s.id)}><CheckCircle size={13} /> Claim shift</button>
          </div>
        ))}
      </div>

      <h3 className="section-label">Incoming swap requests</h3>
      {incoming.length === 0 && <p className="muted">No pending requests.</p>}
      <div className="stack">
        {incoming.map((s) => {
          const sh = shiftInfo(s.shiftId);
          return (
            <div className="row-card" key={s.id}>
              <div>
                <strong>{nameOf(s.fromId)}</strong>
                <div className="muted small">wants you to cover {sh ? `${fmtDate(sh.date)}, ${sh.start}-${sh.end}` : "a shift"}</div>
              </div>
              <div className="ticket-actions">
                <button className="ghost-btn small" onClick={() => respond(s.id, true)}><CheckCircle size={13} /> Accept</button>
                <button className="ghost-btn small" onClick={() => respond(s.id, false)}><XCircle size={13} /> Decline</button>
              </div>
            </div>
          );
        })}
      </div>

      <h3 className="section-label">Your outgoing requests</h3>
      {mine.length === 0 && <p className="muted">You haven't requested any swaps.</p>}
      <div className="stack">
        {mine.map((s) => (
          <div className="row-card" key={s.id}>
            <div>
              <strong>To {nameOf(s.toId)}</strong>
              <div className="muted small">{shiftInfo(s.shiftId) ? fmtDate(shiftInfo(s.shiftId).date) : ""}</div>
            </div>
            <StatusPill status={s.status} />
          </div>
        ))}
      </div>
    </div>
  );
}

function LeaveTab({ data, persist, notify, currentUser, showToast }) {
  const [type, setType] = useState("vacation");
  const [start, setStart] = useState(today());
  const [end, setEnd] = useState(today());
  const [note, setNote] = useState("");

  const mine = data.leave.filter((l) => l.employeeId === currentUser.id).sort((a, b) => b.createdAt - a.createdAt);

  const submit = async () => {
    const req = { id: uid(), employeeId: currentUser.id, type, start, end, note, status: "pending", createdAt: Date.now() };
    const notifs = [...data.notifications];
    notify(notifs, "admin", `${currentUser.name} submitted a ${LEAVE_TYPES.find(t => t.key === type).label} request (${fmtDate(start)} – ${fmtDate(end)}).`, req.id);
    await persist({ ...data, leave: [...data.leave, req], notifications: notifs });
    setNote(""); showToast("Request submitted.");
  };

  return (
    <div className="panel">
      <h2>Request time off</h2>
      <div className="card form-card">
        <div className="form-row">
          <label>Type
            <select value={type} onChange={(e) => setType(e.target.value)}>
              {LEAVE_TYPES.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
            </select>
          </label>
          <label>Start<input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label>
          <label>End<input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
        </div>
        <label>Note<input value={note} onChange={(e) => setNote(e.target.value)} placeholder={type === "overtime" ? "How many extra hours, and why" : "Optional details"} /></label>
        <button className="primary-btn" onClick={submit}><Send size={14} /> Submit request</button>
      </div>

      <h3 className="section-label">Your requests</h3>
      {mine.length === 0 && <p className="muted">No requests yet.</p>}
      <div className="stack">
        {mine.map((l) => (
          <div className="row-card" key={l.id}>
            <div>
              <strong>{LEAVE_TYPES.find((t) => t.key === l.type).label}</strong>
              <div className="muted small">{fmtDate(l.start)} – {fmtDate(l.end)}{l.note ? " · " + l.note : ""}</div>
            </div>
            <StatusPill status={l.status} />
          </div>
        ))}
      </div>
    </div>
  );
}

function NotificationsTab({ data, persist, audience }) {
  const mine = data.notifications.filter((n) => n.audience === audience).sort((a, b) => b.ts - a.ts);
  const markAllRead = async () => {
    const notifications = data.notifications.map((n) => n.audience === audience ? { ...n, read: true } : n);
    await persist({ ...data, notifications });
  };
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Notifications</h2>
        {mine.some((n) => !n.read) && <button className="ghost-btn small" onClick={markAllRead}>Mark all read</button>}
      </div>
      {mine.length === 0 && <p className="muted">Nothing here yet.</p>}
      <div className="stack">
        {mine.map((n) => (
          <div className={`row-card ${!n.read ? "unread" : ""}`} key={n.id}>
            <div>
              <div>{n.message}</div>
              <div className="muted small">{new Date(n.ts).toLocaleString()}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------- ADMIN PANELS ---------- */
function AdminPanels({ tab, data, persist, notify, showToast, goTo, unreadAlerts }) {
  if (tab === "home") return <ManagerHome data={data} goTo={goTo} unreadAlerts={unreadAlerts} />;
  if (tab === "daily") return <DailyBreakdown data={data} />;
  if (tab === "builder") return <ScheduleBuilder data={data} persist={persist} notify={notify} showToast={showToast} />;
  if (tab === "approve") return <ApprovalView showToast={showToast} />;
  if (tab === "team") return <TeamAvailability data={data} />;
  if (tab === "swapapprovals") return <SwapApprovals data={data} persist={persist} notify={notify} showToast={showToast} />;
  if (tab === "leaveapprovals") return <LeaveApprovals data={data} persist={persist} notify={notify} showToast={showToast} />;
  if (tab === "notifications") return <NotificationsTab data={data} persist={persist} audience="admin" />;
  return null;
}

function DailyBreakdown({ data }) {
  const [date, setDate] = useState(today());
  const employees = data.roster.filter((u) => !u.isAdmin);
  const nameOf = (id) => data.roster.find((u) => u.id === id)?.name || "—";

  const working = data.shifts
    .filter((s) => s.date === date && !s.open)
    .sort((a, b) => a.start.localeCompare(b.start));
  const openThatDay = data.shifts.filter((s) => s.date === date && s.open);
  const workingIds = new Set(working.map((s) => s.employeeId));
  const offToday = employees.filter((e) => !workingIds.has(e.id));
  const unavailableToday = employees.filter((e) => data.availability[e.id]?.[date]?.status === "unavailable");

  return (
    <div className="panel">
      <h2>Daily breakdown</h2>
      <p className="muted">Everyone on schedule for a given day, at a glance.</p>
      <div className="card form-card">
        <label>Date<input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
      </div>

      <h3 className="section-label" style={{ marginTop: 0 }}>Working — {fmtDate(date)}</h3>
      {working.length === 0 && <p className="muted">Nobody's scheduled that day.</p>}
      <div className="stack">
        {working.map((s) => (
          <div className="row-card" key={s.id}>
            <div>
              <strong>{nameOf(s.employeeId)}</strong>
              <div className="muted small">{s.start} – {s.end}</div>
            </div>
            <StatusPill status={s.status} />
          </div>
        ))}
      </div>

      {openThatDay.length > 0 && (
        <>
          <h3 className="section-label">Open that day</h3>
          <div className="stack">
            {openThatDay.map((s) => (
              <div className="row-card" key={s.id}>
                <div>
                  <strong>Unclaimed shift</strong>
                  <div className="muted small">{s.start} – {s.end} · was {nameOf(s.employeeId)}'s</div>
                </div>
                <StatusPill status="open" />
              </div>
            ))}
          </div>
        </>
      )}

      <h3 className="section-label">Not working</h3>
      {offToday.length === 0 && <p className="muted">Everyone's on the schedule.</p>}
      <div className="stack">
        {offToday.map((e) => {
          const isMarkedOff = unavailableToday.some((u) => u.id === e.id);
          return (
            <div className="row-card" key={e.id}>
              <div>
                <strong>{e.name}</strong>
                {isMarkedOff && <div className="muted small">Marked unavailable</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ScheduleBuilder({ data, persist, notify, showToast }) {
  const employees = data.roster.filter((u) => !u.isAdmin);
  const [employeeId, setEmployeeId] = useState(employees[0]?.id || "");
  const [date, setDate] = useState(today());
  const [start, setStart] = useState("09:00");
  const [end, setEnd] = useState("17:00");

  const addShift = async () => {
    if (!employeeId) { showToast("Add an employee first."); return; }
    const emp = data.roster.find((u) => u.id === employeeId);
    const avail = data.availability[employeeId]?.[date];
    const conflict = avail?.status === "unavailable";
    const shift = { id: uid(), employeeId, date, start, end, status: conflict ? "conflict" : "scheduled" };
    const notifs = [...data.notifications];
    if (conflict) {
      notify(notifs, "admin", `Conflict: ${emp.name} was marked unavailable (${avail.reason}) on ${fmtDate(date)} but was scheduled anyway.`, shift.id);
      notify(notifs, employeeId, `You were scheduled ${fmtDate(date)}, ${start}-${end} — this conflicts with your marked unavailability. Please reschedule.`, shift.id);
    }
    await persist({ ...data, shifts: [...data.shifts, shift], notifications: notifs });
    showToast(conflict ? "Shift added — conflict flagged." : "Shift added.");
  };

  const removeShift = async (id) => {
    await persist({ ...data, shifts: data.shifts.filter((s) => s.id !== id) });
  };

  const sorted = [...data.shifts].sort((a, b) => a.date.localeCompare(b.date));
  const nameOf = (id) => data.roster.find((u) => u.id === id)?.name || "—";

  return (
    <div className="panel">
      <h2>Build the schedule</h2>
      <div className="card form-card">
        <div className="form-row">
          <label>Employee
            <select value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}>
              {employees.length === 0 && <option value="">No employees yet</option>}
              {employees.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
            </select>
          </label>
          <label>Date<input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
        </div>
        <div className="form-row">
          <label>Start<input type="time" value={start} onChange={(e) => setStart(e.target.value)} /></label>
          <label>End<input type="time" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
        </div>
        <button className="primary-btn" onClick={addShift}><Plus size={15} /> Add shift</button>
      </div>

      <h3 className="section-label">All shifts</h3>
      {sorted.length === 0 && <p className="muted">No shifts scheduled yet.</p>}
      <div className="stack">
        {sorted.map((s) => (
          <div className="row-card ticket" key={s.id}>
            <div>
              <strong>{nameOf(s.employeeId)}</strong>
              <div className="muted small">{fmtDate(s.date)} · {s.start}–{s.end}</div>
            </div>
            <div className="ticket-actions">
              <StatusPill status={s.status} />
              <button className="icon-btn" onClick={() => removeShift(s.id)} aria-label={`Remove shift for ${nameOf(s.employeeId)} on ${fmtDate(s.date)}`}><Trash2 size={15} /></button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TeamAvailability({ data }) {
  const employees = data.roster.filter((u) => !u.isAdmin);
  return (
    <div className="panel">
      <h2>Team availability</h2>
      {employees.length === 0 && <p className="muted">No employees have joined yet.</p>}
      <div className="stack">
        {employees.map((e) => {
          const entries = Object.entries(data.availability[e.id] || {})
            .filter(([, v]) => v.status === "unavailable")
            .sort((a, b) => a[0].localeCompare(b[0]));
          return (
            <div className="card" key={e.id}>
              <strong>{e.name}</strong>
              {entries.length === 0 && <p className="muted small">No unavailable days marked.</p>}
              <div className="stack tight">
                {entries.map(([d, v]) => (
                  <div className="mini-row" key={d}>
                    <span>{fmtDate(d)}</span>
                    <span className="muted small">{v.reason}{v.note ? " — " + v.note : ""}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SwapApprovals({ data, persist, notify, showToast }) {
  const pending = data.swaps.filter((s) => s.status === "accepted");
  const nameOf = (id) => data.roster.find((u) => u.id === id)?.name || "—";
  const shiftInfo = (id) => data.shifts.find((s) => s.id === id);

  const decide = async (swap, approve) => {
    let shifts = data.shifts;
    if (approve) {
      shifts = data.shifts.map((s) => s.id === swap.shiftId ? { ...s, employeeId: swap.toId, status: "scheduled" } : s);
    }
    const swaps = data.swaps.map((s) => s.id === swap.id ? { ...s, status: approve ? "approved" : "denied" } : s);
    const notifs = [...data.notifications];
    notify(notifs, swap.fromId, `Your swap was ${approve ? "approved" : "denied"} by admin.`, swap.id);
    notify(notifs, swap.toId, `The swap you accepted was ${approve ? "approved" : "denied"} by admin.`, swap.id);
    await persist({ ...data, shifts, swaps, notifications: notifs });
    showToast(approve ? "Swap approved." : "Swap denied.");
  };

  return (
    <div className="panel">
      <h2>Swap approvals</h2>
      {pending.length === 0 && <p className="muted">Nothing waiting on you.</p>}
      <div className="stack">
        {pending.map((s) => {
          const sh = shiftInfo(s.shiftId);
          return (
            <div className="row-card" key={s.id}>
              <div>
                <strong>{nameOf(s.fromId)} → {nameOf(s.toId)}</strong>
                <div className="muted small">{sh ? `${fmtDate(sh.date)}, ${sh.start}-${sh.end}` : ""}</div>
              </div>
              <div className="ticket-actions">
                <button className="ghost-btn small" onClick={() => decide(s, true)}><CheckCircle size={13} /> Approve</button>
                <button className="ghost-btn small" onClick={() => decide(s, false)}><XCircle size={13} /> Deny</button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function LeaveApprovals({ data, persist, notify, showToast }) {
  const pending = data.leave.filter((l) => l.status === "pending").sort((a, b) => a.createdAt - b.createdAt);
  const nameOf = (id) => data.roster.find((u) => u.id === id)?.name || "—";

  const decide = async (req, approve) => {
    const leave = data.leave.map((l) => l.id === req.id ? { ...l, status: approve ? "approved" : "denied" } : l);
    const notifs = [...data.notifications];
    notify(notifs, req.employeeId, `Your ${LEAVE_TYPES.find(t => t.key === req.type).label} request was ${approve ? "approved" : "denied"}.`, req.id);
    await persist({ ...data, leave, notifications: notifs });
    showToast(approve ? "Approved." : "Denied.");
  };

  return (
    <div className="panel">
      <h2>Leave requests</h2>
      {pending.length === 0 && <p className="muted">No pending requests.</p>}
      <div className="stack">
        {pending.map((l) => (
          <div className="row-card" key={l.id}>
            <div>
              <strong>{nameOf(l.employeeId)} · {LEAVE_TYPES.find((t) => t.key === l.type).label}</strong>
              <div className="muted small">{fmtDate(l.start)} – {fmtDate(l.end)}{l.note ? " · " + l.note : ""}</div>
            </div>
            <div className="ticket-actions">
              <button className="ghost-btn small" onClick={() => decide(l, true)}><CheckCircle size={13} /> Approve</button>
              <button className="ghost-btn small" onClick={() => decide(l, false)}><XCircle size={13} /> Deny</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Modal({ title, onClose, children }) {
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
        className="modal-card"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h3>{title}</h3>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            <XCircle size={18} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

const GLOBAL_CSS = `
${paletteCss()}

@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500&display=swap');

.scheduler-root {
  --ink: #1C2333;
  --paper: #EEF0EC;
  --paper-raised: #FFFFFF;
  --muted: #5A6158;
  --teal: #2D6A4F;
  --teal-bg: #DCEAE1;
  --brick: #B8433D;
  --brick-bg: #F5DEDC;
  --indigo: #4C5FD5;
  --indigo-bg: #E2E5FA;
  --line: #D8DCD4;
  font-family: 'IBM Plex Sans', sans-serif;
  color: var(--ink);
  background: var(--paper);
  min-height: 100vh;
  min-height: 100dvh;
  width: 100%;
}
.scheduler-root * { box-sizing: border-box; }
.scheduler-root :focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.scheduler-root.dark {
  --ink: #ECEFE9;
  --paper: #14181F;
  --paper-raised: #1E232C;
  --muted: #B4BAAF;
  --teal: #6FD3A1;
  --teal-bg: rgba(111,211,161,0.16);
  --brick: #E58F89;
  --brick-bg: rgba(229,143,137,0.16);
  --indigo: #9AA6F4;
  --indigo-bg: rgba(154,166,244,0.18);
  --line: #2C3340;
}
.theme-toggle { display:flex; align-items:center; justify-content:center; width: 32px; height: 32px; border-radius: 8px; border: 1px solid var(--line); background: var(--paper-raised); color: var(--ink); cursor: pointer; }
.theme-toggle:hover { background: var(--paper); }
.appearance { position: relative; }
.appearance.corner { position: absolute; top: 16px; right: 16px; z-index: 20; }
.appearance-panel { position: absolute; right: 0; top: calc(100% + 8px); z-index: 30; width: 320px; max-width: calc(100vw - 32px); max-height: 80vh; overflow: auto; background: var(--paper-raised); color: var(--ink); border: 1px solid var(--line); border-radius: 12px; padding: 14px; box-shadow: 0 8px 24px rgba(0,0,0,0.18); }
.appearance-title { margin: 0; font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 1rem; }
.appearance-group { border: none; margin: 12px 0 0; padding: 0; min-width: 0; }
.appearance-group legend { padding: 0; margin-bottom: 6px; font-size: 0.72rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
.appearance-option { display: flex; align-items: center; gap: 10px; min-height: 40px; padding: 4px 10px; border: 1px solid var(--line); border-radius: 10px; margin-bottom: 6px; cursor: pointer; font-size: 0.88rem; }
.appearance-option.on, .appearance-mode.on { border-color: var(--primary); background: var(--primary-bg); }
.appearance-option input, .appearance-mode input { accent-color: var(--primary); margin: 0; }
.appearance-option:focus-within, .appearance-mode:focus-within { outline: 2px solid var(--primary); outline-offset: 2px; }
.appearance-dots { display: flex; gap: 2px; }
.appearance-dots i { width: 14px; height: 14px; border-radius: 50%; border: 1px solid var(--line); display: block; }
.appearance-modes { display: flex; gap: 6px; flex-wrap: wrap; }
.appearance-mode { display: flex; align-items: center; gap: 6px; min-height: 40px; padding: 4px 10px; border: 1px solid var(--line); border-radius: 10px; cursor: pointer; font-size: 0.85rem; flex: 1 1 auto; }
@media (max-width: 640px) {
  .appearance-panel { position: fixed; left: 16px; right: 16px; top: 64px; width: auto; max-width: none; }
}
.center-screen { position: relative; }
.center-screen { display:flex; align-items:center; justify-content:center; min-height: max(400px, 100vh); min-height: max(400px, 100dvh); }

.cal { width: 100%; }
.cal-head { display:flex; align-items:center; justify-content:space-between; margin-bottom: 10px; font-family:'Space Grotesk', sans-serif; }
.cal-head strong { font-size: 0.95rem; }
.cal-grid { display:grid; grid-template-columns: repeat(7, 1fr); gap: 4px; }
.cal-dow { margin-bottom: 4px; }
.cal-dow-cell { text-align:center; font-size: 0.68rem; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:0.04em; }
.cal-cell { position:relative; aspect-ratio: 1; border: 1px solid var(--line); background: var(--paper); border-radius: 8px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap: 3px; cursor:pointer; font-family:'IBM Plex Sans'; font-size: 0.8rem; color: var(--ink); }
.cal-cell:hover { border-color: var(--indigo); }
.cal-cell.empty { border: none; background: transparent; cursor: default; }
.cal-cell.selected { background: var(--primary); color: var(--on-primary); border-color: var(--primary); }
.cal-cell.is-today:not(.selected) { border-color: var(--indigo); border-width: 2px; }
.cal-daynum { font-weight: 500; }
.choice-group { border: none; margin: 0 0 12px; padding: 0; min-width: 0; }
.choice-group legend { padding: 0; margin-bottom: 8px; font-size: 0.85rem; font-weight: 600; }
.choice-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.choice { position: relative; display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 56px; padding: 8px 12px; border: 1px solid var(--line); border-radius: 12px; background: var(--paper-raised); color: var(--ink); font-weight: 600; cursor: pointer; }
.choice input { position: absolute; opacity: 0; inset: 0; margin: 0; cursor: pointer; }
.choice.on { border-color: var(--primary); background: var(--primary-bg); }
.choice:has(input:focus-visible) { outline: 2px solid var(--primary); outline-offset: 2px; }
.choice-mark { font-weight: 700; }
.choice-mark.ok { color: var(--teal); }
.choice-mark.no { color: var(--brick); }
.cal-mark { font-size: 0.72rem; font-weight: 700; line-height: 1; }
.cal-mark.ok { color: var(--teal); }
.cal-mark.no { color: var(--brick); }
.cal-cell.selected .cal-mark { color: inherit; }
.loader { font-family:'IBM Plex Mono', monospace; letter-spacing: 0.05em; color: var(--ink); }

h1,h2,h3 { font-family: 'Space Grotesk', sans-serif; margin: 0 0 4px; }
h2 { font-size: 1.3rem; }
h3.section-label { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin: 24px 0 10px; }
.muted { color: var(--muted); }
.small { font-size: 0.82rem; }
.tight { gap: 4px !important; }

.brand { display:flex; align-items:center; gap:10px; }
.brand-mark { font-family:'Space Grotesk', sans-serif; font-weight:700; background: var(--primary); color: var(--on-primary); border-radius: 6px; padding: 4px 9px; font-size: 0.85rem; letter-spacing: 0.03em; }
.brand-mark.big { display: inline-block; margin-bottom: 10px; font-size: 1.4rem; padding: 10px 16px; border-radius: 10px; }
.brand-name { font-family:'Space Grotesk', sans-serif; font-weight:700; font-size: 1.1rem; }

.topbar { display:flex; justify-content:space-between; align-items:center; padding: 14px 20px; border-bottom: 1px solid var(--line); background: var(--paper-raised); flex-wrap: wrap; gap: 10px; }
.topbar-right { display:flex; align-items:center; gap: 12px; flex-wrap: wrap; min-width: 0; max-width: 100%; }
.who { display:flex; align-items:center; gap:6px; font-weight:600; font-size:0.9rem; }

.tabbar { display:flex; gap: 4px; padding: 10px 16px; overflow-x:auto; background: var(--paper-raised); border-bottom: 1px solid var(--line); }
.tab { display:flex; align-items:center; gap:6px; padding: 8px 14px; border-radius: 8px; border:none; background:transparent; color: var(--muted); font-family:'IBM Plex Sans'; font-weight:500; font-size:0.85rem; cursor:pointer; white-space:nowrap; position:relative; }
.tab:hover { background: var(--paper); }
.tab-active { background: var(--primary); color: var(--on-primary); }
.badge { background: var(--brick); color:white; font-size:0.65rem; padding: 1px 6px; border-radius: 10px; margin-left: 2px; }

.content { max-width: 760px; margin: 0 auto; padding: 24px 18px 60px; }
.content:has(.approval-panel) { max-width: 980px; }
.panel-head { display:flex; justify-content:space-between; align-items:center; }
.approval-tech { margin: 4px 0 8px; }
.approval-tech summary { cursor: pointer; font-size: 0.8rem; color: var(--muted); }
.approval-sample { display:flex; flex-direction:column; gap:4px; font-size:0.8rem; font-weight:600; min-width: 220px; max-width: 100%; }
.approval-sample select { max-width: 100%; text-overflow: ellipsis; }
.approval-source-controls { display:flex; flex-direction:column; gap:8px; align-items:flex-end; }
.approval-meta-row { display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin-bottom: 10px; }
.approval-dl { display:grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px 16px; margin: 0; }
.approval-dl dt { font-size: 0.72rem; font-weight:600; text-transform:uppercase; letter-spacing:0.06em; color:var(--muted); }
.approval-dl dd { margin: 2px 0 0; font-size: 0.88rem; }
.approval-dl code { font-family:'IBM Plex Mono', monospace; font-size: 0.78rem; }
.approval-banner { margin-top: 12px; padding: 10px 12px; border-radius: 8px; background: var(--brick-bg); border: 1px solid var(--brick); color: var(--ink); font-size: 0.88rem; }
.approval-banner.soft { background: var(--indigo-bg); border-color: var(--indigo); }
.approval-list { margin: 0; padding-left: 1.1rem; display:flex; flex-direction:column; gap: 6px; font-size: 0.88rem; }
.approval-grid-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.approval-grid { width: 100%; border-collapse: collapse; font-size: 0.78rem; min-width: 640px; }
.approval-grid th, .approval-grid td { border: 1px solid var(--line); padding: 8px 6px; vertical-align: top; text-align: left; }
.approval-cell-btn { display: block; width: 100%; min-height: 44px; padding: 0; border: none; background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; border-radius: 6px; }
.approval-cell-btn:hover { background: var(--primary-bg); }
.day-detail-sub { margin: 0; }
.day-detail-count { margin: 0 0 8px; }
.day-detail-list { list-style: none; margin: 0 0 14px; padding: 0; display: grid; gap: 6px; }
.day-detail-list li { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; background: var(--paper); }
.day-detail-list code { font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; padding: 2px 8px; border-radius: 6px; background: var(--primary-bg); color: var(--primary); }
.modal-card.day-detail { max-width: 420px; max-height: 85vh; overflow: auto; }
.approval-grid th { background: var(--paper); font-weight: 600; }
.approval-nurses { font-family:'IBM Plex Mono', monospace; font-size: 0.72rem; word-break: break-word; }
.approval-gap-tag { margin-top: 4px; font-size: 0.7rem; font-weight: 600; color: var(--brick); }
.approval-ack { display:flex; align-items:flex-start; gap: 8px; font-size: 0.88rem; font-weight: 500; }
.approval-ack input { width: auto; margin-top: 3px; }
.approval-error { color: var(--brick); font-size: 0.88rem; margin: 0; }
.approval-modal { max-width: 440px; }
.approval-block { margin-bottom: 10px; }
.approval-run { margin-bottom: 14px; display:flex; flex-direction:column; gap: 8px; }
.approval-run-row { display:flex; flex-wrap:wrap; align-items:flex-end; gap: 10px; }
.approval-run-row .approval-sample { min-width: 140px; }
.approval-run-row .approval-sample input { font-weight: 500; }

.card { background: var(--paper-raised); border: 1px solid var(--line); border-radius: 12px; padding: 16px; margin-bottom: 12px; }
.form-card { display:flex; flex-direction:column; gap: 12px; }
.form-row { display:flex; gap: 12px; flex-wrap: wrap; }
.form-row label, .modal-body label { flex:1; min-width: 140px; display:flex; flex-direction:column; gap:4px; font-size: 0.8rem; font-weight:600; color: var(--muted); }
.modal-body label { margin-bottom: 12px; }
.modal-body select, .modal-body input:not([type=radio]) { min-height: 44px; }
.modal-body .choice { flex-direction: row; flex: none; min-width: 0; margin-bottom: 0; font-size: 0.95rem; color: var(--ink); }

input, select { font-family:'IBM Plex Sans'; padding: 9px 10px; border-radius: 8px; border: 1px solid var(--line); background: var(--paper); font-size: 0.9rem; color: var(--ink); }
input:focus, select:focus { outline: 2px solid var(--indigo); outline-offset: 1px; }

.primary-btn { display:flex; align-items:center; gap:6px; justify-content:center; background: var(--primary); color: var(--on-primary); border:none; padding: 10px 16px; border-radius: 8px; font-weight:600; font-size:0.85rem; cursor:pointer; align-self:flex-start; }
.primary-btn:disabled { opacity: 0.4; cursor:not-allowed; }
.primary-btn:hover:not(:disabled) { background: color-mix(in srgb, var(--primary), var(--ink) 18%); }
.ghost-btn { display:flex; align-items:center; gap:6px; background:transparent; border: 1px solid var(--line); padding: 8px 12px; border-radius: 8px; font-size:0.82rem; font-weight:500; cursor:pointer; color: var(--ink); }
.ghost-btn:hover { background: var(--paper); }
.ghost-btn.small { padding: 5px 9px; font-size: 0.75rem; }
.icon-btn { background:transparent; border:none; cursor:pointer; color: var(--muted); padding: 6px; border-radius: 6px; }
.icon-btn:hover { background: var(--paper); color: var(--brick); }

.scheduler-root button, .scheduler-root input, .scheduler-root select, .scheduler-root textarea { font-family: inherit; }
.subtabs { display:flex; gap: 6px; padding: 8px 16px; overflow-x:auto; background: var(--paper-raised); border-bottom: 1px solid var(--line); }
.subtab { min-height: 36px; padding: 6px 14px; border-radius: 999px; border: 1px solid var(--line); background: transparent; color: var(--ink); font-family:'IBM Plex Sans'; font-size: 0.85rem; font-weight: 500; cursor: pointer; white-space: nowrap; }
.subtab.on { background: var(--primary-bg); border-color: var(--primary); color: var(--primary); font-weight: 600; }
.home h2 { margin: 0 0 14px; }
.home-date { margin: 0 0 2px; }
.home-next { background: var(--primary-bg); border-radius: 14px; padding: 16px 18px; }
.home-next-label { margin: 0; font-size: 0.78rem; color: var(--primary); font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
.home-next-main { margin: 2px 0 0; font-family:'Space Grotesk', sans-serif; font-weight: 700; font-size: 1.3rem; color: var(--primary); }
.home-next-sub { margin: 4px 0 0; font-size: 0.88rem; color: var(--ink); }
.home-week { list-style: none; margin: 0 0 8px; padding: 0; display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; }
.home-day { display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 8px 0; border: 1px solid var(--line); border-radius: 10px; font-size: 0.72rem; color: var(--muted); background: var(--paper-raised); }
.home-day.work { background: var(--primary); border-color: var(--primary); color: var(--on-primary); font-weight: 600; }
.home-day.today { outline: 2px solid var(--ink); outline-offset: 2px; }
.home-day-num { font-size: 1rem; font-family:'Space Grotesk', sans-serif; font-weight: 700; }
.home-actions { display: grid; gap: 8px; }
.home-action { display: flex; align-items: center; gap: 12px; min-height: 56px; padding: 0 16px; border: 1px solid var(--line); border-radius: 12px; background: var(--paper-raised); color: var(--ink); font-family:'IBM Plex Sans'; font-size: 1rem; font-weight: 500; text-align: left; cursor: pointer; }
.home-action span { flex: 1; }
.home-action:hover { border-color: var(--primary); background: var(--primary-bg); }
.home-need { display: flex; align-items: flex-start; gap: 12px; min-width: 0; }
.home-need-sub { display: block; }
.home-alerts { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.link-btn { background: none; border: none; padding: 0; min-height: 0; color: var(--primary); font-weight: 600; text-decoration: underline; cursor: pointer; font-size: inherit; }
.home-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; margin-bottom: 4px; }
.home-stat { display: flex; flex-direction: column; gap: 2px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; background: var(--paper-raised); }
.home-stat strong { font-family: 'Space Grotesk', sans-serif; font-size: 1.3rem; }
.home-attn { display: flex; align-items: center; gap: 8px; color: var(--warm); font-weight: 500; }
@media (max-width: 640px) {
  .tabbar-bottom { position: fixed; left: 0; right: 0; bottom: 0; z-index: 25; justify-content: space-around; gap: 0; padding: 6px 4px calc(6px + env(safe-area-inset-bottom)); border-top: 1px solid var(--line); border-bottom: none; }
  .tabbar-bottom .tab { flex: 1; flex-direction: column; gap: 2px; font-size: 0.72rem; min-height: 52px; padding: 6px 4px; justify-content: center; }
  .scheduler-root:has(.tabbar-bottom) .content { padding-bottom: 96px; }
}
.stack { display:flex; flex-direction:column; gap: 8px; }
.row-card { display:flex; justify-content:space-between; align-items:center; background: var(--paper-raised); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; gap: 10px; flex-wrap: wrap; }
.row-card.unread { border-left: 3px solid var(--indigo); }
.row-card.ticket { border-style: dashed; }
.ticket-actions { display:flex; align-items:center; gap: 8px; flex-wrap: wrap; }
@media (max-width: 640px) {
  .approval-source-controls { align-items: stretch; width: 100%; min-width: 0; }
  .approval-sample { min-width: 0; width: 100%; }
  .approval-run-row .approval-sample { min-width: 0; width: auto; flex: 1 1 140px; }
  .icon-btn, .theme-toggle, .ghost-btn.small { min-width: 40px; min-height: 40px; }
  .theme-toggle { width: 40px; height: 40px; }
  .ghost-btn, .primary-btn, .tab { min-height: 40px; }
}
.mini-row { display:flex; justify-content:space-between; padding: 4px 0; border-bottom: 1px dotted var(--line); }

.stamp { font-family:'IBM Plex Mono', monospace; font-size: 0.68rem; font-weight:600; letter-spacing: 0.06em; text-transform: uppercase; padding: 3px 9px; border-radius: 4px; display:inline-block; transform: rotate(-1.5deg); border: 1px solid currentColor; }

.login-card { background: var(--paper-raised); border: 1px solid var(--line); border-radius: 16px; padding: 32px; width: 100%; max-width: 380px; text-align:center; }
.roster-list { display:flex; flex-direction:column; gap:8px; margin: 20px 0; text-align:left; }
.roster-item { display:flex; justify-content:space-between; align-items:center; padding: 10px 14px; border-radius: 9px; border: 1px solid var(--line); background: var(--paper); color: var(--ink); cursor:pointer; font-weight:500; }
.roster-item:hover { border-color: var(--indigo); }
.add-row { display:flex; gap:8px; }
.add-row input { flex:1; }

.modal-backdrop { position:fixed; inset:0; background: rgba(28,35,51,0.45); display:flex; align-items:center; justify-content:center; z-index:50; padding: 16px; }
.modal-card { background: var(--paper-raised); border-radius: 14px; padding: 20px; width: 100%; max-width: 380px; }
.modal-head { display:flex; justify-content:space-between; align-items:center; margin-bottom: 10px; }

.toast { position:fixed; bottom: 20px; left:50%; transform: translateX(-50%); background: var(--ink); color: var(--paper); padding: 10px 18px; border-radius: 8px; font-size: 0.85rem; z-index: 60; }
.saving-dot { position:fixed; top: 14px; right: 14px; width: 8px; height: 8px; border-radius: 50%; background: var(--indigo); opacity: 0.6; }
`;
