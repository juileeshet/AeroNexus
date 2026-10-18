# AeroNexus — Airport Management System

AeroNexus is a web-based airport management system built with Flask and SQLite. It provides flight booking, passenger check-in, boarding management, flight tracking, and administrative tools through a unified interface.

## Features

### Passenger Portal
- Register and book flights.
- Select seats using an interactive seat map.
- Choose meals and additional services.
- View boarding passes and airport information.
- Cancel bookings and review refund calculations.
- Track flight delays and cancellations.

### Staff Portal
- View assigned flights and passenger details.
- Check in passengers.
- Manage the boarding process.

### Admin Dashboard
- Add, edit, delay, and cancel flights.
- Manage users, airport shops, and staff assignments.
- View audit logs.
- Create database backups.
- Manage flight operations and passenger bookings.

### Flight Tracking
- View flight information and status through an interactive flight tracker map.

## Tech Stack

| Technology | Purpose |
|---|---|
| Python | Application logic |
| Flask | Web framework and routing |
| SQLite | Database management |
| Flask-Session | Session management |
| bcrypt | Password hashing |
| Bootstrap 5 | Responsive user interface |
| HTML, CSS, JavaScript | Frontend development |
| Leaflet | Interactive maps |

## Getting Started

### Prerequisites

- Python 3.9 or later
- pip
- Git

### 1. Clone the repository

```bash
git clone <repository-url>
cd AeroNexus-Git
```

Replace `<repository-url>` with your actual GitHub repository URL.

### 2. Create a virtual environment

```bash
python -m venv venv
```

Activate it on Windows:

```powershell
venv\Scripts\activate
```

On macOS or Linux:

```bash
source venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Initialize the database

```bash
python database/db.py init
```

This initializes the database and creates sample flights and accounts.

### 5. Run the application

```bash
python main.py
```

Open the application in your browser:

`http://127.0.0.1:5000`

## Demo Accounts

| Role | Username | Password |
|---|---|---|
| Administrator | `admin` | `admin123` |
| Staff | `staff` | `staff123` |
| Passenger | Register a new account | Set during registration |

These are development credentials. Change the default passwords before deploying the application.

## Running Tests

Run the automated test suite from the project root:

```bash
python -m unittest discover -s tests -t .
```

## Configuration

The application supports the following environment variables:

| Variable | Purpose |
|---|---|
| `AERONEXUS_SECRET_KEY` | Configures the Flask session signing key |
| `AERONEXUS_HTTPS=1` | Enables secure session cookies over HTTPS |
| `AERONEXUS_STRICT_BOARDING=1` | Enforces check-in and boarding time windows |
| `FLASK_DEBUG=1` | Enables Flask debug mode for local development |

Keep secret keys and credentials out of version control. Debug mode should not be enabled in production.

## Project Structure

```text
AeroNexus-Git/
├── main.py
├── schema.py
├── wsgi.py
├── configs.json
├── requirements.txt
├── database/
│   └── db.py
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── flight_tracker.html
│   └── ...
├── static/
├── tests/
└── docs/
```

## Future Enhancements

- Integration with real-time flight information APIs.
- Online payment gateway integration.
- Email and SMS booking notifications.
- Advanced operational analytics and reporting.

## License

No license has been specified. Add a license if you intend to distribute or permit reuse of this project.
