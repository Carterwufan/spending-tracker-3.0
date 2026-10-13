# Spending Tracker

## Local use

1. Install dependencies with `pip install -r requirements.txt`.
2. Add `DATABASE_URL` to `.env` with your Neon PostgreSQL connection string. Set
   `LOCAL_DEV=1` to allow the app's local HTTP session cookie. Locally, if
   `SECRET_KEY` is omitted, the app generates a random key at startup; this
   invalidates sessions whenever the app restarts.
3. Generate a password hash with `python hash_password.py`. Enter your
   master password at the hidden prompt, then put the printed hash in `.env` as
   `APP_PASSWORD_HASH`. The standalone script does not load the Flask app or
   connect to Neon. This stores only a scrypt hash in the app configuration,
   not the master password.
4. Start the app with `python app.py`.

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
   generates `SECRET_KEY` and prompts for the other secret values.
3. Set these environment variables for the Render service:
   - `SECRET_KEY`: a long, random Flask signing key. Render generates this from
     the Blueprint configuration.
   - `DATABASE_URL`: your Neon PostgreSQL connection string, including
     `sslmode=require`.
   - `APP_PASSWORD_HASH`: the scrypt hash printed by `python hash_password.py`.
     Store the hash here, not the plaintext master password.
4. Do not set `LOCAL_DEV` on Render. The app then requires `SECRET_KEY`, and
   session cookies are marked `Secure` so they are sent only over HTTPS.

`SESSION_COOKIE_HTTPONLY` is enabled to prevent browser scripts from reading the
session cookie. The app uses Werkzeug's password hash verification for login,
and its transaction queries bind user-provided values as SQL parameters.
