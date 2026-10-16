import sqlite3
import random
from datetime import date, timedelta

conn = sqlite3.connect("mock_erp.db")
cur = conn.cursor()

cur.execute("DROP TABLE IF EXISTS invoices")
cur.execute("DROP TABLE IF EXISTS customers")

cur.execute("""
    CREATE TABLE customers (
        id    INTEGER PRIMARY KEY,
        name  TEXT NOT NULL,
        city  TEXT NOT NULL
    )
""")

cur.execute("""
    CREATE TABLE invoices (
        id           INTEGER PRIMARY KEY,
        customer_id  INTEGER NOT NULL,
        amount_paise INTEGER NOT NULL,
        due_date     TEXT NOT NULL,
        status       TEXT NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES customers(id)
    )
""")

company_names = [
    "Apex Traders", "Bluewave Pharma", "Cedar Logistics", "Delta Foods",
    "Everest Textiles", "Falcon Steel", "Greenleaf Organics", "Horizon Tech",
    "Indus Packaging", "Jupiter Chemicals", "Kiran Electricals", "Lotus Retail",
    "Meridian Labs", "Nova Plastics", "Orbit Auto Parts", "Pinnacle Paper",
    "Quartz Ceramics", "Riverbend Dairy", "Sunrise Agro", "Titan Tools",
]
cities = ["Delhi", "Mumbai", "Pune", "Jaipur", "Chennai", "Hyderabad"]

random.seed(42)

customers = []
for name in company_names:
    customers.append((name, random.choice(cities)))

cur.executemany("INSERT INTO customers (name, city) VALUES (?, ?)", customers)

today = date.today()
invoices = []

for _ in range(40):
    customer_id = random.randint(1, 20)
    amount_paise = random.randint(500_00, 50_000_00)  # ₹500 to ₹50,000
    due = today + timedelta(days=random.randint(-60, 60))

    if due < today:
        status = random.choice(["paid", "overdue"])
    else:
        status = random.choice(["pending", "paid"])

    invoices.append((customer_id, amount_paise, due.isoformat(), status))

cur.executemany(
    "INSERT INTO invoices (customer_id, amount_paise, due_date, status) VALUES (?, ?, ?, ?)",
    invoices,
)

cur.execute("DROP TABLE IF EXISTS call_log")
cur.execute("DROP TABLE IF EXISTS promises")
cur.execute("DROP TABLE IF EXISTS disputes")

cur.execute("""
    CREATE TABLE call_log (
        id           INTEGER PRIMARY KEY,
        customer_id  INTEGER NOT NULL,
        outcome      TEXT NOT NULL,
        transcript   TEXT,
        created_at   TEXT NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES customers(id)
    )
""")

cur.execute("""
    CREATE TABLE promises (
        id            INTEGER PRIMARY KEY,
        invoice_id    INTEGER NOT NULL,
        promised_date TEXT NOT NULL,
        created_at    TEXT NOT NULL
    )
""")

cur.execute("""
    CREATE TABLE disputes (
        id         INTEGER PRIMARY KEY,
        invoice_id INTEGER NOT NULL,
        reason     TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
""")

conn.commit()
conn.close()
print("Done: 20 customers, 40 invoices")