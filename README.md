# AeroNexus — Airport Management System

AeroNexus is a web-based airport management and flight booking system built using Python Flask and SQLite. It provides dedicated interfaces for passengers, airport staff, and administrators to manage flight reservations and airport operations.

## Features

- **Passenger Portal:** Flight search, seat selection, booking management, add-on services, and digital boarding passes.
- **Staff Dashboard:** Manage flight schedules, gates, and airport shops; export passenger manifests.
- **Admin Dashboard:** Monitor bookings, revenue, seat occupancy, manage users, and generate reports.
- **Booking Management:** Fare calculation, ticket cancellation, and database-backed reservations.
- **Database Management:** SQLite storage with initialization, backup, and restore functionality.

## Tech Stack

- **Backend:** Python, Flask
- **Frontend:** HTML, CSS, JavaScript, Jinja2
- **Database:** SQLite
- **Authentication:** bcrypt, Flask-Session

## Installation

```bash
git clone https://github.com/juileeshet/AeroNexus.git
cd AeroNexus
python -m venv venv
```

Activate the virtual environment and install dependencies:

```bash
# Windows
venv\Scripts\activate

# Install dependencies
python -m pip install -r requirements.txt
```

Initialize the database and run the application:

```bash
python database/db.py init
python main.py
```

Open `http://localhost:5000` in your browser.

## Author

**Juilee Shet**

GitHub: [juileeshet](https://github.com/juileeshet)
