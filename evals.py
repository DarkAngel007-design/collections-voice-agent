"""Scripted test scenarios: a tiny evaluation harness.

Each scenario is a list of customer lines plus the outcome we expect.
The database is re-seeded before every scenario so they don't affect each other.
Run with:  python evals.py
"""
import subprocess
import sys
import time
from datetime import date, timedelta

import agent
import erp

future = (date.today() + timedelta(days=10)).isoformat()

SCENARIOS = [
    {
        "name": "promise to pay",
        "lines": ["Hello, go ahead.", f"We will pay all of it on {future}."],
        "expected": "promise_to_pay",
    },
    {
        "name": "dispute",
        "lines": ["Hello.", "We never received the goods for the first invoice, so we dispute it."],
        "expected": "dispute",
    },
    {
        "name": "escalation",
        "lines": ["Hello.", "Stop calling me. I'm talking to my lawyer."],
        "expected": "escalated",
    },
    {
        "name": "vague answer",
        "lines": ["Hello.", "We'll pay soon, probably."],
        "expected": "no_resolution",
    },
]


def first_customer_with_open_invoices():
    first = erp.list_customers_with_open_invoices()[0]
    return first["id"], first["name"]


def run_scenario(scenario):
    subprocess.run([sys.executable, "seed.py"], check=True, capture_output=True)

    customer_id, name = first_customer_with_open_invoices()
    agent.session["customer_id"] = customer_id
    agent.session["outcome"] = "no_resolution"

    system_prompt = agent.build_system_prompt(name)
    contents = [agent.user_msg("(The call connects. The customer says hello.)")]
    transcript = [f"Agent: {agent.agent_turn(contents, system_prompt)}"]

    for line in scenario["lines"]:
        transcript.append(f"Customer: {line}")
        contents.append(agent.user_msg(line))
        transcript.append(f"Agent: {agent.agent_turn(contents, system_prompt)}")
        time.sleep(1)  # be gentle with free-tier rate limits

    agent.log_call(transcript)
    return agent.session["outcome"]


def main():
    passed = 0
    for sc in SCENARIOS:
        print(f"\n--- {sc['name']} ---")
        actual = run_scenario(sc)
        ok = actual == sc["expected"]
        passed += ok
        print(f"expected={sc['expected']}  actual={actual}  {'PASS' if ok else 'FAIL'}")
    print(f"\n{passed}/{len(SCENARIOS)} scenarios passed")


if __name__ == "__main__":
    main()