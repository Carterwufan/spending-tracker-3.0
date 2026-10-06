import hmac
import math
import os
import sqlite3
from datetime import date
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, g, jsonify, redirect, render_template, request,
                   send_from_directory, session, url_for)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

STATIC_DIR = os.path.join(BASE_DIR, "static")
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "expenses.db"))

app = Flask(__name__, template_folder=BASE_DIR, static_folder=STATIC_DIR)
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
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT ''
)"""


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute(SCHEMA)
    con.commit()
    con.close()


init_db()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


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


@app.get("/service-worker.js")
def service_worker():
    response = send_from_directory(
        STATIC_DIR, "service-worker.js", mimetype="application/javascript"
    )
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/")
@login_required
def index():
    return render_template("index.html")


@app.get("/api/expenses")
@login_required
def list_expenses():
    db = get_db()
    rows = db.execute(
        "SELECT id, date, category, amount_cents, note FROM expenses "
        "ORDER BY date DESC, id DESC"
    ).fetchall()
    by_category = db.execute(
        "SELECT category, SUM(amount_cents) AS cents FROM expenses "
        "GROUP BY category ORDER BY cents DESC"
    ).fetchall()
    return jsonify(
        expenses=[
            {"id": r["id"], "date": r["date"], "category": r["category"],
             "amount": r["amount_cents"] / 100, "note": r["note"]}
            for r in rows
        ],
        total=sum(r["amount_cents"] for r in rows) / 100,
        by_category=[
            {"category": r["category"], "total": r["cents"] / 100}
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
    cur = db.execute(
        "INSERT INTO expenses (date, category, amount_cents, note) VALUES (?, ?, ?, ?)",
        (day.isoformat(), category, round(amount * 100), note),
    )
    db.commit()
    return jsonify(id=cur.lastrowid), 201


@app.delete("/api/expenses/<int:expense_id>")
@login_required
def delete_expense(expense_id):
    db = get_db()
    cur = db.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="That expense no longer exists."), 404
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "5000")),
    )
