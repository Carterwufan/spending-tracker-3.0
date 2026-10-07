import hmac
import math
import os
from datetime import date
from functools import wraps

import psycopg
from flask import (Flask, g, jsonify, redirect, render_template, request,
                   session, url_for)
from psycopg.rows import dict_row

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"), encoding="utf-8-sig")
except ImportError:
    pass  # on a host, settings come from real environment variables

DATABASE_URL = os.environ["DATABASE_URL"]      # required: Neon connection string

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]      # required: long random string
APP_PASSWORD = os.environ["APP_PASSWORD"]      # required: your login password
app.config.update(
    # Cookies only travel over HTTPS unless you set LOCAL_DEV=1 for local testing.
    SESSION_COOKIE_SECURE=os.environ.get("LOCAL_DEV") != "1",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,
)

SCHEMA = """CREATE TABLE IF NOT EXISTS expenses (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    spent_on DATE NOT NULL,
    category TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT ''
)"""


def connect(**kwargs):
    # prepare_threshold=None keeps this compatible with Neon's pooled connections.
    return psycopg.connect(DATABASE_URL, connect_timeout=15,
                           prepare_threshold=None, **kwargs)


def init_db():
    with connect() as con:   # commits and closes on exit
        con.execute(SCHEMA)


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
        if hmac.compare_digest(supplied.encode(), APP_PASSWORD.encode()):
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
        "SELECT id, spent_on, category, amount_cents, note FROM expenses "
        "ORDER BY spent_on DESC, id DESC"
    ).fetchall()
    by_category = db.execute(
        "SELECT category, SUM(amount_cents) AS cents FROM expenses "
        "GROUP BY category ORDER BY cents DESC"
    ).fetchall()
    return jsonify(
        expenses=[
            {"id": r["id"], "date": r["spent_on"].isoformat(),
             "category": r["category"], "amount": r["amount_cents"] / 100,
             "note": r["note"]}
            for r in rows
        ],
        total=sum(r["amount_cents"] for r in rows) / 100,
        by_category=[
            {"category": r["category"], "total": int(r["cents"]) / 100}
            for r in by_category
        ],
    )


@app.post("/api/expenses")
@login_required
def add_expense():
    data = request.get_json(silent=True) or {}

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
        "INSERT INTO expenses (spent_on, category, amount_cents, note) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (day, category, round(amount * 100), note),
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
