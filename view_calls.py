import sqlite3

conn = sqlite3.connect("mock_erp.db")

print("=== call_log ===")
for row in conn.execute("SELECT id, customer_id, outcome, created_at FROM call_log"):
    print(row)

print("\n=== promises ===")
for row in conn.execute("SELECT id, invoice_id, promised_date FROM promises"):
    print(row)

print("\n=== disputes ===")
for row in conn.execute("SELECT id, invoice_id, reason FROM disputes"):
    print(row)

print("\n=== last transcript ===")
last = conn.execute("SELECT transcript FROM call_log ORDER BY id DESC LIMIT 1").fetchone()
print(last[0] if last else "(no calls yet)")

conn.close()