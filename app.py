import math
import os
import re
import secrets
import hashlib
import hmac
import smtplib
from datetime import date
from email.message import EmailMessage
from functools import wraps
from urllib.parse import urlsplit

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

SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM = os.environ.get("SMTP_FROM")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
RESET_EMAIL_CONFIGURED = (
    bool(SMTP_HOST and SMTP_FROM and PUBLIC_BASE_URL)
    and bool(SMTP_USERNAME) == bool(SMTP_PASSWORD)
)
if PUBLIC_BASE_URL:
    parsed_base_url = urlsplit(PUBLIC_BASE_URL)
    if (parsed_base_url.scheme not in ("https", "http")
            or not parsed_base_url.netloc
            or parsed_base_url.path not in ("", "/")
            or parsed_base_url.query
            or parsed_base_url.fragment
            or parsed_base_url.username
            or parsed_base_url.password
            or (not LOCAL_DEV and parsed_base_url.scheme != "https")):
        raise RuntimeError(
            "PUBLIC_BASE_URL must be an HTTPS URL in production."
        )
if not 1 <= SMTP_PORT <= 65535:
    raise RuntimeError("SMTP_PORT must be between 1 and 65535.")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    MAX_CONTENT_LENGTH=16 * 1024,
    SESSION_COOKIE_SECURE=not LOCAL_DEV,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,
)

if not RESET_EMAIL_CONFIGURED:
    app.logger.warning(
        "Password reset email is disabled; configure SMTP_HOST, SMTP_FROM, "
        "PUBLIC_BASE_URL, and both SMTP credentials when required."
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

USERS_SCHEMA = """CREATE TABLE IF NOT EXISTS users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    auth_version INTEGER NOT NULL DEFAULT 0,
    reset_requested_at TIMESTAMPTZ
)"""

RESET_TOKENS_SCHEMA = """CREATE TABLE IF NOT EXISTS password_reset_tokens (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL
)"""

_DUMMY_PASSWORD_HASH = generate_password_hash(
    secrets.token_urlsafe(32), method="scrypt"
)


def connect(**kwargs):
    # prepare_threshold=None keeps this compatible with Neon's pooled connections.
    return psycopg.connect(DATABASE_URL, connect_timeout=15,
                           prepare_threshold=None, **kwargs)


def init_db():
    with connect() as con:   # commits and closes on exit
        con.execute(USERS_SCHEMA)
        con.execute(RESET_TOKENS_SCHEMA)
        con.execute(SCHEMA)
        con.execute(
            "ALTER TABLE expenses ADD COLUMN IF NOT EXISTS user_id "
            "BIGINT REFERENCES users(id) ON DELETE CASCADE"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS expenses_user_date_idx "
            "ON expenses (user_id, spent_on DESC, id DESC)"
        )
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
        user_id = session.get("user_id")
        if type(user_id) is not int:
            if request.path.startswith("/api/"):
                return jsonify(error="Not logged in."), 401
            return redirect(url_for("login"))
        user = get_db().execute(
            "SELECT auth_version FROM users WHERE id = %s", (user_id,)
        ).fetchone()
        if (user is None
                or user["auth_version"] != session.get("auth_version")):
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify(error="Not logged in."), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def csrf_token():
    token = session.get("_csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token}


@app.before_request
def protect_state_changes():
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None
    expected = session.get("_csrf_token", "")
    supplied = request.headers.get("X-CSRF-Token", "")
    if request.form:
        supplied = request.form.get("csrf_token", "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        if request.path.startswith("/api/"):
            return jsonify(error="Invalid request token. Refresh and try again."), 400
        return "Invalid request token. Refresh and try again.", 400
    return None


@app.after_request
def set_security_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


def valid_email(value):
    return (
        len(value) <= 254
        and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) is not None
    )


def reset_token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def send_reset_email(email, token):
    if not RESET_EMAIL_CONFIGURED:
        raise RuntimeError("Password-reset email is not configured.")
    base_url = PUBLIC_BASE_URL or request.url_root.rstrip("/")
    reset_url = f"{base_url}{url_for('reset_password')}?token={token}"
    message = EmailMessage()
    message["Subject"] = "Reset your Spending Tracker password"
    message["From"] = SMTP_FROM
    message["To"] = email
    message.set_content(
        "A password reset was requested for your Spending Tracker account.\n\n"
        f"Use this one-time link within 30 minutes:\n{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )

    if SMTP_PORT == 465:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
            if SMTP_USERNAME:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            if SMTP_USERNAME:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(message)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().casefold()
        supplied = request.form.get("password", "")
        user = None
        if valid_email(email):
            user = get_db().execute(
                "SELECT id, password_hash, auth_version FROM users "
                "WHERE email = %s", (email,)
            ).fetchone()
        stored_hash = user["password_hash"] if user else _DUMMY_PASSWORD_HASH
        password_matches = check_password_hash(stored_hash, supplied)
        if user and password_matches:
            session.clear()
            session["user_id"] = user["id"]
            session["auth_version"] = user["auth_version"]
            session.permanent = True
            csrf_token()
            return redirect(url_for("index"))
        error = "That email or password is incorrect."
    return render_template("login.html", error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().casefold()
        password = request.form.get("password", "")
        confirmation = request.form.get("password_confirmation", "")
        if not valid_email(email):
            error = "Enter a valid email address."
        elif not 12 <= len(password) <= 1024:
            error = "Use a password between 12 and 1024 characters."
        elif password != confirmation:
            error = "The passwords do not match."
        else:
            password_hash = generate_password_hash(password, method="scrypt")
            row = get_db().execute(
                "INSERT INTO users (email, password_hash) "
                "VALUES (%s, %s) ON CONFLICT (email) DO NOTHING "
                "RETURNING id, auth_version",
                (email, password_hash),
            ).fetchone()
            if row is None:
                error = "An account for that email may already exist."
            else:
                get_db().commit()
                session.clear()
                session["user_id"] = row["id"]
                session["auth_version"] = row["auth_version"]
                session.permanent = True
                csrf_token()
                return redirect(url_for("index"))
    return render_template("register.html", error=error)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    message = None
    if request.method == "POST":
        if not RESET_EMAIL_CONFIGURED:
            message = (
                "Password reset email is not configured yet. Please contact "
                "the app administrator for help."
            )
        else:
            email = request.form.get("email", "").strip().casefold()
            if not valid_email(email):
                message = (
                    "If an account matches and email delivery is available, "
                    "you will receive a reset link. If it does not arrive, wait "
                    "five minutes before trying again."
                )
            else:
                db = get_db()
                user = db.execute(
                    "UPDATE users SET reset_requested_at = now() "
                    "WHERE email = %s AND (reset_requested_at IS NULL OR "
                    "reset_requested_at < now() - interval '5 minutes') "
                    "RETURNING id",
                    (email,),
                ).fetchone()
                if user:
                    token = secrets.token_urlsafe(32)
                    token_hash = reset_token_hash(token)
                    db.execute(
                        "INSERT INTO password_reset_tokens "
                        "(user_id, token_hash, expires_at) "
                        "VALUES (%s, %s, now() + interval '30 minutes') "
                        "ON CONFLICT (user_id) DO UPDATE SET "
                        "token_hash = EXCLUDED.token_hash, "
                        "expires_at = EXCLUDED.expires_at",
                        (user["id"], token_hash),
                    )
                    db.commit()
                    try:
                        send_reset_email(email, token)
                    except (OSError, smtplib.SMTPException, RuntimeError):
                        app.logger.exception("Could not send password reset email.")
                        with db.transaction():
                            revoked = db.execute(
                                "DELETE FROM password_reset_tokens "
                                "WHERE user_id = %s AND token_hash = %s "
                                "RETURNING user_id",
                                (user["id"], token_hash),
                            ).fetchone()
                            if revoked:
                                db.execute(
                                    "UPDATE users SET reset_requested_at = NULL "
                                    "WHERE id = %s",
                                    (user["id"],),
                                )
                message = (
                    "If an account matches and email delivery is available, "
                    "you will receive a reset link. If it does not arrive, wait "
                    "five minutes before trying again."
                )
    return render_template(
        "forgot_password.html", message=message,
        reset_email_configured=RESET_EMAIL_CONFIGURED,
    )


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    token = request.values.get("token", "")
    is_valid = False
    if len(token) <= 128:
        is_valid = get_db().execute(
            "SELECT 1 FROM password_reset_tokens "
            "WHERE token_hash = %s AND expires_at > now()",
            (reset_token_hash(token),),
        ).fetchone() is not None
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        confirmation = request.form.get("password_confirmation", "")
        if not is_valid:
            error = "This reset link is invalid or has expired."
        elif not 12 <= len(password) <= 1024:
            error = "Use a password between 12 and 1024 characters."
        elif password != confirmation:
            error = "The passwords do not match."
        else:
            db = get_db()
            with db.transaction():
                reset = db.execute(
                    "DELETE FROM password_reset_tokens "
                    "WHERE token_hash = %s AND expires_at > now() "
                    "RETURNING user_id",
                    (reset_token_hash(token),),
                ).fetchone()
                if reset:
                    db.execute(
                        "UPDATE users SET password_hash = %s, "
                        "auth_version = auth_version + 1, "
                        "reset_requested_at = NULL WHERE id = %s",
                        (
                            generate_password_hash(password, method="scrypt"),
                            reset["user_id"],
                        ),
                    )
            db.commit()
            if reset:
                return render_template("reset_password.html", success=True)
            error = "This reset link is invalid or has expired."
            is_valid = False
    return render_template(
        "reset_password.html", token=token, valid=is_valid, error=error
    )


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
        "FROM expenses WHERE user_id = %s "
        "ORDER BY spent_on DESC, id DESC",
        (session["user_id"],),
    ).fetchall()
    by_category = db.execute(
        "SELECT category, SUM(amount_cents) AS cents FROM expenses "
        "WHERE user_id = %s AND transaction_type = 'expense' "
        "GROUP BY category ORDER BY cents DESC",
        (session["user_id"],),
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
        "FROM expenses WHERE user_id = %s AND spent_on >= %s AND spent_on < %s "
        "GROUP BY date_trunc('month', spent_on)",
        (session["user_id"], previous_start, next_start),
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
        "WHERE user_id = %s AND transaction_type = 'expense' "
        "AND spent_on >= %s "
        "AND spent_on < %s GROUP BY category ORDER BY cents DESC",
        (session["user_id"], month_start, next_start),
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
        "(user_id, spent_on, category, amount_cents, note, transaction_type) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (session["user_id"], day, category, round(amount * 100), note,
         transaction_type),
    ).fetchone()
    db.commit()
    return jsonify(id=row["id"]), 201


@app.delete("/api/expenses/<int:expense_id>")
@login_required
def delete_expense(expense_id):
    db = get_db()
    cur = db.execute(
        "DELETE FROM expenses WHERE id = %s AND user_id = %s",
        (expense_id, session["user_id"]),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="That expense no longer exists."), 404
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
