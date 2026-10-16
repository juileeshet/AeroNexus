# AeroNexus

A flight booking system built with Flask and SQLite. Passengers book a seat on a cabin map, add meals and extras, and get a boarding pass with their gate, a route to it, and the shops along the way. Staff run the schedule and gates. Admins monitor the system.

## What each role can do

**Passenger**
- Browse upcoming flights, filter by domestic or international, search by city, airline or flight number
- Choose a seat on a cabin map showing the cockpit, doors, wings, exit rows, aisle and window seats
- Pre-order a meal and add extra baggage, priority boarding, lounge access, insurance or free special assistance
- See the full price (fare, taxes, seat fee, meal, extras) before confirming. Prices are calculated on the server
- Get a boarding pass straight after booking: PNR, gate, terminal, boarding time, group, baggage allowance
- Gate and shop guide: a schematic route from the entrance, through security, to the gate, with the shops and amenities on the way
- Cancel a ticket with the refund amount shown first; the seat is released

**Staff**
- Add and edit flights, including terminal and gate (passengers see changes on their boarding pass immediately)
- Download a passenger manifest (CSV) for any flight
- Manage the airport shop directory used by the passenger guide

**Admin** (monitoring only, cannot book flights)
- System overview: net revenue, bookings, seats sold and empty, load factor, bookings and revenue chart
- Flights and seats: occupancy per flight and a read-only cabin map showing sold seats
- Manage users (add, delete, reset password), backup and restore, CSV reports
- Recent activity and system health are read from the database, not hardcoded

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate        # macOS/Linux: source venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create the database (first time only), from the project folder:
   ```bash
   python database/db.py init
   ```
4. Run the app:
   ```bash
   python main.py
   ```
5. Open http://localhost:5000

Default accounts: `admin` / `admin123` and `staff` / `staff123`. Passengers register from the Register page.

The app upgrades an existing database automatically on start (new columns and catalog tables are added, nothing is deleted).

### Refreshing the flight schedule
The sample flights are dated relative to the day you ran `init`, so they eventually depart. To get a fresh schedule, run `python database/db.py reset` then `python database/db.py init`. This erases all data, including bookings. Staff can also add flights any time from the dashboard.

## Notes
- Meals, add-ons, airports and shops are stored in database tables (`meals`, `addons`, `airports`, `airport_shops`), seeded on first start. Shop names are placeholders; staff can edit them.
- The airport route map is schematic and not to scale. The barcode on the boarding pass is decorative and does not scan.
- Currency is Indian rupees.

## Project structure
- `main.py`: routes and business rules
- `schema.py`: database upgrades and seed catalogs
- `database/db.py`: create, reset and inspect the database
- `templates/`: pages (`_seatmap.html` is the shared cabin map)
- `static/`: CSS, JS and images
