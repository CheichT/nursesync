# NurseSync

A team of 4 AI agents that drafts a hospital unit's weekly nurse schedule and checks it against the rules, so the manager reviews and approves instead of building it by hand.

**Owners:** Cheich Toure and Kerrian Gordon
**Status:** design phase. The PRD, workflow diagram and build plan are done. The agents are not built yet.

![NurseSync multi-agent workflow](nursesync_multi_agent_architecture.png)

## The problem

Nurse managers spend hours every week building schedules by hand. Staffing needs change daily, availability and time-off requests live in different places, and rules like rest time and overtime are easy to miss. Rule violations are often found only after the schedule is posted.

## The idea

Four AI agents do the heavy lifting, and the manager stays in charge.

## How the workflow runs

1. **Demand agent:** works out how many nurses each shift needs.
2. **Availability agent:** collects who can work and who has approved time off. Steps 1 and 2 run at the same time.
3. **Scheduler agent:** builds a draft schedule from both.
4. **Rules Checker agent:** reviews the draft against rest-time, overtime and skill rules. A failing draft goes back to the Scheduler. After 3 failed tries, it goes to the manager marked "Needs manual review."
5. **Nurse manager (human):** reviews and approves. Nothing goes out until a person says yes.

## Why more than one agent

A scheduler can't reliably check its own work. A separate Rules Checker catches mistakes the Scheduler can't see, such as a nurse scheduled with no rest between shifts. Demand and Availability are independent, so they run in parallel. When something goes wrong, it's easy to see which agent caused it.

## Design principles

- **Agents propose, people decide.** Only the manager's approval makes a schedule official.
- **Read-only tools.** The agents read data and create proposals. They never change the live schedule.
- **Uncertain results go to a human.** Missing data is listed as "Needs manual review," never guessed.
- **Mock data only.** No real patient or staff data.

## What's in this repo

- [PRD (PDF)](NurseSync%20PRD%20-%20Cheich%20Toure%20and%20Kerrian%20Gordon.pdf): problem, users, solution, tools, system prompt, risks and eval cases.
- [Architecture diagram (SVG)](nursesync_multi_agent_architecture.svg): the agents, handoffs and shared state.
- The Shift Board scheduling prototype (React + Vite), which NurseSync is being built on. Its login is pick-a-name with no real authentication, and it is not secure.

## Next

Build the rules and tools first, then the agents, then the manager approval screen.
