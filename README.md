# Spending Tracker

## Local use

1. Install dependencies with `pip install -r requirements.txt`.
2. Add `DATABASE_URL` to `.env` with your Neon PostgreSQL connection string. Set
   `LOCAL_DEV=1` to allow the app's local HTTP session cookie. Locally, if
   `SECRET_KEY` is omitted, the app generates a random key at startup; this
   invalidates sessions whenever the app restarts.
3. Start the app with `python app.py`. Create an account from the login page.
   Account passwords are stored as Werkzeug scrypt hashes.

Password recovery needs an SMTP account. For local use, configure `SMTP_HOST`,
`SMTP_FROM`, and `PUBLIC_BASE_URL` in `.env`; use port 587 with STARTTLS or
port 465 with implicit TLS. Set `SMTP_USERNAME` and `SMTP_PASSWORD` together
when your mail server requires authentication. `LOCAL_DEV=1` allows an HTTP
`PUBLIC_BASE_URL` for local testing.

The app listens on port 5000. Use the Render HTTPS URL for production access.
Never commit `.env` or put plaintext passwords or database credentials in source
control.

## Track income and compare months

Add each record as either an **Income** or **Expense**, with its date and
category. The monthly comparison shows income, spending, and net (income minus
spending) for the selected month, alongside the previous month's totals and
changes. Existing records are kept and treated as expenses.

Database values from transaction fields are passed as Psycopg query parameters;
do not insert user input into SQL strings.

## Host on Render with Neon

1. Keep the GitHub repository private and ensure `.gitignore` excludes `.env`
   and local data.
2. Create a Render Blueprint from the repository. The included `render.yaml`
   generates `SECRET_KEY` and prompts for the database and mail settings.
3. Set these environment variables for the Render service:
   - `SECRET_KEY`: a long, random Flask signing key. Render generates this from
     the Blueprint configuration.
   - `DATABASE_URL`: your Neon PostgreSQL connection string, including
     `sslmode=require`.
   - `SMTP_HOST`, `SMTP_PORT`, and `SMTP_FROM`: your mail server and verified
     sender address. Use port 587 for STARTTLS or 465 for implicit TLS.
   - `SMTP_USERNAME` and `SMTP_PASSWORD`: provide both if the mail server
     requires authentication.
   - `PUBLIC_BASE_URL`: the app's public HTTPS origin, such as
     `https://spending-tracker.onrender.com`. Reset emails use this fixed
     origin rather than a request's Host header.
4. Do not set `LOCAL_DEV` on Render. The app then requires `SECRET_KEY`, and
   session cookies are marked `Secure` so they are sent only over HTTPS.
   Production startup also requires the reset-email settings.

`SESSION_COOKIE_HTTPONLY` is enabled to prevent browser scripts from reading the
session cookie. Forms and API writes require CSRF tokens. Password reset
messages do not reveal whether an email is registered; reset tokens are
single-use, expire after 30 minutes, and are stored only as hashes. Existing
expenses from the former shared-password setup remain unassigned and are not
visible to newly created accounts. The former shared password no longer signs
in; create a new account to use the app.

Each account has its own expenses. Database queries bind user-provided values
as SQL parameters and restrict reads, inserts, and deletes to the signed-in
account.
