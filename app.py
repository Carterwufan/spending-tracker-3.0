import math
import os
import secrets
from datetime import date
from functools import wraps

import psycopg
from flask import (Flask, g, jsonify, redirect, render_template, request,
                   session, url_for)
from psycopg.rows import dict_row
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"), encoding="utf-8-sig")
except ImportError:
    pass  # on a host, settings come from real environment variables

LOCAL_DEV = os.environ.get("LOCAL_DEV") == "1"
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Set DATABASE_URL to your Neon PostgreSQL connection string.")

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    if not LOCAL_DEV:
        raise RuntimeError("Set SECRET_KEY in the production environment.")
    SECRET_KEY = secrets.token_hex(32)

APP_PASSWORD_HASH = os.environ.get("APP_PASSWORD_HASH")
if not APP_PASSWORD_HASH:
    raise RuntimeError("Set APP_PASSWORD_HASH to a Werkzeug password hash.")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_SECURE=not LOCAL_DEV,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,
)

SCHEMA = """CREATE TABLE IF NOT EXISTS expenses (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    spent_on DATE NOT NULL,
    category TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    transaction_type TEXT NOT NULL DEFAULT 'expense'
        CHECK (transaction_type IN ('income', 'expense'))
)"""


def connect(**kwargs):
    # prepare_threshold=None keeps this compatible with Neon's pooled connections.
    return psycopg.connect(DATABASE_URL, connect_timeout=15,
                           prepare_threshold=None, **kwargs)


def init_db():
    with connect() as con:   # commits and closes on exit
        con.execute(SCHEMA)
        con.execute(
            "ALTER TABLE expenses ADD COLUMN IF NOT EXISTS transaction_type "
            "TEXT NOT NULL DEFAULT 'expense' "
            "CHECK (transaction_type IN ('income', 'expense'))"
        )


init_db()


def get_db():
    if "db" not in g:
        g.db = connect(row_factory=dict_row)
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.errorhandler(psycopg.OperationalError)
def database_unavailable(_exc):
    message = "The database is waking up or unavailable. Try again in a moment."
    if request.path.startswith("/api/"):
        return jsonify(error=message), 503
    return message, 503


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("auth"):
            if request.path.startswith("/api/"):
                return jsonify(error="Not logged in."), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        supplied = request.form.get("password", "")
        if check_password_hash(APP_PASSWORD_HASH, supplied):
            session.clear()
            session["auth"] = True
            session.permanent = True
            return redirect(url_for("index"))
        error = "That password is incorrect."
    return render_template("login.html", error=error)


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def index():
    return render_template("index.html")


@app.get("/api/expenses")
@login_required
def list_expenses():
    db = get_db()
    rows = db.execute(
        "SELECT id, spent_on, category, amount_cents, note, transaction_type "
        "FROM expenses "
        "ORDER BY spent_on DESC, id DESC"
    ).fetchall()
    by_category = db.execute(
        "SELECT category, SUM(amount_cents) AS cents FROM expenses "
        "WHERE transaction_type = 'expense' "
        "GROUP BY category ORDER BY cents DESC"
    ).fetchall()
    transactions = [
        {"id": r["id"], "date": r["spent_on"].isoformat(),
         "category": r["category"], "amount": r["amount_cents"] / 100,
         "note": r["note"], "type": r["transaction_type"]}
        for r in rows
    ]
    expenses = [transaction for transaction in transactions
                if transaction["type"] == "expense"]
    return jsonify(
        expenses=expenses,
        transactions=transactions,
        total=sum(r["amount_cents"] for r in rows
                  if r["transaction_type"] == "expense") / 100,
        by_category=[
            {"category": r["category"], "total": int(r["cents"]) / 100}
            for r in by_category
        ],
    )


@app.get("/api/monthly-summary")
@login_required
def monthly_summary():
    month_text = request.args.get("month", date.today().strftime("%Y-%m"))
    try:
        year, month_number = (int(part) for part in month_text.split("-"))
        month_start = date(year, month_number, 1)
        if (month_start.strftime("%Y-%m") != month_text
                or (year == 1 and month_number == 1)
                or (year == date.max.year and month_number == 12)):
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        return jsonify(error="Choose a valid month."), 400

    if month_number == 1:
        previous_start = date(year - 1, 12, 1)
    else:
        previous_start = date(year, month_number - 1, 1)
    if month_number == 12:
        next_start = date(year + 1, 1, 1)
    else:
        next_start = date(year, month_number + 1, 1)

    db = get_db()
    rows = db.execute(
        "SELECT date_trunc('month', spent_on)::date AS month, "
        "COALESCE(SUM(amount_cents) FILTER "
        "(WHERE transaction_type = 'income'), 0) AS income_cents, "
        "COALESCE(SUM(amount_cents) FILTER "
        "(WHERE transaction_type = 'expense'), 0) AS expense_cents "
        "FROM expenses WHERE spent_on >= %s AND spent_on < %s "
        "GROUP BY date_trunc('month', spent_on)",
        (previous_start, next_start),
    ).fetchall()
    months = {
        row["month"].strftime("%Y-%m"): {
            "income": int(row["income_cents"]) / 100,
            "expenses": int(row["expense_cents"]) / 100,
        }
        for row in rows
    }

    def totals_for(month):
        totals = months.get(month, {"income": 0, "expenses": 0})
        return {
            **totals,
            "net": totals["income"] - totals["expenses"],
        }

    categories = db.execute(
        "SELECT category, SUM(amount_cents) AS cents FROM expenses "
        "WHERE transaction_type = 'expense' AND spent_on >= %s "
        "AND spent_on < %s GROUP BY category ORDER BY cents DESC",
        (month_start, next_start),
    ).fetchall()
    return jsonify(
        month=month_text,
        previous_month=previous_start.strftime("%Y-%m"),
        current=totals_for(month_text),
        previous=totals_for(previous_start.strftime("%Y-%m")),
        by_category=[
            {"category": row["category"], "total": int(row["cents"]) / 100}
            for row in categories
        ],
    )


@app.post("/api/expenses")
@login_required
def add_expense():
    data = request.get_json(silent=True) or {}

    transaction_type = data.get("type", "expense")
    if transaction_type not in ("income", "expense"):
        return jsonify(error="Choose income or expense."), 400

    category = " ".join(str(data.get("category", "")).split()).capitalize()
    if not category or len(category) > 50:
        return jsonify(error="Enter a category (50 characters max)."), 400

    try:
        amount = float(data.get("amount"))
    except (TypeError, ValueError):
        return jsonify(error="Enter the amount as a number."), 400
    if not math.isfinite(amount) or amount <= 0 or amount > 1_000_000:
        return jsonify(error="Enter an amount greater than zero."), 400

    try:
        day = date.fromisoformat(str(data.get("date") or date.today().isoformat()))
    except ValueError:
        return jsonify(error="Enter a valid date."), 400

    note = str(data.get("note", "")).strip()[:200]

    db = get_db()
    row = db.execute(
        "INSERT INTO expenses "
        "(spent_on, category, amount_cents, note, transaction_type) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (day, category, round(amount * 100), note, transaction_type),
    ).fetchone()
    db.commit()
    return jsonify(id=row["id"]), 201


@app.delete("/api/expenses/<int:expense_id>")
@login_required
def delete_expense(expense_id):
    db = get_db()
    cur = db.execute("DELETE FROM expenses WHERE id = %s", (expense_id,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="That expense no longer exists."), 404
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
