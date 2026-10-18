# Putting AeroNexus online for free

## Recommended: PythonAnywhere (free "Beginner" account)

Why this one: it keeps your files and database between restarts, needs no credit card, and your site
gets an `https://YOURNAME.pythonanywhere.com` address.

Free-tier limits (checked October 2026; they change, so look at the PythonAnywhere pricing page):
one web app, 512 MB of disk, 100 CPU-seconds per day, no SSH, and **an unused web app expires after
1 month** (log in and press the extend button on the Web tab to keep it alive).

1. Create a free account at pythonanywhere.com.
2. **Files** tab: upload `airport_management_system-roles-fixed.zip`. Open a **Bash console** and run:
   ```bash
   unzip airport_management_system-roles-fixed.zip
   cd airport_management_system-main
   python3 -m venv ~/aeronexus-venv
   source ~/aeronexus-venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Web** tab: *Add a new web app*, choose *Manual configuration*, pick the same Python version your
   virtualenv uses, then set:
   - **Virtualenv**: `/home/YOURNAME/aeronexus-venv`
   - **WSGI configuration file**: replace its contents with
     ```python
     import os, sys
     PROJECT = '/home/YOURNAME/airport_management_system-main'
     sys.path.insert(0, PROJECT)
     os.environ['AERONEXUS_SECRET_KEY'] = 'paste-a-long-random-string-here'
     os.environ['AERONEXUS_HTTPS'] = '1'
     from wsgi import application
     ```
     (Make a random string with `python3 -c "import secrets; print(secrets.token_hex(32))"`.)
4. Press **Reload**. The first visit creates the sample database automatically.
5. **Immediately** log in as `admin` / `admin123` and `staff` / `staff123` and change both passwords
   (Password button in the top bar).

Updating later: upload the new files over the old ones (keep `database.db`), then press Reload.

## Quick demo only: Render (free web service)

Render's free web services have an **ephemeral filesystem**: the SQLite database is wiped every time the
service restarts, redeploys or spins down after 15 minutes idle (Render documents this at
render.com/docs/free). Fine for a five-minute demo, not for keeping real data. The included `Procfile`
(`gunicorn wsgi:application`) is what it needs, and the app recreates the sample data on each start.
Set `AERONEXUS_SECRET_KEY` and `AERONEXUS_HTTPS=1` as environment variables.

## Settings reference

| Variable | What it does |
|---|---|
| `AERONEXUS_SECRET_KEY` | Signs sessions. Set it on any real server. |
| `AERONEXUS_HTTPS=1` | Marks the session cookie Secure (use when served over HTTPS). |
| `AERONEXUS_STRICT_BOARDING=1` | Enforces real check-in and boarding windows (off by default so demos work). |
| `FLASK_DEBUG=1` | Debug mode for local development only. Never on a public server. |
