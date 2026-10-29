import { useEffect, useState } from "react";
import { Bell, ClipboardCheck, Repeat, Send, CalendarX, Sparkles, PhoneOff, ChevronRight } from "lucide-react";
import { checkHealth, listCases, getUsage } from "./caseApi";

const pad2 = (n) => String(n).padStart(2, "0");
const keyOf = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

/** The manager's home screen: what needs a decision now, a few numbers, and the two big actions. */
export default function ManagerHome({ data, goTo, unreadAlerts }) {
  const [ai, setAi] = useState({ state: "loading", waiting: 0, stopped: 0, left: null, cap: null });

  useEffect(() => {
    let alive = true;
    (async () => {
      const health = await checkHealth();
      if (!health.ok) {
        if (alive) setAi({ state: "offline", waiting: 0, stopped: 0, left: null, cap: null });
        return;
      }
      try {
        const [list, usage] = await Promise.all([listCases(), getUsage().catch(() => null)]);
        const waiting = (list.cases || []).filter((c) => c.status === "waiting_approval");
        if (alive) {
          setAi({
            state: "ready",
            waiting: waiting.filter((c) => c.outcome !== "stopped_missing_input").length,
            stopped: waiting.filter((c) => c.outcome === "stopped_missing_input").length,
            left: usage?.capped ? usage.remaining : null,
            cap: usage?.capped ? usage.max_per_day : null,
          });
        }
      } catch {
        if (alive) setAi({ state: "offline", waiting: 0, stopped: 0, left: null, cap: null });
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const swaps = data.swaps.filter((s) => s.status === "accepted").length;
  const leave = data.leave.filter((l) => l.status === "pending").length;
  const conflicts = data.shifts.filter((s) => s.status === "conflict").length;
  const openShifts = data.shifts.filter((s) => s.open).length;

  const now = new Date();
  const sunday = new Date(now);
  sunday.setDate(now.getDate() - now.getDay());
  const saturday = new Date(sunday);
  saturday.setDate(sunday.getDate() + 6);
  const thisWeek = data.shifts.filter((s) => !s.open && s.date >= keyOf(sunday) && s.date <= keyOf(saturday)).length;
  const weekLabel = `${sunday.toLocaleDateString("en-US", { month: "short", day: "numeric" })} to ${saturday.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;

  const items = [];
  if (ai.waiting) {
    items.push({ key: "draft", icon: Sparkles, title: ai.waiting === 1 ? "An AI draft is ready to approve" : `${ai.waiting} AI drafts are ready to approve`, sub: "Review it, then approve, change demand, or reject.", cta: "Review draft", to: "approve" });
  }
  if (ai.stopped) {
    items.push({ key: "stopped", icon: ClipboardCheck, title: `${plural(ai.stopped, "AI run", "AI runs")} stopped for missing data`, sub: "Nothing was guessed. Open it to see what is missing.", cta: "Open", to: "approve" });
  }
  if (leave) {
    items.push({ key: "leave", icon: Send, title: plural(leave, "time-off request", "time-off requests"), sub: "Waiting for your approval.", cta: "Review", to: "leaveapprovals" });
  }
  if (swaps) {
    items.push({ key: "swaps", icon: Repeat, title: plural(swaps, "swap request", "swap requests"), sub: "Accepted by a coworker, waiting for you.", cta: "Review", to: "swapapprovals" });
  }
  if (conflicts) {
    items.push({ key: "conflicts", icon: CalendarX, title: `${plural(conflicts, "shift needs", "shifts need")} rescheduling`, sub: "A nurse flagged a problem.", cta: "Open", to: "builder" });
  }

  return (
    <div className="panel home">
      <p className="muted small home-date">Week of {weekLabel}</p>
      <h2>{items.length ? (items.length === 1 ? "1 thing needs you" : `${items.length} things need you`) : "You're all caught up"}</h2>

      {items.length > 0 && (
        <div className="stack">
          {items.map((it) => {
            const Icon = it.icon;
            return (
              <div className="row-card" key={it.key}>
                <span className="home-need">
                  <Icon size={20} aria-hidden="true" />
                  <span>
                    <strong>{it.title}</strong>
                    <span className="muted small home-need-sub">{it.sub}</span>
                  </span>
                </span>
                <button type="button" className="ghost-btn" onClick={() => goTo(it.to)}>{it.cta}</button>
              </div>
            );
          })}
        </div>
      )}

      {unreadAlerts > 0 && (
        <p className="muted small home-alerts">
          <Bell size={14} aria-hidden="true" /> {plural(unreadAlerts, "unread alert", "unread alerts")}.{" "}
          <button type="button" className="link-btn" onClick={() => goTo("notifications")}>Open alerts</button>
        </p>
      )}

      {ai.state === "offline" && (
        <p className="muted small">AI drafts are not shown because the case API is not running. Everything else on this page still works.</p>
      )}
      {ai.state === "ready" && ai.waiting === 0 && ai.stopped === 0 && (
        <p className="muted small">No AI draft is waiting for approval.</p>
      )}

      <h3 className="section-label">This week at a glance</h3>
      <div className="home-stats">
        <div className="home-stat"><span className="muted small">Shifts scheduled</span><strong>{thisWeek}</strong></div>
        <div className="home-stat"><span className="muted small">Open shifts</span><strong>{openShifts}</strong></div>
        <div className="home-stat">
          <span className="muted small">AI runs left today</span>
          <strong>{ai.left == null ? "n/a" : `${ai.left} of ${ai.cap}`}</strong>
        </div>
      </div>

      <h3 className="section-label">Quick actions</h3>
      <div className="home-actions">
        <button type="button" className="home-action" onClick={() => goTo("approve")}>
          <Sparkles size={20} aria-hidden="true" />
          <span>Build next week with AI</span>
          <ChevronRight size={16} aria-hidden="true" />
        </button>
        <button type="button" className="home-action" onClick={() => goTo("approve")}>
          <PhoneOff size={20} aria-hidden="true" />
          <span>Report a call-out</span>
          <ChevronRight size={16} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
