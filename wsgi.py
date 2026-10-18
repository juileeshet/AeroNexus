"""WSGI entry point for hosting (PythonAnywhere, gunicorn, ...).

    PythonAnywhere: point the WSGI file at this module (see DEPLOY.md)
    gunicorn:       gunicorn wsgi:application

It switches to the project folder (the app uses relative paths for the database, backups and
sessions) and creates the sample database the first time, so a fresh server works straight away.
"""
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_DIR)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

if not os.path.exists(os.path.join(PROJECT_DIR, 'database.db')):
    from database import db
    db.init_db()

from main import app as application  # noqa: E402

app = application
