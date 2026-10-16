import os
import time
from datetime import date

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

import erp

load_dotenv()  # reads the .env file in this folder and loads its values into the environment

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")  # change the model in .env, not here

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise SystemExit("GEMINI_API_KEY not found. Check that your .env file is in this folder and has the line GEMINI_API_KEY=your-key")

client = genai.Client(api_key=API_KEY)

# Shared state for the current call. Fine for this one-call-at-a-time text
# agent; the LiveKit version keeps it per call in `userdata` instead.
session = {"customer_id": None, "outcome": "no_resolution"}


# ======================================================================
# TOOLS: the database work lives in erp.py. These wrappers pass in the
# customer from `session` (never from the model) and record the outcome.
# ======================================================================
def record(outcome, result):
    """Set the call outcome only when the tool actually succeeded."""
    if result.get("ok"):
        session["outcome"] = outcome
    return result


def get_open_invoices():
    return erp.get_open_invoices(session["customer_id"])


def log_promise_to_pay(invoice_id, promised_date):
    return record("promise_to_pay",
                  erp.log_promise_to_pay(session["customer_id"], invoice_id, promised_date))


def raise_dispute(invoice_id, reason):
    return record("dispute", erp.raise_dispute(session["customer_id"], invoice_id, reason))


def escalate_to_human(reason):
    return record("escalated", erp.escalate_to_human(session["customer_id"], reason))


# ======================================================================
# TOOL DESCRIPTIONS: what the model actually sees
# ======================================================================
TOOLS = types.Tool(function_declarations=[
    {
        "name": "get_open_invoices",
        "description": "List the unpaid (pending or overdue) invoices for the customer on this call. Call this before discussing any amounts or dates.",
    },
    {
        "name": "log_promise_to_pay",
        "description": "Record that the customer has promised to pay a specific invoice by a specific date. Only use after the customer has clearly stated a date.",
        "parameters": {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "integer", "description": "ID of the invoice"},
                "promised_date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
            },
            "required": ["invoice_id", "promised_date"],
        },
    },
    {
        "name": "raise_dispute",
        "description": "Record that the customer disputes an invoice (wrong amount, goods not received, already paid, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "integer"},
                "reason": {"type": "string", "description": "The customer's reason, in a short sentence"},
            },
            "required": ["invoice_id", "reason"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": "Hand the call to a human. Use for legal threats, abusive language, hardship requests, or anything you cannot handle.",
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
])

TOOL_FUNCTIONS = {
    "get_open_invoices": get_open_invoices,
    "log_promise_to_pay": log_promise_to_pay,
    "raise_dispute": raise_dispute,
    "escalate_to_human": escalate_to_human,
}


def run_tool(name, args):
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return {"error": f"unknown tool {name}"}
    try:
        return func(**args)  # **args unpacks {"invoice_id": 3} into invoice_id=3
    except Exception as e:
        return {"error": str(e)}


# ======================================================================
# SMALL HELPERS
# ======================================================================
def clean_args(args):
    """Gemini sometimes sends 3.0 instead of 3. Turn whole floats back into ints."""
    return {k: int(v) if isinstance(v, float) and v.is_integer() else v
            for k, v in args.items()}


def user_msg(text):
    return types.Content(role="user", parts=[types.Part(text=text)])


# ======================================================================
# SYSTEM PROMPT
# ======================================================================
def build_system_prompt(customer_name):
    return f"""You are a polite, professional accounts-receivable assistant calling on behalf of a supplier.
Today's date is {date.today().isoformat()}. You are speaking with a representative of {customer_name}.

Your goal: find out when overdue or pending invoices will be paid.

Rules:
- Always call get_open_invoices before mentioning any amount, invoice number, or due date. Never guess these.
- Be courteous and brief. Never threaten, pressure, or mention legal action.
- If the customer commits to a payment date, confirm it back to them, then call log_promise_to_pay.
- If the customer says an invoice is wrong, already paid, or goods weren't received, call raise_dispute.
- If the customer is abusive, mentions lawyers, or reports financial hardship, call escalate_to_human.
- Only record a promise when the customer states a specific date. If they are vague, politely ask for one.
- Once an outcome is recorded, thank them and end the conversation.
"""


# ======================================================================
# THE AGENT LOOP
# ======================================================================
def generate_with_retry(contents, config, tries=5):
    """Call Gemini. If the server is busy (503) or rate-limited (429), wait and try again."""
    for attempt in range(tries):
        try:
            return client.models.generate_content(
                model=MODEL, contents=contents, config=config
            )
        except errors.APIError as e:
            temporary = e.code in (429, 500, 503, 504)
            if not temporary or attempt == tries - 1:
                raise  # a real error (or out of attempts): let it crash so you can see it
            wait = 2 ** attempt * 2  # 2s, 4s, 8s, 16s
            print(f"   [retry] Gemini error {e.code}, waiting {wait}s (attempt {attempt + 1}/{tries})...")
            time.sleep(wait)


def agent_turn(contents, system_prompt):
    """Send the conversation to the model. Keep running tools until it replies with plain text."""
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[TOOLS],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    while True:
        response = generate_with_retry(contents, config)
        # Append the model's reply exactly as returned (keeps hidden "thought" data intact)
        contents.append(response.candidates[0].content)

        calls = response.function_calls
        if not calls:
            return response.text or ""

        parts = []
        for call in calls:
            args = clean_args(dict(call.args or {}))
            result = run_tool(call.name, args)
            print(f"   [tool] {call.name}({args}) -> {result}")
            parts.append(
                types.Part.from_function_response(
                    name=call.name, response={"result": result}
                )
            )
        contents.append(types.Content(role="user", parts=parts))


# ======================================================================
# LOGGING + TERMINAL LOOP (you play the customer)
# ======================================================================
def log_call(transcript):
    erp.log_call(session["customer_id"], session["outcome"], transcript)


def main():
    rows = erp.list_customers_with_open_invoices()

    print("Customers with open invoices:")
    for r in rows:
        print(f"  {r['id']:>2}  {r['name']}  ({r['open_count']} open)")

    chosen = int(input("\nWhich customer id are you playing? "))
    name = next(r["name"] for r in rows if r["id"] == chosen)

    session["customer_id"] = chosen
    session["outcome"] = "no_resolution"

    system_prompt = build_system_prompt(name)
    contents = [user_msg("(The call connects. The customer says hello.)")]
    transcript = []

    agent_reply = agent_turn(contents, system_prompt)
    print(f"\nAgent: {agent_reply}")
    transcript.append(f"Agent: {agent_reply}")

    while True:
        said = input("\nYou: ").strip()
        if said.lower() in ("quit", "exit", "bye"):
            break
        transcript.append(f"Customer: {said}")
        contents.append(user_msg(said))
        agent_reply = agent_turn(contents, system_prompt)
        print(f"\nAgent: {agent_reply}")
        transcript.append(f"Agent: {agent_reply}")

    log_call(transcript)
    print(f"\nCall logged. Outcome: {session['outcome']}")


if __name__ == "__main__":
    main()