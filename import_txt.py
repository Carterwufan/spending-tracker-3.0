"""One-time import of expenses.txt into Neon.

Run once, locally, from this folder:  python import_txt.py
Needs DATABASE_URL in your .env file. Your old file has no dates, so every
legacy CATEGORY:AMOUNT entry gets today's date. New entries use
CATEGORY:AMOUNT:YYYY-MM-DD and keep their recorded date.
"""
import math
import os
import sys
from datetime import date

import psycopg

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"), encoding="utf-8-sig")
except ImportError:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL")
TXT_PATH = os.path.join(BASE_DIR, "expenses.txt")

SCHEMA = """CREATE TABLE IF NOT EXISTS expenses (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    spent_on DATE NOT NULL,
    category TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT ''
)"""

if not DATABASE_URL:
    sys.exit("Add DATABASE_URL=... to your .env file first.")
if not os.path.exists(TXT_PATH):
    sys.exit(f"Could not find {TXT_PATH}. Put expenses.txt in this folder first.")

today = date.today()
imported = 0

with psycopg.connect(DATABASE_URL, connect_timeout=15, prepare_threshold=None) as con:
    con.execute(SCHEMA)
    if con.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]:
        sys.exit("The database already has expenses, so nothing was imported.")

    with open(TXT_PATH) as f:
        for number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            parts = line.split(":", maxsplit=2)
            if len(parts) not in (2, 3):
                print(
                    f"Skipped line {number}: expected "
                    "CATEGORY:AMOUNT[:YYYY-MM-DD]"
                )
                continue
            category, amount = parts[:2]
            category = " ".join(category.split()).capitalize()
            try:
                value = float(amount)
                spent_on = (
                    today
                    if len(parts) == 2
                    else date.fromisoformat(parts[2])
                )
                if len(parts) == 3 and spent_on.isoformat() != parts[2]:
                    raise ValueError
            except ValueError:
                value = math.nan
                spent_on = today
            if not category or not math.isfinite(value):
                print(
                    f"Skipped line {number}: expected "
                    "CATEGORY:AMOUNT[:YYYY-MM-DD]"
                )
                continue
            con.execute(
                "INSERT INTO expenses (spent_on, category, amount_cents) "
                "VALUES (%s, %s, %s)",
                (spent_on, category, round(value * 100)),
            )
            imported += 1

print(f"Imported {imported} expenses into Neon.")
