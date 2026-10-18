# AeroNexus — Airport Management System

AeroNexus is a full-stack airport management and flight booking web application built using Flask and SQLite. It enables passengers to book flights, select seats, manage tickets, and access boarding passes, while airport staff handle check-ins and boarding, and administrators manage flights, schedules, users, and airport operations.

## Features

- **Passenger Portal:** Flight search, interactive seat selection, meal and add-on selection, ticket booking, cancellations, and digital boarding passes.
- **Staff Dashboard:** View assigned flights, manage passenger check-ins and boarding, and export passenger manifests.
- **Admin Dashboard:** Manage flights, delays, cancellations, staff assignments, users, and airport shops.
- **Analytics and Reports:** Monitor bookings, revenue, seat occupancy, and system activity through dashboards, CSV exports, and audit logs.
- **Flight Tracker:** Map-based flight tracking interface.
- **Security:** Password hashing, session management, CSRF protection, login lockout, and role-based access control.

## Technology Stack

- **Backend:** Python, Flask
- **Frontend:** HTML, CSS, JavaScript, Bootstrap 5, Jinja2
- **Database:** SQLite
- **Authentication:** bcrypt, Flask-Session
- **Maps:** Leaflet
- **Testing:** Python `unittest`

## Installation and Setup

**1. Clone the repository**

```bash
git clone https://github.com/juileeshet/AeroNexus.git
cd AeroNexus
```

**2. Create and activate a virtual environment**

```bash
python -m venv venv
```

Windows:

```powershell
venv\Scripts\activate
```

**3. Install dependencies**

```bash
python -m pip install -r requirements.txt
```

**4. Initialize the database**

```bash
python database/db.py init
```

**5. Run the application**

```bash
python main.py
```

Open `http://127.0.0.1:5000` in your browser.

## Demo Credentials

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `admin123` |
| Staff | `staff` | `staff123` |
| Passenger | Register an account | Set during registration |

Change the default admin and staff passwords before deploying the application publicly.

## Run Tests

```bash
python -m unittest discover -s tests -t .
```

## Project Structure

```text
AeroNexus/
├── main.py
├── schema.py
├── wsgi.py
├── requirements.txt
├── database/
│   └── db.py
├── templates/
│   ├── admin_dashboard/
│   ├── employee_dashboard/
│   ├── passenger_dashboard/
│   └── base.html
├── static/
├── tests/
└── docs/
```

## Limitations

- Flight schedules use sample data rather than a live airline inventory.
- The airport navigation map is schematic.
- Payments are simulated; no payment gateway is integrated.
- The boarding-pass barcode is decorative and is not scannable.

## Author

**Juilee Shet**

GitHub: [juileeshet](https://github.com/juileeshet)

Repository: [AeroNexus](https://github.com/juileeshet/AeroNexus)
