"""One-time import of expenses.txt (CATEGORY:AMOUNT per line) into expenses.db.

Run once, from this folder:  python import_txt.py
Your old file has no dates, so every imported expense gets today's date.
"""
import math
import os
import sqlite3
import sys
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "expenses.db"))
TXT_PATH = os.path.join(BASE_DIR, "expenses.txt")

SCHEMA = """CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT ''
)"""

if not os.path.exists(TXT_PATH):
    sys.exit(f"Could not find {TXT_PATH}. Copy expenses.txt into this folder first.")

con = sqlite3.connect(DB_PATH)
con.execute(SCHEMA)
if con.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]:
    sys.exit("The database already has expenses, so nothing was imported.")

today = date.today().isoformat()
imported = 0
with open(TXT_PATH) as f:
    for number, line in enumerate(f, start=1):
        line = line.strip()
        if not line:
            continue
        category, sep, amount = line.partition(":")
        category = " ".join(category.split()).capitalize()
        try:
            value = float(amount)
        except ValueError:
            value = math.nan
        if not sep or not category or not math.isfinite(value):
            print(f"Skipped line {number}: expected CATEGORY:AMOUNT")
            continue
        con.execute(
            "INSERT INTO expenses (date, category, amount_cents) VALUES (?, ?, ?)",
            (today, category, round(value * 100)),
        )
        imported += 1

con.commit()
con.close()
print(f"Imported {imported} expenses into {DB_PATH}")
