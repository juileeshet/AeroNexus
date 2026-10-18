"""
Schema upgrades and reference data for AeroNexus.

ensure_schema() is idempotent: it can run on every start-up against a brand new
database or an existing one, and never deletes user data. Catalog data
(airports, shops, meals, add-ons) lives in database tables so it can be managed
instead of being baked into page templates.
"""
import os
import re
import sqlite3

DB_FILE = 'database.db'

# (city, IATA, name, country, terminals)
AIRPORTS = [
    ('Mumbai', 'BOM', 'Chhatrapati Shivaji Maharaj International Airport', 'India', 2),
    ('Delhi', 'DEL', 'Indira Gandhi International Airport', 'India', 3),
    ('Bangalore', 'BLR', 'Kempegowda International Airport', 'India', 2),
    ('Chennai', 'MAA', 'Chennai International Airport', 'India', 2),
    ('Hyderabad', 'HYD', 'Rajiv Gandhi International Airport', 'India', 1),
    ('Kolkata', 'CCU', 'Netaji Subhas Chandra Bose International Airport', 'India', 1),
    ('Dubai', 'DXB', 'Dubai International Airport', 'UAE', 3),
    ('Doha', 'DOH', 'Hamad International Airport', 'Qatar', 1),
    ('Singapore', 'SIN', 'Singapore Changi Airport', 'Singapore', 4),
    ('London', 'LHR', 'London Heathrow Airport', 'United Kingdom', 4),
    ('Frankfurt', 'FRA', 'Frankfurt Airport', 'Germany', 2),
]
GATES_PER_TERMINAL = 20

# (name, category, zone, position 0-100 along that zone, opening hours)
SHOP_TEMPLATES = [
    ('Travel Essentials', 'Convenience', 'landside', 22, '24 hours'),
    ('Currency Exchange', 'Forex', 'landside', 45, '24 hours'),
    ('Departure Cafe', 'Cafe', 'landside', 72, '05:00-23:00'),
    ('Brew & Bite Cafe', 'Cafe', 'airside', 10, '05:00-23:00'),
    ('Duty Free Emporium', 'Duty Free', 'airside', 22, '24 hours'),
    ('WellCare Pharmacy', 'Pharmacy', 'airside', 33, '24 hours'),
    ('Spice Route Food Court', 'Restaurant', 'airside', 45, '24 hours'),
    ('Charging Pods', 'Amenity', 'airside', 54, '24 hours'),
    ('Page Turner Books', 'Bookstore', 'airside', 62, '06:00-22:00'),
    ('TechPort Electronics', 'Electronics', 'airside', 75, '06:00-22:00'),
    ('Quiet Room & Prayer Space', 'Amenity', 'airside', 86, '24 hours'),
    ('Sky Lounge', 'Lounge', 'airside', 93, '24 hours'),
]

# (code, name, description, diet, price)
MEALS = [
    ('NONE', 'No meal', 'Skip the meal service', '-', 0),
    ('VEG', 'Vegetarian meal', 'Seasonal vegetables, dal, rice and bread', 'Veg', 350),
    ('NONVEG', 'Chicken meal', 'Chicken curry with rice and bread', 'Non-veg', 420),
    ('JAIN', 'Jain meal', 'Prepared without root vegetables', 'Veg', 350),
    ('VEGAN', 'Vegan meal', 'Fully plant-based, no dairy', 'Vegan', 380),
    ('DIAB', 'Diabetic-friendly meal', 'Low sugar, high fibre', 'Veg', 380),
    ('CHILD', 'Child meal', 'Smaller portions, kid friendly', 'Veg', 300),
]

# (code, name, description, price, group)
ADDONS = [
    ('XBAG10', 'Extra baggage 10 kg', 'Added to your checked allowance', 1500, 'baggage'),
    ('XBAG20', 'Extra baggage 20 kg', 'Added to your checked allowance', 2800, 'baggage'),
    ('PRIORITY', 'Priority boarding', 'Board in the first group', 400, ''),
    ('LOUNGE', 'Lounge access', 'Relax before departure', 1200, ''),
    ('INSURE', 'Travel insurance', 'Covers delays and cancellations', 299, ''),
    ('ASSIST', 'Special assistance', 'Wheelchair or boarding help, free of charge', 0, ''),
]

_ready = False


def _table_exists(c, name):
    c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return c.fetchone() is not None


def _add_column(c, table, definition):
    try:
        c.execute(f'ALTER TABLE {table} ADD COLUMN {definition}')
    except sqlite3.OperationalError:
        pass  # column already there


def gate_number(gate):
    """Numeric part of a gate label such as '14' or 'B14'."""
    m = re.search(r'\d+', str(gate or ''))
    return int(m.group()) if m else None


def ensure_schema(db_path=DB_FILE):
    """Upgrade the schema. Returns True when the base tables exist."""
    global _ready
    if not os.path.exists(db_path):
        return False
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        if not (_table_exists(c, 'flights') and _table_exists(c, 'tickets')
                and _table_exists(c, 'passengers')):
            return False

        _add_column(c, 'tickets', 'created_at TEXT')
        _add_column(c, 'tickets', "status TEXT DEFAULT 'CONFIRMED'")
        _add_column(c, 'tickets', 'meal TEXT')
        _add_column(c, 'tickets', 'breakdown TEXT')
        _add_column(c, 'tickets', 'refund_amount REAL DEFAULT 0')
        _add_column(c, 'tickets', 'cancelled_at TEXT')
        _add_column(c, 'flights', 'terminal TEXT')
        _add_column(c, 'flights', 'gate TEXT')
        _add_column(c, 'flights', 'created_at TEXT')
        _add_column(c, 'passengers', 'created_at TEXT')
        _add_column(c, 'flights', 'ops_status TEXT')
        _add_column(c, 'flights', 'ops_reason TEXT')
        _add_column(c, 'flights', 'delay_minutes INTEGER DEFAULT 0')
        _add_column(c, 'flights', 'orig_departure TEXT')
        _add_column(c, 'flights', 'orig_arrival TEXT')
        _add_column(c, 'tickets', 'checked_in_at TEXT')
        _add_column(c, 'tickets', 'boarded_at TEXT')

        c.execute("UPDATE tickets SET created_at = datetime('now','localtime') WHERE created_at IS NULL")
        c.execute("UPDATE tickets SET status = 'CONFIRMED' WHERE status IS NULL")
        c.execute("UPDATE tickets SET refund_amount = 0 WHERE refund_amount IS NULL")
        c.execute("UPDATE flights SET created_at = datetime('now','localtime') WHERE created_at IS NULL")
        c.execute("UPDATE passengers SET created_at = datetime('now','localtime') WHERE created_at IS NULL")

        c.execute('''CREATE TABLE IF NOT EXISTS airports
                    (city TEXT PRIMARY KEY, iata TEXT NOT NULL, name TEXT NOT NULL,
                     country TEXT NOT NULL, terminals INTEGER NOT NULL DEFAULT 1,
                     gates INTEGER NOT NULL DEFAULT 20)''')
        c.execute('''CREATE TABLE IF NOT EXISTS airport_shops
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, city TEXT NOT NULL,
                     name TEXT NOT NULL, category TEXT NOT NULL,
                     zone TEXT NOT NULL DEFAULT 'airside', pos INTEGER NOT NULL DEFAULT 50,
                     hours TEXT NOT NULL DEFAULT '24 hours')''')
        c.execute('''CREATE TABLE IF NOT EXISTS meals
                    (code TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
                     diet TEXT, price REAL NOT NULL DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS addons
                    (code TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
                     price REAL NOT NULL DEFAULT 0, grp TEXT DEFAULT '')''')

        c.execute('SELECT COUNT(*) FROM airports')
        if c.fetchone()[0] == 0:
            c.executemany('INSERT INTO airports (city, iata, name, country, terminals, gates) VALUES (?,?,?,?,?,?)',
                          [a + (GATES_PER_TERMINAL,) for a in AIRPORTS])
        c.execute('SELECT COUNT(*) FROM airport_shops')
        if c.fetchone()[0] == 0:
            rows = [(a[0],) + t for a in AIRPORTS for t in SHOP_TEMPLATES]
            c.executemany('INSERT INTO airport_shops (city, name, category, zone, pos, hours) VALUES (?,?,?,?,?,?)', rows)
        c.execute('SELECT COUNT(*) FROM meals')
        if c.fetchone()[0] == 0:
            c.executemany('INSERT INTO meals (code, name, description, diet, price) VALUES (?,?,?,?,?)', MEALS)
        c.execute('SELECT COUNT(*) FROM addons')
        if c.fetchone()[0] == 0:
            c.executemany('INSERT INTO addons (code, name, description, price, grp) VALUES (?,?,?,?,?)', ADDONS)

        c.execute('''CREATE TABLE IF NOT EXISTS staff_assignments
                    (staff_username TEXT NOT NULL, f_id INTEGER NOT NULL,
                     PRIMARY KEY (staff_username, f_id))''')

        c.execute('''CREATE TABLE IF NOT EXISTS audit_log
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, actor TEXT NOT NULL,
                     role TEXT NOT NULL, action TEXT NOT NULL, target TEXT, detail TEXT)''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log (ts)')

        assign_missing_gates(c)
        conn.commit()
        _ready = True
        return True
    finally:
        conn.close()


def default_terminal_gate(c, f_id, city):
    c.execute('SELECT terminals, gates FROM airports WHERE city = ?', (city,))
    row = c.fetchone()
    terminals, gates = (row[0], row[1]) if row else (1, GATES_PER_TERMINAL)
    terminal = str(1 + (f_id % max(terminals, 1)))
    gate = str(((f_id * 7) % gates) + 1)
    return terminal, gate


def assign_missing_gates(c):
    c.execute("SELECT f_id, source FROM flights WHERE gate IS NULL OR gate = '' OR terminal IS NULL OR terminal = ''")
    for f_id, source in c.fetchall():
        terminal, gate = default_terminal_gate(c, f_id, source)
        c.execute('''UPDATE flights SET terminal = COALESCE(NULLIF(terminal, ''), ?),
                     gate = COALESCE(NULLIF(gate, ''), ?) WHERE f_id = ?''', (terminal, gate, f_id))


def is_ready():
    return _ready
