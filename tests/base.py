"""Shared test setup. Every test runs against a fresh throwaway database in a temp folder,
so running the tests never touches your real database.db."""
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix='aeronexus_test_')
os.chdir(TMP)
os.environ['AERONEXUS_SECRET_KEY'] = 'test-secret-key-for-unit-tests-only-0123456789'
os.environ.pop('AERONEXUS_STRICT_BOARDING', None)

import main  # noqa: E402
import schema  # noqa: E402
from database import db as dbmod  # noqa: E402

dbmod.DB_PATH = os.path.join(TMP, 'database.db')
STAFF = ('/employee_login', 'staff', 'staff123')
ADMIN = ('/admin_login', 'admin', 'admin123')


class AppTestCase(unittest.TestCase):
    def setUp(self):
        for name in ('database.db', 'database.db-journal'):
            if os.path.exists(os.path.join(TMP, name)):
                os.remove(os.path.join(TMP, name))
        dbmod.init_db()
        schema._ready = False
        schema.ensure_schema(main.DB)
        main.LOGIN_FAILS.clear()
        main.STRICT_WINDOWS = False
        main.app.config['TESTING'] = True

    # ---- helpers ----
    def sql(self, query, args=()):
        conn = sqlite3.connect(main.DB)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(query, args).fetchall()
            conn.commit()
            return rows
        finally:
            conn.close()

    def token(self, client, url='/'):
        html = client.get(url).get_data(as_text=True)
        return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)

    def login(self, who):
        path, user, pw = who
        c = main.app.test_client()
        c.post(path, data={'username': user, 'password': pw, 'csrf_token': self.token(c, path)})
        return c

    def post(self, c, url, data=None, json=None, expect_json=False):
        tok = self.token(c, '/')
        if json is not None or expect_json:
            return c.post(url, json=json or {}, headers={'X-CSRF-Token': tok})
        return c.post(url, data={**(data or {}), 'csrf_token': tok})

    def register_passenger(self, username='riya', password='pass123'):
        c = main.app.test_client()
        c.post('/register', data={'username': username, 'password': password, 'name': 'Riya Shah',
                                  'phone': '9800000000', 'email': 'riya@example.com',
                                  'csrf_token': self.token(c, '/register')})
        return self.login(('/login', username, password))

    def make_flight(self, start_hours, duration_hours=2, number='TST-100'):
        dep = datetime.now() + timedelta(hours=start_hours)
        arr = dep + timedelta(hours=duration_hours)
        conn = sqlite3.connect(main.DB)
        cur = conn.execute('''INSERT INTO flights (flight_number, flight_name, source, destination, departure,
                              arrival, price, created_at) VALUES (?,?,?,?,?,?,?,?)''',
                           (number, 'Test Air', 'Mumbai', 'Delhi', dep.strftime('%Y-%m-%d %H:%M'),
                            arr.strftime('%Y-%m-%d %H:%M'), 5000, main.now_str()))
        conn.commit()
        f_id = cur.lastrowid
        schema.assign_missing_gates(conn.cursor())
        conn.commit()
        conn.close()
        return f_id

    def book(self, f_id, username='riya', seat='12A', name='Riya Shah', price=5000):
        conn = sqlite3.connect(main.DB)
        if not conn.execute('SELECT 1 FROM passengers WHERE username=?', (username,)).fetchone():
            conn.execute('INSERT INTO passengers (username,password,name,phone,email) VALUES (?,?,?,?,?)',
                         (username, b'x', name, '9800000000', f'{username}@example.com'))
        cur = conn.execute('''INSERT INTO tickets (p_id,f_id,price,class,seat,passenger_name,passenger_age,
                              passenger_gender,status,created_at,breakdown,meal)
                              VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                           (username, f_id, price, 'Economy', seat, name, 28, 'F', 'CONFIRMED', main.now_str(), '{}', 'VEG'))
        conn.commit()
        t_id = cur.lastrowid
        conn.close()
        return t_id

    def assign(self, f_id, username='staff'):
        self.sql('INSERT OR IGNORE INTO staff_assignments VALUES (?,?)', (username, f_id))

    def far_flight(self):
        """A seeded flight that departs furthest in the future (so it is bookable and not assigned to staff)."""
        return self.sql('SELECT f_id FROM flights ORDER BY departure DESC LIMIT 1')[0]['f_id']

    def audit_actions(self):
        return [r['action'] for r in self.sql('SELECT action FROM audit_log ORDER BY id')]
