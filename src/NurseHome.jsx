import { Calendar, Repeat, Send, ChevronRight, Bell } from "lucide-react";

const pad2 = (n) => String(n).padStart(2, "0");
const keyOf = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
const addDays = (d, n) => {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
};
const longDay = (d) => d.toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" });

/** A short, friendly day name: Today, Tomorrow, or Wed, Oct 28. */
function whenLabel(date, now) {
  const key = keyOf(date);
  if (key === keyOf(now)) return "Today";
  if (key === keyOf(addDays(now, 1))) return "Tomorrow";
  return date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

/** The nurse's home screen: next shift, this week, three main actions, and what needs attention. */
export default function NurseHome({ data, currentUser, goTo, unreadAlerts }) {
  const now = new Date();
  const todayKey = keyOf(now);
  const first = currentUser.name.trim().split(/\s+/)[0] || currentUser.name;
  const mine = data.shifts.filter((s) => s.employeeId === currentUser.id && !s.open);

  const upcoming = mine
    .filter((s) => s.date >= todayKey)
    .sort((a, b) => `${a.date}${a.start}`.localeCompare(`${b.date}${b.start}`));
  const next = upcoming[0];

  const sunday = addDays(now, -now.getDay());
  const week = Array.from({ length: 7 }, (_, i) => addDays(sunday, i));

  let dayOff = null;
  for (let i = 0; i < 14; i += 1) {
    const d = addDays(now, i);
    const marked = data.availability?.[currentUser.id]?.[keyOf(d)]?.status === "unavailable"; // a day you can't work is not a day off
    if (!mine.some((s) => s.date === keyOf(d)) && !marked) {
      dayOff = whenLabel(d, now);
      break;
    }
  }

  const incomingSwaps = data.swaps.filter((s) => s.toId === currentUser.id && s.status === "pending").length;
  const pendingLeave = data.leave.filter((l) => l.employeeId === currentUser.id && l.status === "pending").length;
  const needsResched = mine.filter((s) => s.status === "conflict").length;

  const items = [];
  if (incomingSwaps) {
    items.push({ key: "swaps", text: `${incomingSwaps} swap request${incomingSwaps > 1 ? "s" : ""} waiting for you`, to: "swaps", cta: "View" });
  }
  if (needsResched) {
    items.push({ key: "resched", text: `${needsResched} of your shifts need${needsResched > 1 ? "" : "s"} rescheduling`, to: "shifts", cta: "View" });
  }
  if (pendingLeave) {
    items.push({ key: "leave", text: `${pendingLeave} time-off request${pendingLeave > 1 ? "s" : ""} waiting for approval`, to: "leave", cta: "View" });
  }
  if (unreadAlerts) {
    items.push({ key: "alerts", text: `${unreadAlerts} unread alert${unreadAlerts > 1 ? "s" : ""}`, to: "notifications", cta: "Open" });
  }

  return (
    <div className="panel home">
      <p className="muted small home-date">{longDay(now)}</p>
      <h2>Hi {first}</h2>

      <section className="home-next" aria-label="Your next shift">
        {next ? (
          <>
            <p className="home-next-label">Your next shift</p>
            <p className="home-next-main">
              {whenLabel(new Date(`${next.date}T00:00:00`), now)}, {next.start} to {next.end}
            </p>
            {next.status === "conflict" && <p className="home-next-sub">This shift needs rescheduling. Your manager has been told.</p>}
          </>
        ) : (
          <>
            <p className="home-next-label">Your next shift</p>
            <p className="home-next-main">Nothing scheduled yet</p>
            <p className="home-next-sub">Your manager will add shifts here once the schedule is ready.</p>
          </>
        )}
      </section>

      <h3 className="section-label">This week</h3>
      <ul className="home-week" aria-label="This week">
        {week.map((d) => {
          const key = keyOf(d);
          const shifts = mine.filter((s) => s.date === key).sort((a, b) => a.start.localeCompare(b.start));
          const working = shifts.length > 0;
          const label = `${longDay(d)}: ${working ? `working ${shifts.map((s) => `${s.start} to ${s.end}`).join(", ")}` : "off"}`;
          return (
            <li key={key} className={`home-day ${working ? "work" : ""} ${key === todayKey ? "today" : ""}`} aria-label={label} aria-current={key === todayKey ? "date" : undefined}>
              <span className="home-day-name" aria-hidden="true">{d.toLocaleDateString("en-US", { weekday: "narrow" })}</span>
              <span className="home-day-num" aria-hidden="true">{d.getDate()}</span>
              <span className="home-day-state" aria-hidden="true">{working ? "Work" : "Off"}</span>
            </li>
          );
        })}
      </ul>
      <p className="muted small">{dayOff ? `Next day off: ${dayOff.toLowerCase() === "today" || dayOff.toLowerCase() === "tomorrow" ? dayOff.toLowerCase() : dayOff}` : "No day off in the next two weeks."}</p>

      <h3 className="section-label">What do you want to do?</h3>
      <div className="home-actions">
        <button type="button" className="home-action" onClick={() => goTo("availability")}>
          <Calendar size={20} aria-hidden="true" />
          <span>Mark availability</span>
          <ChevronRight size={16} aria-hidden="true" />
        </button>
        <button type="button" className="home-action" onClick={() => goTo("shifts")}>
          <Repeat size={20} aria-hidden="true" />
          <span>Swap or give away a shift</span>
          <ChevronRight size={16} aria-hidden="true" />
        </button>
        <button type="button" className="home-action" onClick={() => goTo("leave")}>
          <Send size={20} aria-hidden="true" />
          <span>Request time off</span>
          <ChevronRight size={16} aria-hidden="true" />
        </button>
      </div>

      <h3 className="section-label">Needs your attention</h3>
      {items.length === 0 ? (
        <p className="muted">You're all caught up.</p>
      ) : (
        <div className="stack">
          {items.map((it) => (
            <div className="row-card" key={it.key}>
              <span className="home-attn"><Bell size={16} aria-hidden="true" /> {it.text}</span>
              <button type="button" className="ghost-btn small" onClick={() => goTo(it.to)}>{it.cta}</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
