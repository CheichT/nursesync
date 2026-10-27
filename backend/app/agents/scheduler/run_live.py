"""Run the real Scheduler on a scenario, with the stand-in hint writer. Costs a few cents per round.

Usage: cd backend && ../.venv/bin/python -m app.agents.scheduler.run_live [mock|case_04|case_05|case_06]
"""

import sys

from app.agents.scheduler.agent import AnthropicScheduler
from app.harness.phase1 import format_report, load_inputs, load_scenario, run_phase1
from app.harness.stand_ins import HintingRulesChecker


def main(name: str = "mock") -> int:
    inputs = load_inputs() if name == "mock" else load_scenario(name)[0]
    scheduler = AnthropicScheduler()
    result = run_phase1(scheduler, HintingRulesChecker(), inputs)
    print(format_report(result))
    for call in scheduler.calls:
        print(f"Round {call['version']}: stop_reason={call['stop_reason']} output_tokens={call['output_tokens']}")
    return 0 if result.outcome == "passed" else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))
