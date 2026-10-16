import sqlite3

conn = sqlite3.connect("mock_erp.db")
cur = conn.cursor()

# 1. Row counts
print(cur.execute("SELECT COUNT(*) FROM customers").fetchone())
print(cur.execute("SELECT COUNT(*) FROM invoices").fetchone())

# 2. Overdue invoices with customer names (a JOIN)
rows = cur.execute("""
    SELECT c.name, i.amount_paise / 100.0 AS amount_inr, i.due_date
    FROM invoices i
    JOIN customers c ON c.id = i.customer_id
    WHERE i.status = 'overdue'
    ORDER BY i.due_date
""").fetchall()

for row in rows:
    print(row)

conn.close()