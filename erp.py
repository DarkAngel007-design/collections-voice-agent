"""Mock ERP: plain database functions with no LLM code.

Every function takes customer_id from the caller (the call session), never from
the model, so the model cannot read or change another customer's invoices.
Money is stored as integer paise; amounts are formatted only when returned.
"""
import sqlite3
from datetime import date, datetime

DB = "mock_erp.db"
OPEN_STATUSES = ("pending", "overdue")


def get_conn():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    return conn


def format_inr(paise):
    """45000050 -> '450000.50'. Speakable formatting comes later (Phase 3)."""
    return f"{paise / 100:.2f}"


def get_customer(customer_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT id, name, city FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_customers_with_open_invoices():
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.id, c.name, COUNT(*) AS open_count
        FROM customers c JOIN invoices i ON i.customer_id = c.id
        WHERE i.status IN ('pending', 'overdue')
        GROUP BY c.id ORDER BY c.id
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _invoice_status(conn, customer_id, invoice_id):
    """The invoice's status, or None if it doesn't belong to this customer."""
    row = conn.execute(
        "SELECT status FROM invoices WHERE id = ? AND customer_id = ?",
        (invoice_id, customer_id),
    ).fetchone()
    return row["status"] if row else None


# ======================================================================
# TOOLS: each returns a small dict the model can read.
# ======================================================================
def get_open_invoices(customer_id):
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, amount_paise, due_date, status FROM invoices
           WHERE customer_id = ? AND status IN ('pending', 'overdue')
           ORDER BY due_date""",
        (customer_id,),
    ).fetchall()
    conn.close()
    return [
        {"id": r["id"], "amount_inr": format_inr(r["amount_paise"]),
         "due_date": r["due_date"], "status": r["status"]}
        for r in rows
    ]


def log_promise_to_pay(customer_id, invoice_id, promised_date):
    try:
        when = datetime.strptime(promised_date, "%Y-%m-%d").date()
    except ValueError:
        return {"error": "promised_date must look like 2026-11-05"}
    if when < date.today():
        return {"error": "promised_date cannot be in the past"}

    conn = get_conn()
    status = _invoice_status(conn, customer_id, invoice_id)
    if status is None:
        conn.close()
        return {"error": "that invoice does not belong to this customer"}
    if status not in OPEN_STATUSES:
        conn.close()
        return {"error": f"that invoice is {status}, so no payment is due"}
    conn.execute(
        "INSERT INTO promises (invoice_id, promised_date, created_at) VALUES (?, ?, ?)",
        (invoice_id, promised_date, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "invoice_id": invoice_id, "promised_date": promised_date}


def raise_dispute(customer_id, invoice_id, reason):
    conn = get_conn()
    if _invoice_status(conn, customer_id, invoice_id) is None:
        conn.close()
        return {"error": "that invoice does not belong to this customer"}
    conn.execute(
        "INSERT INTO disputes (invoice_id, reason, created_at) VALUES (?, ?, ?)",
        (invoice_id, reason, datetime.now().isoformat()),
    )
    conn.execute("UPDATE invoices SET status = 'disputed' WHERE id = ?", (invoice_id,))
    conn.commit()
    conn.close()
    return {"ok": True, "invoice_id": invoice_id}


def escalate_to_human(customer_id, reason):
    return {"ok": True, "message": "A human colleague will follow up.", "reason": reason}


def log_call(customer_id, outcome, transcript_lines):
    conn = get_conn()
    conn.execute(
        "INSERT INTO call_log (customer_id, outcome, transcript, created_at) VALUES (?, ?, ?, ?)",
        (customer_id, outcome, "\n".join(transcript_lines), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
