# AeroNexus: Airport Management System

A flight booking and airport operations app built with Flask and SQLite. Free to run, with no paid services or API keys.

## Features

- **Passengers:** book a seat on a cabin map, add meals and extras, get a boarding pass and an airport guide, cancel with a refund shown first, and see delays and cancellations
- **Staff:** see only their assigned flights, view each passenger and who booked them, and check passengers in and board them
- **Admins:** add and edit flights, delay or cancel them (cancelling refunds everyone), assign staff, manage shops and users, take backups, and view an audit log
- **Everyone:** live flight tracker map

## Run it

Needs Python 3.9 or newer.

```bash
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python database/db.py init     # creates sample flights and accounts
python main.py
```

Open http://127.0.0.1:5000

| Role | Page | Username | Password |
|---|---|---|---|
| Admin | `/admin_login` | `admin` | `admin123` |
| Staff | `/employee_login` | `staff` | `staff123` |
| Passenger | `/register` | create your own | |

Change the default passwords before putting the app online.

## Tests

```bash
python -m unittest discover -s tests -t .
```

## Deploy for free

See [DEPLOY.md](DEPLOY.md).

## Settings

| Variable | Purpose |
|---|---|
| `AERONEXUS_SECRET_KEY` | Signs sessions. Set it on any real server |
| `AERONEXUS_HTTPS=1` | Secure cookies when served over HTTPS |
| `AERONEXUS_STRICT_BOARDING=1` | Enforce real check-in and boarding windows |
| `FLASK_DEBUG=1` | Debug mode, local use only |

## Built with

Flask, SQLite, bcrypt, Bootstrap 5, Leaflet.
