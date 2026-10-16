from flask import (Flask, render_template, request, url_for, session, redirect,
                   jsonify, flash, Response, abort)
import bcrypt
from flask_session import Session
import sqlite3
import csv
import io
import os
import re
import json
import math
import hashlib
import logging
from functools import wraps
from contextlib import contextmanager
from markupsafe import escape
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

import schema

DB = 'database.db'
APP_NAME = 'AeroNexus'

app = Flask(__name__)
app.secret_key = 'secret_key'

app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
Session(app)

app.logger.setLevel(logging.ERROR)

# ---------------------------------------------------------------------------
# Aircraft layout and commercial rules. These drive the seat map, the price
# quote and the admin occupancy numbers, so the page never hardcodes them.
# ---------------------------------------------------------------------------
SEAT_COLS = ['A', 'B', 'C', 'D', 'E', 'F']
SEAT_TYPES = {'A': 'Window', 'B': 'Middle', 'C': 'Aisle', 'D': 'Aisle', 'E': 'Middle', 'F': 'Window'}
CLASS_BANDS = [
    {'name': 'First', 'first_row': 1, 'last_row': 2, 'multiplier': 3},
    {'name': 'Business', 'first_row': 3, 'last_row': 4, 'multiplier': 2},
    {'name': 'Economy', 'first_row': 5, 'last_row': 14, 'multiplier': 1},
]
EXIT_ROWS = {8}
WING_ROWS = (7, 10)
EXIT_ROW_FEE = 600
TAX_RATE = 0.10
INCLUDED_MEAL_CLASSES = ('First', 'Business')
BAGGAGE_KG = {'Economy': (15, 7), 'Business': (30, 10), 'First': (40, 12)}  # (checked, cabin)
BOARDING_OPENS_MIN = 45
GATE_CLOSES_MIN = 20
REFUND_RULES = [(48, 0.90), (4, 0.50)]  # (hours before departure, refund share)
TOTAL_SEATS = sum((b['last_row'] - b['first_row'] + 1) * len(SEAT_COLS) for b in CLASS_BANDS)
CLASS_CAPACITY = {b['name']: (b['last_row'] - b['first_row'] + 1) * len(SEAT_COLS) for b in CLASS_BANDS}


def seat_info(seat):
    m = re.fullmatch(r'(\d{1,2})([A-F])', str(seat or '').upper())
    if not m:
        return None
    row, col = int(m.group(1)), m.group(2)
    for band in CLASS_BANDS:
        if band['first_row'] <= row <= band['last_row']:
            return {'seat': f'{row}{col}', 'row': row, 'col': col, 'class': band['name'],
                    'multiplier': band['multiplier'], 'type': SEAT_TYPES[col],
                    'exit': row in EXIT_ROWS}
    return None


def build_layout():
    layout = []
    for band in CLASS_BANDS:
        rows = []
        for r in range(band['first_row'], band['last_row'] + 1):
            rows.append({
                'number': r,
                'exit': r in EXIT_ROWS,
                'wing': WING_ROWS[0] <= r <= WING_ROWS[1],
                'seats': [{'id': f'{r}{c}', 'col': c, 'type': SEAT_TYPES[c]} for c in SEAT_COLS],
            })
        layout.append({'name': band['name'], 'multiplier': band['multiplier'], 'rows': rows})
    return layout


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
@contextmanager
def get_db():
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def parse_dt(value):
    value = str(value).strip().replace('T', ' ')
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f'Unrecognised date/time: {value}')


def norm_dt(value):
    return parse_dt(value).strftime('%Y-%m-%d %H:%M')


def now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def humanize(ts):
    try:
        delta = datetime.now() - parse_dt(ts)
    except Exception:
        return ''
    secs = int(delta.total_seconds())
    if secs < 60:
        return 'just now'
    if secs < 3600:
        return f'{secs // 60} min ago'
    if secs < 86400:
        return f'{secs // 3600} h ago'
    return f'{secs // 86400} d ago'


def flight_status(dep, arr, now=None):
    now = now or datetime.now()
    dep_dt, arr_dt = parse_dt(dep), parse_dt(arr)
    if now >= arr_dt:
        return 'Landed'
    if now >= dep_dt:
        return 'In Air'
    if now >= dep_dt - timedelta(minutes=BOARDING_OPENS_MIN):
        return 'Boarding'
    return 'Scheduled'


STATUS_BADGE = {'Scheduled': 'bg-info', 'Boarding': 'bg-warning', 'In Air': 'bg-success', 'Landed': 'bg-secondary'}


def airport_for(conn, city):
    row = conn.execute('SELECT * FROM airports WHERE city = ?', (city,)).fetchone()
    if row:
        return dict(row)
    return {'city': city, 'iata': (city or '???')[:3].upper(), 'name': f'{city} Airport',
            'country': None, 'terminals': 1, 'gates': schema.GATES_PER_TERMINAL}


def is_domestic(a1, a2):
    return bool(a1['country'] and a1['country'] == a2['country'])


def pnr_for(t_id):
    digest = hashlib.sha1(f'AERONEXUS-{t_id}'.encode()).digest()
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    n = int.from_bytes(digest[:5], 'big')
    out = ''
    for _ in range(6):
        out += alphabet[n % 32]
        n //= 32
    return out


def barcode_bars(text, width=300, height=56):
    """Decorative bar pattern derived from the ticket reference (not a scannable code)."""
    digest = hashlib.sha256(text.encode()).digest()
    bars, x = [], 0
    for b in digest * 2:
        w = 1 + (b % 3)
        if x + w > width:
            break
        if (b >> 3) % 2 == 0:
            bars.append({'x': x, 'w': w})
        x += w + 1
    return {'bars': bars, 'width': width, 'height': height}


def boarding_group(info, addon_names):
    if info['class'] in ('First', 'Business') or 'Priority boarding' in addon_names:
        return 1
    return 2 if info['row'] >= 11 else 3


def refund_for(ticket, dep_dt):
    """Return (allowed, amount, share, message)."""
    if ticket['status'] == 'CANCELLED':
        return False, 0.0, 0.0, 'This ticket is already cancelled.'
    hours = (dep_dt - datetime.now()).total_seconds() / 3600
    if hours <= 0:
        return False, 0.0, 0.0, 'This flight has already departed.'
    share = 0.0
    for limit, s in REFUND_RULES:
        if hours >= limit:
            share = s
            break
    return True, round(ticket['price'] * share, 2), share, ''


def refund_policy_text():
    parts = []
    prev = None
    for limit, share in REFUND_RULES:
        if prev is None:
            parts.append(f'{int(share * 100)}% when you cancel {limit} hours or more before departure')
        else:
            parts.append(f'{int(share * 100)}% from {limit} to {prev} hours')
        prev = limit
    parts.append(f'nothing inside the last {prev} hours')
    return 'Refunds are ' + ', '.join(parts[:-1]) + ', and ' + parts[-1] + '. Your seat is released straight away.'


def open_at(hours, hhmm):
    hours = (hours or '').strip().lower()
    if hours.startswith('24'):
        return True
    m = re.match(r'(\d\d):(\d\d)\s*[-\u2013]\s*(\d\d):(\d\d)', hours)
    if not m:
        return True
    start, end = int(m.group(1)) * 60 + int(m.group(2)), int(m.group(3)) * 60 + int(m.group(4))
    h, mi = hhmm.split(':')
    cur = int(h) * 60 + int(mi)
    return start <= cur <= end if start <= end else (cur >= start or cur <= end)


def build_terminal_map(gate_no, gates, shops):
    """Schematic (not to scale) layout: entrance -> check-in -> security -> concourse -> gate."""
    gates = max(gates, 1)
    gate_no = min(max(gate_no or 1, 1), gates)
    conc_x0, conc_w = 330, 600
    gate_w = conc_w / gates
    gate_boxes = []
    for n in range(1, gates + 1):
        gate_boxes.append({'n': n, 'x': round(conc_x0 + (n - 1) * gate_w, 1), 'w': round(gate_w - 3, 1),
                           'mine': n == gate_no})
    gate_x = conc_x0 + (gate_no - 0.5) * gate_w
    gate_pos = (gate_no - 0.5) / gates * 100

    ordered = sorted(shops, key=lambda s: (0 if s['zone'] == 'landside' else 1, s['pos']))
    placed = []
    for i, s in enumerate(ordered, start=1):
        if s['zone'] == 'landside':
            x = 30 + s['pos'] / 100 * 250
            on_route = True
        else:
            x = conc_x0 + s['pos'] / 100 * conc_w
            on_route = s['pos'] <= gate_pos + 8
        near_gate = s['zone'] == 'airside' and abs(s['pos'] - gate_pos) <= 15
        placed.append(dict(s, n=i, x=round(x, 1), y=292 if i % 2 else 326,
                           on_route=on_route, near_gate=near_gate))

    points = [(20, 210), (110, 210), (300, 210), (gate_x, 210), (gate_x, 140)]
    length = sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))
    meters = int(round(length * 0.45, -1))
    minutes = max(1, math.ceil(meters / 75))
    return {'gates': gate_boxes, 'shops': placed, 'gate_x': round(gate_x, 1), 'conc_x0': conc_x0,
            'conc_w': conc_w, 'route': ' '.join(f'{x:.0f},{y:.0f}' for x, y in points),
            'meters': meters, 'minutes': minutes}


def build_quote(conn, flight, seat, meal_code, addon_codes):
    info = seat_info(seat)
    if not info:
        raise ValueError('Please choose a valid seat.')
    base = round(flight['price'] * info['multiplier'], 2)
    tax = round(base * TAX_RATE, 2)
    seat_fee = float(EXIT_ROW_FEE) if info['exit'] else 0.0

    meal = conn.execute('SELECT * FROM meals WHERE code = ?', (meal_code or 'NONE',)).fetchone()
    if not meal:
        raise ValueError('That meal option is not available.')
    included = info['class'] in INCLUDED_MEAL_CLASSES
    meal_price = 0.0 if included else float(meal['price'])

    addons, seen_groups = [], set()
    for code in dict.fromkeys(addon_codes or []):
        row = conn.execute('SELECT * FROM addons WHERE code = ?', (code,)).fetchone()
        if not row:
            raise ValueError('One of the selected add-ons is not available.')
        if row['grp']:
            if row['grp'] in seen_groups:
                raise ValueError('Please choose only one extra baggage option.')
            seen_groups.add(row['grp'])
        addons.append({'code': row['code'], 'name': row['name'], 'price': float(row['price'])})

    total = round(base + tax + seat_fee + meal_price + sum(a['price'] for a in addons), 2)
    return {'info': info, 'base': base, 'tax': tax, 'seat_fee': seat_fee,
            'meal': {'code': meal['code'], 'name': meal['name'], 'price': meal_price, 'included': included},
            'addons': addons, 'total': total}


def seats_taken(conn, f_id):
    rows = conn.execute("SELECT seat FROM tickets WHERE f_id = ? AND COALESCE(status,'CONFIRMED') = 'CONFIRMED'",
                        (f_id,)).fetchall()
    return [r['seat'] for r in rows]


def login_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if 'loggedin' not in session:
                return redirect(url_for('login'))
            if roles and session.get('role') not in roles:
                flash('That page is not available for your account type.', 'warning')
                return redirect(url_for('index'))
            return fn(*args, **kwargs)
        return wrapper
    return deco


def json_role_check(*roles):
    return 'loggedin' in session and session.get('role') in roles


def flight_rows(conn):
    """All flights with computed status, airports, seat counts."""
    flights = [dict(r) for r in conn.execute('SELECT * FROM flights ORDER BY departure').fetchall()]
    sold = {r['f_id']: r['n'] for r in conn.execute(
        "SELECT f_id, COUNT(*) n FROM tickets WHERE COALESCE(status,'CONFIRMED')='CONFIRMED' GROUP BY f_id")}
    airports = {r['city']: dict(r) for r in conn.execute('SELECT * FROM airports')}
    for f in flights:
        src = airports.get(f['source']) or airport_for(conn, f['source'])
        dst = airports.get(f['destination']) or airport_for(conn, f['destination'])
        f['src_iata'], f['dst_iata'] = src['iata'], dst['iata']
        f['domestic'] = is_domestic(src, dst)
        try:
            f['status'] = flight_status(f['departure'], f['arrival'])
        except ValueError:
            f['status'] = 'Scheduled'
        f['badge'] = STATUS_BADGE[f['status']]
        f['sold'] = sold.get(f['f_id'], 0)
        f['seats_left'] = TOTAL_SEATS - f['sold']
        f['bookable'] = f['status'] in ('Scheduled', 'Boarding') and f['seats_left'] > 0
    return flights


@app.before_request
def _prepare_schema():
    if not schema.is_ready():
        try:
            schema.ensure_schema(DB)
        except Exception as e:  # never block the app on a migration hiccup
            app.logger.error(f'schema: {e}')


@app.context_processor
def inject_globals():
    return {'APP_NAME': APP_NAME, 'current_year': datetime.now().year}


# ---------------------------------------------------------------------------
# Public pages and authentication
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    if 'loggedin' not in session:
        return render_template('index.html', **landing_data())

    role = session.get('role')
    with get_db() as conn:
        if role == 'PASSENGER':
            return passenger_home(conn)
        if role == 'STAFF':
            return staff_home(conn)
        if role == 'ADMIN':
            return admin_home(conn)
    return render_template('index.html', **landing_data())


def landing_data():
    data = {'routes': [], 'airline_count': 0, 'domestic_cities': 0, 'intl_cities': 0, 'featured': None}
    if not os.path.exists(DB):
        return data
    try:
        with get_db() as conn:
            flights = flight_rows(conn)
            airports = {r['city']: r['country'] for r in conn.execute('SELECT city, country FROM airports')}
    except sqlite3.Error:
        return data
    upcoming = [f for f in flights if f['status'] in ('Scheduled', 'Boarding')] or flights
    data['airline_count'] = len({f['flight_name'] for f in flights})
    cities = {f['source'] for f in flights} | {f['destination'] for f in flights}
    data['domestic_cities'] = sum(1 for c in cities if airports.get(c) == 'India')
    data['intl_cities'] = len(cities) - data['domestic_cities']
    seen, routes = set(), []
    for f in upcoming:
        key = (f['source'], f['destination'])
        if key in seen:
            continue
        seen.add(key)
        same = [x for x in upcoming if (x['source'], x['destination']) == key]
        routes.append({'source': f['source'], 'destination': f['destination'],
                       'src_iata': f['src_iata'], 'dst_iata': f['dst_iata'],
                       'from_price': min(x['price'] for x in same), 'airline': f['flight_name'],
                       'domestic': f['domestic']})
    data['routes'] = routes[:8]
    intl = [f for f in upcoming if not f['domestic']]
    feat = (intl or upcoming or [None])[0]
    if feat:
        dep, arr = parse_dt(feat['departure']), parse_dt(feat['arrival'])
        mins = int((arr - dep).total_seconds() // 60)
        feat['duration'] = f'{mins // 60}h {mins % 60:02d}m'
        data['featured'] = feat
    return data


def passenger_home(conn):
    me = conn.execute('SELECT * FROM passengers WHERE username = ?', (session['username'],)).fetchone()
    flights = [f for f in flight_rows(conn) if f['bookable']]
    trips = conn.execute('''SELECT t.*, f.flight_number, f.flight_name, f.source, f.destination, f.departure,
                                   f.terminal, f.gate
                            FROM tickets t LEFT JOIN flights f ON f.f_id = t.f_id
                            WHERE t.p_id = ? AND COALESCE(t.status,'CONFIRMED') = 'CONFIRMED'
                            ORDER BY f.departure''', (session['username'],)).fetchall()
    upcoming = [dict(t) for t in trips if t['departure'] and parse_dt(t['departure']) > datetime.now()]
    for t in upcoming:
        t['dep_dt'] = parse_dt(t['departure'])
    return render_template('passenger_dashboard/index.html', flights=flights, trips=upcoming,
                           trip_count=len(trips), me=me)


def staff_home(conn):
    flights = flight_rows(conn)
    today = datetime.now().strftime('%Y-%m-%d')
    today_flights = [f for f in flights if f['departure'].startswith(today)]
    next_up = [f for f in flights if f['status'] in ('Scheduled', 'Boarding')][:6]
    sold_total = sum(f['sold'] for f in flights)
    return render_template('employee_dashboard/index.html', flights=flights, today_flights=today_flights,
                           next_up=next_up, sold_total=sold_total, total_seats=TOTAL_SEATS,
                           now_label=datetime.now().strftime('%A %d %B %Y'))


def admin_home(conn):
    flights = flight_rows(conn)
    upcoming = [f for f in flights if f['status'] in ('Scheduled', 'Boarding')]
    users = sum(conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('passengers', 'employees', 'admin'))
    confirmed = conn.execute("SELECT COUNT(*) FROM tickets WHERE COALESCE(status,'CONFIRMED')='CONFIRMED'").fetchone()[0]
    cancelled = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='CANCELLED'").fetchone()[0]
    revenue = conn.execute('SELECT COALESCE(SUM(price - COALESCE(refund_amount,0)),0) FROM tickets').fetchone()[0]
    capacity = len(upcoming) * TOTAL_SEATS
    sold = sum(f['sold'] for f in upcoming)
    stats = {'users': users, 'flights_total': len(flights), 'flights_upcoming': len(upcoming),
             'confirmed': confirmed, 'cancelled': cancelled, 'revenue': revenue,
             'seats_sold': sold, 'seats_empty': capacity - sold, 'capacity': capacity,
             'load': round(sold / capacity * 100, 1) if capacity else 0}

    events = []
    for r in conn.execute('''SELECT t.created_at ts, t.passenger_name n, f.flight_number fn, f.source s, f.destination d
                             FROM tickets t LEFT JOIN flights f ON f.f_id = t.f_id
                             WHERE t.created_at IS NOT NULL ORDER BY t.created_at DESC LIMIT 8'''):
        events.append((r['ts'], 'bi-ticket-perforated', f"{r['n'] or 'A passenger'} booked {r['fn'] or 'a flight'}"
                       + (f" ({r['s']} to {r['d']})" if r['s'] else '')))
    for r in conn.execute('''SELECT t.cancelled_at ts, t.passenger_name n, f.flight_number fn
                             FROM tickets t LEFT JOIN flights f ON f.f_id = t.f_id
                             WHERE t.cancelled_at IS NOT NULL ORDER BY t.cancelled_at DESC LIMIT 8'''):
        events.append((r['ts'], 'bi-x-circle', f"{r['n'] or 'A passenger'} cancelled {r['fn'] or 'a booking'}"))
    for r in conn.execute('''SELECT created_at ts, flight_number fn, source s, destination d FROM flights
                             WHERE created_at IS NOT NULL ORDER BY created_at DESC LIMIT 8'''):
        events.append((r['ts'], 'bi-airplane', f"Flight {r['fn']} added ({r['s']} to {r['d']})"))
    for r in conn.execute('''SELECT created_at ts, username u FROM passengers
                             WHERE created_at IS NOT NULL ORDER BY created_at DESC LIMIT 8'''):
        events.append((r['ts'], 'bi-person-plus', f"New passenger registered: {r['u']}"))
    events.sort(key=lambda e: e[0], reverse=True)
    activity = [{'icon': i, 'text': t, 'when': humanize(ts)} for ts, i, t in events[:8]]

    backups = [f for f in os.listdir('backups') if f.endswith('.db')] if os.path.isdir('backups') else []
    last_backup = None
    try:
        with open('configs.json') as fh:
            last_backup = json.load(fh).get('system_health', {}).get('last_database_backup')
    except (OSError, ValueError):
        pass
    health = {'db_ok': True, 'db_size_kb': round(os.path.getsize(DB) / 1024, 1) if os.path.exists(DB) else 0,
              'backups': len(backups), 'last_backup': last_backup}
    return render_template('admin_dashboard/index.html', stats=stats, activity=activity, health=health)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if 'loggedin' in session:
            return redirect(url_for('index'))
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect(DB) as conn:
            c = conn.cursor()
            c.execute('''SELECT * FROM passengers WHERE username = ?''', (username,))
            user = c.fetchone()
            c.close()
        if user and bcrypt.checkpw(password.encode('utf-8'), user[2]):
            session['loggedin'] = True
            session['username'] = user[1]
            session['role'] = 'PASSENGER'
            return redirect(url_for('index'))
        return render_template('passenger/login.html', error_message='Invalid username or password')
    if 'loggedin' in session:
        return redirect(url_for('index'))
    return render_template('passenger/login.html')


@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('username', None)
    session.pop('role', None)
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        name = request.form['name']
        phone = request.form['phone']
        email = request.form['email']
        try:
            with sqlite3.connect(DB) as conn:
                c = conn.cursor()
                c.execute('''INSERT INTO passengers (username, password, name, phone, email, created_at)
                             VALUES (?, ?, ?, ?, ?, ?)''',
                          (username, bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()),
                           name, phone, email, now_str()))
                conn.commit()
                c.close()
        except sqlite3.IntegrityError:
            flash('That username is already taken. Please choose a different one.', 'danger')
            return render_template('passenger/register.html')
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('passenger/register.html')


@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if 'loggedin' in session:
            return redirect(url_for('index'))
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect(DB) as conn:
            c = conn.cursor()
            c.execute('''SELECT * FROM admin WHERE username = ?''', (username,))
            user = c.fetchone()
            c.close()
        if user and bcrypt.checkpw(password.encode('utf-8'), user[2]):
            session['loggedin'] = True
            session['username'] = user[1]
            session['role'] = 'ADMIN'
            return redirect(url_for('index'))
        return render_template('admin/login.html', message='Invalid username or password')
    if 'loggedin' in session:
        return redirect(url_for('index'))
    return render_template('admin/login.html')


@app.route('/employee_login', methods=['GET', 'POST'])
def employee_login():
    if request.method == 'POST':
        if 'loggedin' in session:
            return redirect(url_for('index'))
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect(DB) as conn:
            c = conn.cursor()
            c.execute('''SELECT * FROM employees WHERE username = ?''', (username,))
            user = c.fetchone()
            c.close()
        if user and bcrypt.checkpw(password.encode('utf-8'), user[2]):
            session['loggedin'] = True
            session['username'] = user[1]
            session['role'] = 'STAFF'
            return redirect(url_for('index'))
        return render_template('employee/login.html', message='Invalid username or password')
    if 'loggedin' in session:
        return redirect(url_for('index'))
    return render_template('employee/login.html')


# ---------------------------------------------------------------------------
# Flights
# ---------------------------------------------------------------------------
@app.route('/flights')
@login_required()
def flights():
    with get_db() as conn:
        rows = flight_rows(conn)
        if session['role'] == 'ADMIN':
            cls = {}
            for r in conn.execute('''SELECT f_id, class, COUNT(*) n FROM tickets
                                     WHERE COALESCE(status,'CONFIRMED')='CONFIRMED' GROUP BY f_id, class'''):
                cls.setdefault(r['f_id'], {})[r['class']] = r['n']
            rev = {r['f_id']: r['v'] for r in conn.execute(
                'SELECT f_id, SUM(price - COALESCE(refund_amount,0)) v FROM tickets GROUP BY f_id')}
            for f in rows:
                f['by_class'] = cls.get(f['f_id'], {})
                f['revenue'] = rev.get(f['f_id'], 0) or 0
                f['load'] = round(f['sold'] / TOTAL_SEATS * 100)
            return render_template('admin_dashboard/flights.html', flights=rows, class_capacity=CLASS_CAPACITY,
                                   total_seats=TOTAL_SEATS)
    return render_template('passenger_dashboard/flights.html', flights=rows)


@app.route('/admin/flight/<int:f_id>')
@login_required('ADMIN')
def admin_flight_detail(f_id):
    with get_db() as conn:
        flight = next((f for f in flight_rows(conn) if f['f_id'] == f_id), None)
        if not flight:
            abort(404)
        sold = {r['seat']: r['passenger_name'] for r in conn.execute(
            "SELECT seat, passenger_name FROM tickets WHERE f_id=? AND COALESCE(status,'CONFIRMED')='CONFIRMED'",
            (f_id,))}
    return render_template('admin_dashboard/flight_detail.html', flight=flight, layout=build_layout(),
                           sold=sold, total_seats=TOTAL_SEATS)


@app.route('/book_flight/<int:f_id>', methods=['GET', 'POST'])
@login_required('PASSENGER')
def book_flight(f_id):
    with get_db() as conn:
        flight = next((f for f in flight_rows(conn) if f['f_id'] == f_id), None)
        if not flight:
            abort(404)
        if not flight['bookable']:
            flash('This flight is no longer open for booking.' if flight['seats_left'] > 0
                  else 'This flight is fully booked.', 'warning')
            return redirect(url_for('flights'))

        if request.method == 'POST':
            try:
                name = request.form['passenger_name'].strip()
                age = int(request.form['passenger_age'])
                gender = request.form['passenger_gender']
                if not name or not (0 <= age <= 120) or gender not in ('M', 'F', 'O'):
                    raise ValueError('Please check the passenger details.')
                quote = build_quote(conn, flight, request.form.get('seat', ''), request.form.get('meal'),
                                    request.form.getlist('addons'))
                info = quote['info']
                conn.execute('BEGIN IMMEDIATE')
                if info['seat'] in seats_taken(conn, f_id):
                    conn.rollback()
                    raise ValueError(f"Seat {info['seat']} was just taken. Please pick another seat.")
                breakdown = {k: quote[k] for k in ('base', 'tax', 'seat_fee', 'meal', 'addons', 'total')}
                cur = conn.execute('''INSERT INTO tickets
                    (p_id, f_id, price, class, seat, travel_date, passenger_name, passenger_age,
                     passenger_gender, created_at, status, meal, breakdown, refund_amount)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0)''',
                    (session['username'], f_id, quote['total'], info['class'], info['seat'],
                     flight['departure'][:10], name, age, gender, now_str(), 'CONFIRMED',
                     quote['meal']['name'], json.dumps(breakdown)))
                conn.commit()
                flash('Booking confirmed. Your boarding pass is ready.', 'success')
                return redirect(url_for('boarding_pass', t_id=cur.lastrowid))
            except (ValueError, KeyError) as e:
                flash(str(e) if isinstance(e, ValueError) else 'Please complete every field.', 'danger')

        meals = [dict(r) for r in conn.execute('SELECT * FROM meals ORDER BY price, name')]
        addons = [dict(r) for r in conn.execute('SELECT * FROM addons ORDER BY grp DESC, price')]
        me = conn.execute('SELECT name FROM passengers WHERE username = ?', (session['username'],)).fetchone()
    config = {'basePrice': flight['price'], 'tax': TAX_RATE, 'exitFee': EXIT_ROW_FEE,
              'multipliers': {b['name']: b['multiplier'] for b in CLASS_BANDS},
              'includedMealClasses': list(INCLUDED_MEAL_CLASSES), 'meals': meals, 'addons': addons,
              'flightId': f_id, 'baggage': {k: v[0] for k, v in BAGGAGE_KG.items()}}
    return render_template('passenger_dashboard/book_flight.html', flight=flight, layout=build_layout(),
                           meals=meals, addons=addons, config=config, default_name=me['name'] if me else '',
                           included_classes=INCLUDED_MEAL_CLASSES, exit_fee=EXIT_ROW_FEE, tax_pct=int(TAX_RATE * 100))


def load_trip(conn, t_id):
    """Ticket + flight + airports for the signed-in passenger, or None."""
    t = conn.execute('SELECT * FROM tickets WHERE t_id = ? AND p_id = ?', (t_id, session['username'])).fetchone()
    if not t:
        return None
    f = conn.execute('SELECT * FROM flights WHERE f_id = ?', (t['f_id'],)).fetchone()
    return {'t': dict(t), 'f': dict(f) if f else None}


@app.route('/tickets')
@login_required('PASSENGER')
def tickets():
    with get_db() as conn:
        rows = conn.execute('''SELECT t.*, f.flight_number, f.flight_name, f.source, f.destination, f.departure,
                                      f.arrival, f.terminal, f.gate
                               FROM tickets t LEFT JOIN flights f ON f.f_id = t.f_id
                               WHERE t.p_id = ? ORDER BY t.t_id DESC''', (session['username'],)).fetchall()
        trips = []
        for r in rows:
            t = dict(r)
            t['status'] = t['status'] or 'CONFIRMED'
            t['pnr'] = pnr_for(t['t_id'])
            if t['departure']:
                dep = parse_dt(t['departure'])
                t['dep_dt'] = dep
                t['src_iata'] = airport_for(conn, t['source'])['iata']
                t['dst_iata'] = airport_for(conn, t['destination'])['iata']
                t['flight_state'] = flight_status(t['departure'], t['arrival'])
                allowed, amount, share, why = refund_for(t, dep)
                t['can_cancel'], t['refund_amount_quote'], t['refund_share'] = allowed, amount, int(share * 100)
            else:
                t['can_cancel'] = False
            trips.append(t)
    return render_template('passenger_dashboard/tickets.html', trips=trips, policy=refund_policy_text())


@app.route('/boarding_pass/<int:t_id>')
@login_required('PASSENGER')
def boarding_pass(t_id):
    with get_db() as conn:
        trip = load_trip(conn, t_id)
        if not trip or not trip['f']:
            flash('That ticket could not be found.', 'warning')
            return redirect(url_for('tickets'))
        t, f = trip['t'], trip['f']
        t['status'] = t['status'] or 'CONFIRMED'
        src, dst = airport_for(conn, f['source']), airport_for(conn, f['destination'])
        info = seat_info(t['seat']) or {'type': '-', 'row': 0, 'class': t['class'], 'exit': False}
        breakdown = json.loads(t['breakdown']) if t.get('breakdown') else None
        addon_names = [a['name'] for a in (breakdown or {}).get('addons', [])]
        dep, arr = parse_dt(f['departure']), parse_dt(f['arrival'])
        mins = int((arr - dep).total_seconds() // 60)
        allowed, refund_amount, share, why = refund_for(t, dep)
        checked, cabin = BAGGAGE_KG.get(t['class'], (15, 7))
        extra_kg = sum(int(re.search(r'(\d+) kg', a).group(1)) for a in addon_names if re.search(r'(\d+) kg', a))
        pnr = pnr_for(t['t_id'])
    pass_data = {
        't': t, 'f': f, 'src': src, 'dst': dst, 'seat': info, 'pnr': pnr, 'dep': dep, 'arr': arr,
        'duration': f'{mins // 60}h {mins % 60:02d}m',
        'boarding_time': (dep - timedelta(minutes=BOARDING_OPENS_MIN)).strftime('%H:%M'),
        'gate_close': (dep - timedelta(minutes=GATE_CLOSES_MIN)).strftime('%H:%M'),
        'group': boarding_group(info, addon_names), 'breakdown': breakdown, 'addon_names': addon_names,
        'checked_kg': checked + extra_kg, 'cabin_kg': cabin, 'extra_kg': extra_kg,
        'barcode': barcode_bars(f'{pnr}{t["t_id"]}{f["flight_number"]}{t["seat"]}'),
        'state': flight_status(f['departure'], f['arrival']), 'can_cancel': allowed,
        'refund_amount': refund_amount, 'refund_share': int(share * 100),
        'is_domestic': is_domestic(src, dst),
        'opens_min': BOARDING_OPENS_MIN, 'close_min': GATE_CLOSES_MIN,
    }
    return render_template('passenger_dashboard/boarding_pass.html', **pass_data)


@app.route('/airport_guide/<int:t_id>')
@login_required('PASSENGER')
def airport_guide(t_id):
    with get_db() as conn:
        trip = load_trip(conn, t_id)
        if not trip or not trip['f']:
            flash('That ticket could not be found.', 'warning')
            return redirect(url_for('tickets'))
        t, f = trip['t'], trip['f']
        src = airport_for(conn, f['source'])
        shops = [dict(r) for r in conn.execute('SELECT * FROM airport_shops WHERE city = ?', (f['source'],))]
        dep = parse_dt(f['departure'])
        board_hhmm = (dep - timedelta(minutes=BOARDING_OPENS_MIN)).strftime('%H:%M')
        for s in shops:
            s['open_at_boarding'] = open_at(s['hours'], board_hhmm)
        gate_no = schema.gate_number(f['gate'])
        tmap = build_terminal_map(gate_no, src['gates'], shops)
    return render_template('passenger_dashboard/airport_guide.html', t=t, f=f, src=src, tmap=tmap,
                           gate_no=gate_no, dep=dep, boarding_time=board_hhmm, pnr=pnr_for(t['t_id']),
                           shops=tmap['shops'], opens=BOARDING_OPENS_MIN)


@app.route('/cancel_ticket/<int:t_id>', methods=['POST'])
@login_required('PASSENGER')
def cancel_ticket(t_id):
    with get_db() as conn:
        trip = load_trip(conn, t_id)
        if not trip:
            flash('That ticket could not be found.', 'warning')
            return redirect(url_for('tickets'))
        t, f = trip['t'], trip['f']
        t['status'] = t['status'] or 'CONFIRMED'
        if not f:
            flash('This flight no longer exists, so the ticket cannot be cancelled online.', 'warning')
            return redirect(url_for('tickets'))
        allowed, amount, share, why = refund_for(t, parse_dt(f['departure']))
        if not allowed:
            flash(why, 'warning')
            return redirect(url_for('tickets'))
        conn.execute("UPDATE tickets SET status='CANCELLED', refund_amount=?, cancelled_at=? WHERE t_id=?",
                     (amount, now_str(), t_id))
        conn.commit()
    flash(f'Ticket cancelled. Refund of \u20b9{amount:,.2f} ({int(share * 100)}%) will go to your original payment method.',
          'success')
    return redirect(url_for('tickets'))


@app.route('/get_occupied_seats/<int:f_id>')
def get_occupied_seats(f_id):
    try:
        with get_db() as conn:
            return jsonify({'status': 'success', 'seats': seats_taken(conn, f_id)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


# ---------------------------------------------------------------------------
# Staff: flights, shops, manifests
# ---------------------------------------------------------------------------
def read_flight_form(data):
    number, name = data['flight_number'].strip(), data['flight_name'].strip()
    source, dest = data['source'].strip(), data['destination'].strip()
    if not all([number, name, source, dest]):
        raise ValueError('Please fill in every flight detail.')
    if source.lower() == dest.lower():
        raise ValueError('Source and destination must be different.')
    dep, arr = norm_dt(data['departure']), norm_dt(data['arrival'])
    if parse_dt(arr) <= parse_dt(dep):
        raise ValueError('Arrival must be after departure.')
    price = float(data['price'])
    if price <= 0:
        raise ValueError('Price must be greater than zero.')
    return number, name, source, dest, dep, arr, price


@app.route('/add_flight', methods=['GET', 'POST'])
@login_required('STAFF')
def add_flight():
    if request.method == 'POST':
        try:
            number, name, source, dest, dep, arr, price = read_flight_form(request.form)
        except (ValueError, KeyError) as e:
            flash(str(e) if isinstance(e, ValueError) else 'Please complete the form.', 'danger')
            return render_template('employee_dashboard/add_flight.html', form=request.form)
        with get_db() as conn:
            cur = conn.execute('''INSERT INTO flights (flight_number, flight_name, source, destination, departure,
                                  arrival, price, terminal, gate, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)''',
                               (number, name, source, dest, dep, arr, price,
                                request.form.get('terminal', '').strip(), request.form.get('gate', '').strip(),
                                now_str()))
            schema.assign_missing_gates(conn.cursor())
            conn.commit()
        flash(f'Flight {number} added.', 'success')
        return redirect(url_for('flights'))
    with get_db() as conn:
        cities = [r['city'] for r in conn.execute('SELECT city FROM airports ORDER BY city')]
    return render_template('employee_dashboard/add_flight.html', form={}, cities=cities)


@app.route('/delete_flight/<int:f_id>', methods=['POST'])
@login_required('STAFF')
def delete_flight(f_id):
    with get_db() as conn:
        n = conn.execute("SELECT COUNT(*) FROM tickets WHERE f_id=? AND COALESCE(status,'CONFIRMED')='CONFIRMED'",
                         (f_id,)).fetchone()[0]
        if n:
            flash(f'This flight has {n} confirmed booking(s) and cannot be deleted.', 'danger')
        else:
            conn.execute('DELETE FROM flights WHERE f_id = ?', (f_id,))
            conn.commit()
            flash('Flight deleted.', 'success')
    return redirect(url_for('flights'))


@app.route('/edit_flight/<int:f_id>', methods=['POST'])
def edit_flight(f_id):
    if not json_role_check('STAFF'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'})
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'No data provided'})
    try:
        number, name, source, dest, dep, arr, price = read_flight_form(data)
        with get_db() as conn:
            conn.execute('''UPDATE flights SET flight_number=?, flight_name=?, source=?, destination=?,
                            departure=?, arrival=?, price=?, terminal=?, gate=? WHERE f_id=?''',
                         (number, name, source, dest, dep, arr, price,
                          str(data.get('terminal', '')).strip(), str(data.get('gate', '')).strip(), f_id))
            schema.assign_missing_gates(conn.cursor())
            conn.commit()
        return jsonify({'status': 'success', 'message': 'Flight updated successfully'})
    except (ValueError, KeyError) as e:
        return jsonify({'status': 'error', 'message': str(e) if isinstance(e, ValueError) else 'Missing field'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/staff/shops')
@login_required('STAFF')
def staff_shops():
    with get_db() as conn:
        shops = [dict(r) for r in conn.execute('SELECT * FROM airport_shops ORDER BY city, zone, pos')]
        cities = [r['city'] for r in conn.execute('SELECT city FROM airports ORDER BY city')]
    return render_template('employee_dashboard/shops.html', shops=shops, cities=cities)


@app.route('/staff/shops/add', methods=['POST'])
@login_required('STAFF')
def staff_shop_add():
    try:
        name, city = request.form['name'].strip(), request.form['city'].strip()
        category, hours = request.form['category'].strip(), request.form['hours'].strip() or '24 hours'
        zone = request.form['zone']
        pos = int(request.form['pos'])
        if not name or not category or zone not in ('landside', 'airside') or not 0 <= pos <= 100:
            raise ValueError
        with get_db() as conn:
            if not conn.execute('SELECT 1 FROM airports WHERE city=?', (city,)).fetchone():
                raise ValueError
            conn.execute('INSERT INTO airport_shops (city, name, category, zone, pos, hours) VALUES (?,?,?,?,?,?)',
                         (city, name, category, zone, pos, hours))
            conn.commit()
        flash(f'{name} added to {city}.', 'success')
    except (ValueError, KeyError):
        flash('Please fill in the shop details correctly (position must be 0 to 100).', 'danger')
    return redirect(url_for('staff_shops'))


@app.route('/staff/shops/delete/<int:shop_id>', methods=['POST'])
@login_required('STAFF')
def staff_shop_delete(shop_id):
    with get_db() as conn:
        conn.execute('DELETE FROM airport_shops WHERE id = ?', (shop_id,))
        conn.commit()
    flash('Shop removed.', 'success')
    return redirect(url_for('staff_shops'))


def csv_response(filename, header, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return Response(buf.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})


@app.route('/manifest/<int:f_id>.csv')
@login_required('STAFF', 'ADMIN')
def manifest(f_id):
    with get_db() as conn:
        f = conn.execute('SELECT * FROM flights WHERE f_id = ?', (f_id,)).fetchone()
        if not f:
            abort(404)
        rows = conn.execute('''SELECT t_id, passenger_name, passenger_age, passenger_gender, seat, class, meal,
                                      breakdown FROM tickets WHERE f_id = ?
                               AND COALESCE(status,'CONFIRMED')='CONFIRMED' ORDER BY seat''', (f_id,)).fetchall()
    out = []
    for r in rows:
        addons = ', '.join(a['name'] for a in json.loads(r['breakdown'] or '{}').get('addons', []))
        out.append([f"TKT-{r['t_id']:04d}", pnr_for(r['t_id']), r['passenger_name'], r['passenger_age'],
                    r['passenger_gender'], r['seat'], r['class'], r['meal'] or '', addons])
    return csv_response(f"manifest_{f['flight_number']}.csv",
                        ['Ticket', 'PNR', 'Passenger', 'Age', 'Gender', 'Seat', 'Class', 'Meal', 'Add-ons'], out)


@app.route('/admin/export/<kind>.csv')
@login_required('ADMIN')
def admin_export(kind):
    with get_db() as conn:
        if kind == 'bookings':
            rows = conn.execute('''SELECT t.t_id, t.created_at, t.passenger_name, f.flight_number, f.source,
                                          f.destination, t.seat, t.class, t.price, t.status, t.refund_amount
                                   FROM tickets t LEFT JOIN flights f ON f.f_id=t.f_id ORDER BY t.t_id''').fetchall()
            return csv_response('bookings.csv', ['Ticket', 'Booked at', 'Passenger', 'Flight', 'From', 'To', 'Seat',
                                                 'Class', 'Price', 'Status', 'Refunded'],
                                [[f"TKT-{r['t_id']:04d}"] + list(r)[1:] for r in rows])
        if kind == 'occupancy':
            out = []
            for f in flight_rows(conn):
                out.append([f['flight_number'], f['flight_name'], f['source'], f['destination'], f['departure'],
                            f['status'], f['sold'], f['seats_left'], TOTAL_SEATS,
                            round(f['sold'] / TOTAL_SEATS * 100, 1)])
            return csv_response('occupancy.csv', ['Flight', 'Airline', 'From', 'To', 'Departure', 'Status',
                                                  'Seats sold', 'Seats empty', 'Capacity', 'Load %'], out)
    abort(404)


# ---------------------------------------------------------------------------
# Admin: backups, users, stats
# ---------------------------------------------------------------------------
@app.route('/backup_database')
def backup_database():
    if json_role_check('ADMIN'):
        import shutil
        os.makedirs('backups', exist_ok=True)
        stamp = datetime.now()
        backup_file = f'backups/database_backup_{stamp.strftime("%Y%m%d_%H%M%S")}.db'
        try:
            shutil.copy2(DB, backup_file)
            with open('configs.json', 'w') as f:
                json.dump({'system_health': {'last_database_backup': stamp.strftime('%Y-%m-%d %H:%M')}}, f)
            return jsonify({'status': 'success', 'message': f'Backup created successfully: {backup_file}',
                            'file': backup_file})
        except Exception as e:
            return jsonify({'status': 'error', 'message': f'Backup failed: {str(e)}'})
    return jsonify({'status': 'error', 'message': 'Unauthorized access'})


@app.route('/list_backups')
def list_backups():
    if json_role_check('ADMIN'):
        backups = []
        if os.path.exists('backups'):
            for file in sorted(os.listdir('backups')):
                if file.endswith('.db'):
                    st = os.stat(os.path.join('backups', file))
                    backups.append({'file': file, 'size': st.st_size,
                                    'created': datetime.fromtimestamp(st.st_ctime).strftime('%Y-%m-%d %H:%M:%S')})
        return jsonify({'status': 'success', 'backups': backups})
    return jsonify({'status': 'error', 'message': 'Unauthorized access'})


@app.route('/restore_backup/<filename>')
def restore_backup(filename):
    if json_role_check('ADMIN'):
        import shutil
        backup_file = os.path.join('backups', os.path.basename(filename))
        if os.path.exists(backup_file):
            try:
                os.makedirs('backups', exist_ok=True)
                shutil.copy2(DB, f'backups/pre_restore_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
                shutil.copy2(backup_file, DB)
                schema._ready = False
                return jsonify({'status': 'success', 'message': f'Database restored from {filename}'})
            except Exception as e:
                return jsonify({'status': 'error', 'message': f'Restore failed: {str(e)}'})
        return jsonify({'status': 'error', 'message': 'Backup file not found'})
    return jsonify({'status': 'error', 'message': 'Unauthorized access'})


@app.route('/admin/users')
def list_users():
    if json_role_check('ADMIN'):
        with get_db() as conn:
            users = []
            for r in conn.execute('SELECT id, username, name, email, phone FROM passengers'):
                users.append({'role': 'PASSENGER', **dict(r)})
            for r in conn.execute('SELECT id, username, name FROM employees'):
                users.append({'role': 'STAFF', **dict(r), 'email': None, 'phone': None})
            for r in conn.execute('SELECT id, username FROM admin'):
                users.append({'role': 'ADMIN', **dict(r), 'name': None, 'email': None, 'phone': None,
                              'self': r['username'] == session.get('username')})
        return jsonify({'status': 'success', 'users': users})
    return jsonify({'status': 'error', 'message': 'Unauthorized access'})


@app.route('/admin/add_user', methods=['POST'])
def add_user():
    if json_role_check('ADMIN'):
        data = request.get_json(silent=True) or {}
        role, username, password = data.get('role'), (data.get('username') or '').strip(), data.get('password')
        name, email, phone = data.get('name'), data.get('email'), data.get('phone')
        if role not in ('PASSENGER', 'STAFF', 'ADMIN') or not username or not password:
            return jsonify({'status': 'error', 'message': 'Role, username and password are required'})
        try:
            with sqlite3.connect(DB) as conn:
                c = conn.cursor()
                hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
                if role == 'PASSENGER':
                    c.execute('''INSERT INTO passengers (username, password, name, email, phone, created_at)
                                 VALUES (?, ?, ?, ?, ?, ?)''',
                              (username, hashed, name or username, email or '', phone or '', now_str()))
                elif role == 'STAFF':
                    c.execute('INSERT INTO employees (username, password, name) VALUES (?, ?, ?)',
                              (username, hashed, name or username))
                else:
                    c.execute('INSERT INTO admin (username, password) VALUES (?, ?)', (username, hashed))
                conn.commit()
            return jsonify({'status': 'success', 'message': f'{role} user added successfully'})
        except sqlite3.IntegrityError:
            return jsonify({'status': 'error', 'message': 'Username already exists'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})
    return jsonify({'status': 'error', 'message': 'Unauthorized access'})


@app.route('/admin/delete_user', methods=['POST'])
def delete_user():
    if json_role_check('ADMIN'):
        data = request.get_json(silent=True) or {}
        role, user_id = data.get('role'), data.get('id')
        try:
            with sqlite3.connect(DB) as conn:
                c = conn.cursor()
                if role == 'PASSENGER':
                    c.execute('DELETE FROM passengers WHERE id = ?', (user_id,))
                elif role == 'STAFF':
                    c.execute('DELETE FROM employees WHERE id = ?', (user_id,))
                elif role == 'ADMIN':
                    c.execute('SELECT username FROM admin WHERE id = ?', (user_id,))
                    row = c.fetchone()
                    if row and row[0] == session.get('username'):
                        return jsonify({'status': 'error', 'message': 'You cannot delete your own account'})
                    c.execute('SELECT COUNT(*) FROM admin')
                    if c.fetchone()[0] <= 1:
                        return jsonify({'status': 'error', 'message': 'Cannot delete the last admin user'})
                    c.execute('DELETE FROM admin WHERE id = ?', (user_id,))
                else:
                    return jsonify({'status': 'error', 'message': 'Unknown role'})
                conn.commit()
            return jsonify({'status': 'success', 'message': f'{role} user deleted successfully'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})
    return jsonify({'status': 'error', 'message': 'Unauthorized access'})


@app.route('/admin/reset_password', methods=['POST'])
def reset_password():
    if json_role_check('ADMIN'):
        data = request.get_json(silent=True) or {}
        role, user_id, new_password = data.get('role'), data.get('id'), data.get('password')
        table = {'PASSENGER': 'passengers', 'STAFF': 'employees', 'ADMIN': 'admin'}.get(role)
        if not table or not new_password:
            return jsonify({'status': 'error', 'message': 'A role and a new password are required'})
        try:
            with sqlite3.connect(DB) as conn:
                conn.execute(f'UPDATE {table} SET password = ? WHERE id = ?',
                             (bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()), user_id))
                conn.commit()
            return jsonify({'status': 'success', 'message': 'Password reset successfully'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})
    return jsonify({'status': 'error', 'message': 'Unauthorized access'})


@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'loggedin' not in session:
        return jsonify({'status': 'error', 'message': 'Please login first'})
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'No data provided'})
    password = data.get('password')
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()) if password else None
    try:
        with sqlite3.connect(DB) as conn:
            c = conn.cursor()
            role = session['role']
            if role == 'PASSENGER':
                if hashed:
                    c.execute('UPDATE passengers SET name=?, phone=?, email=?, password=? WHERE username=?',
                              (data.get('name'), data.get('phone'), data.get('email'), hashed, session['username']))
                else:
                    c.execute('UPDATE passengers SET name=?, phone=?, email=? WHERE username=?',
                              (data.get('name'), data.get('phone'), data.get('email'), session['username']))
            elif role == 'STAFF':
                if hashed:
                    c.execute('UPDATE employees SET name=?, password=? WHERE username=?',
                              (data.get('name'), hashed, session['username']))
                else:
                    c.execute('UPDATE employees SET name=? WHERE username=?', (data.get('name'), session['username']))
            elif role == 'ADMIN' and hashed:
                c.execute('UPDATE admin SET password=? WHERE username=?', (hashed, session['username']))
            conn.commit()
        return jsonify({'status': 'success', 'message': 'Profile updated successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/admin/stats/<period>')
def admin_stats(period):
    if not json_role_check('ADMIN'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'})
    try:
        with sqlite3.connect(DB) as conn:
            c = conn.cursor()
            today = datetime.now()
            labels, bookings, revenue = [], [], []
            net = 'COALESCE(SUM(price - COALESCE(refund_amount,0)), 0)'
            if period == 'daily':
                for i in range(6, -1, -1):
                    d = today - timedelta(days=i)
                    labels.append(d.strftime('%Y-%m-%d'))
                    c.execute(f'SELECT COUNT(*), {net} FROM tickets WHERE date(created_at) = date(?)',
                              (d.strftime('%Y-%m-%d'),))
                    n, total = c.fetchone()
                    bookings.append(n or 0)
                    revenue.append(float(total or 0))
            elif period == 'weekly':
                for i in range(3, -1, -1):
                    start = today - timedelta(weeks=i)
                    end = start + timedelta(days=6)
                    labels.append(f'{start.strftime("%Y-%m-%d")} to {end.strftime("%Y-%m-%d")}')
                    c.execute(f'SELECT COUNT(*), {net} FROM tickets WHERE date(created_at) BETWEEN date(?) AND date(?)',
                              (start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')))
                    n, total = c.fetchone()
                    bookings.append(n or 0)
                    revenue.append(float(total or 0))
            elif period == 'monthly':
                for i in range(5, -1, -1):
                    d = today.replace(day=1) - relativedelta(months=i)
                    labels.append(d.strftime('%B %Y'))
                    c.execute(f"SELECT COUNT(*), {net} FROM tickets WHERE strftime('%Y-%m', created_at) = ?",
                              (d.strftime('%Y-%m'),))
                    n, total = c.fetchone()
                    bookings.append(n or 0)
                    revenue.append(float(total or 0))
            else:
                return jsonify({'status': 'error', 'message': 'Unknown period'})
            return jsonify({'status': 'success', 'labels': labels, 'bookings': bookings, 'revenue': revenue})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


# ---------------------------------------------------------------------------
# Flight tracker
# ---------------------------------------------------------------------------
@app.route('/flight_tracker')
def flight_tracker():
    return render_template('flight_tracker.html')


@app.route('/get_active_flights')
def get_active_flights():
    try:
        now = datetime.now()
        out = []
        with get_db() as conn:
            for f in flight_rows(conn):
                dep, arr = parse_dt(f['departure']), parse_dt(f['arrival'])
                if not (dep <= now + timedelta(hours=12) and arr >= now - timedelta(hours=12)):
                    continue
                total = (arr - dep).total_seconds()
                if now < dep:
                    progress = 0
                elif now > arr:
                    progress = 1
                else:
                    progress = min((now - dep).total_seconds() / total, 1)
                status = 'In Air' if f['status'] == 'In Air' else ('Landed' if f['status'] == 'Landed' else 'Scheduled')
                out.append({'flight_number': str(escape(f['flight_number'])), 'flight_name': str(escape(f['flight_name'])),
                            'source': str(escape(f['source'])), 'destination': str(escape(f['destination'])),
                            'departure': f['departure'], 'arrival': f['arrival'],
                            'progress': progress, 'status': status,
                            'terminal': str(escape(f['terminal'] or '')), 'gate': str(escape(f['gate'] or ''))})
        return jsonify(out)
    except Exception as e:
        app.logger.error(f'Error in get_active_flights: {e}')
        return jsonify({'error': 'Internal server error'}), 500


schema.ensure_schema(DB)

if __name__ == '__main__':
    app.run(debug=True)
