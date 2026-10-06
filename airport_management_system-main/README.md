# AeroNexus – Airport Management System

A full-stack web-based Airport Management System built with Flask and SQLite for managing flights, passenger bookings, staff operations, administrative workflows, and real-time flight tracking.

## Features

### Role-Based Access Control
- Passenger, Staff, and Admin user roles
- Role-based authentication and session management
- Separate dashboards and workflows for each role
- Secure password hashing using bcrypt

### Passenger Features
- User registration and authentication
- Flight search and filtering
- Flight booking
- Seat selection
- Multiple travel classes
- Dynamic seat availability
- Booking history
- Profile management

### Staff Features
- Add flights
- Edit flight information
- Delete flights
- Manage flight schedules and pricing
- View available flights

### Admin Features
- User management
- Add and delete users
- Password reset
- User role management
- Booking and revenue analytics
- Database backup and restore
- System statistics

### Flight Tracking
- Interactive live flight map using Leaflet.js
- OpenStreetMap integration
- Real-time active flight tracking
- Flight progress calculation
- Flight status detection:
  - Scheduled
  - In Air
  - Landed
- Automatic flight data refresh every 10 seconds
- Interactive flight markers and routes

### Analytics
- Daily booking statistics
- Weekly booking statistics
- Monthly booking statistics
- Revenue tracking
- Booking trend analysis

## Technology Stack

- **Backend:** Python, Flask
- **Frontend:** HTML5, CSS3, JavaScript, Jinja2
- **Database:** SQLite
- **Authentication:** Flask-Session, bcrypt
- **Mapping:** Leaflet.js, OpenStreetMap
- **APIs:** Flask JSON endpoints
- **Libraries:** python-dateutil
- **Development:** Git, GitHub

## Project Metrics

- 23 Flask routes
- 3 user roles
- 3 role-specific dashboards
- 3 analytics time periods
- 11 mapped airport locations
- 10-second flight-tracking refresh interval

## Project Structure

```text
airport_management_system-main/
│
├── main.py
├── database.db
├── configs.json
├── requirements.txt
│
├── templates/
│   ├── admin/
│   ├── employee/
│   ├── passenger/
│   ├── admin_dashboard/
│   ├── employee_dashboard/
│   └── passenger_dashboard/
│
├── static/
│
└── backups/