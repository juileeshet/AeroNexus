from tests.base import AppTestCase, ADMIN, STAFF, main


class AuditLogTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.login(ADMIN)

    def test_admin_actions_are_recorded_with_actor(self):
        self.post(self.admin, '/add_flight', data={
            'flight_number': 'AUD-1', 'flight_name': 'Audit Air', 'source': 'Mumbai', 'destination': 'Delhi',
            'departure': '2030-01-01T10:00', 'arrival': '2030-01-01T12:00', 'price': '4000'})
        fid = self.sql("SELECT f_id FROM flights WHERE flight_number='AUD-1'")[0]['f_id']
        self.post(self.admin, f'/admin/flight/{fid}/staff', data={'staff': ['staff']})
        self.post(self.admin, '/admin/shops/add', data={'name': 'Chai Stop', 'city': 'Mumbai', 'category': 'Cafe', 'zone': 'airside', 'pos': 40, 'hours': '24 hours'})
        self.post(self.admin, '/admin/add_user', json={'role': 'STAFF', 'username': 'neha', 'password': 'secret1', 'name': 'Neha'})
        self.post(self.admin, '/backup_database', json={})
        acts = self.audit_actions()
        for a in ('login', 'flight_add', 'staff_assign', 'shop_add', 'user_add', 'backup_create'):
            self.assertIn(a, acts)
        row = self.sql("SELECT * FROM audit_log WHERE action='flight_add'")[0]
        self.assertEqual((row['actor'], row['role'], row['target']), ('admin', 'ADMIN', 'AUD-1'))

    def test_password_events_are_logged_without_passwords(self):
        self.post(self.admin, '/change_password', json={'current_password': 'admin123', 'new_password': 'brandnew1'})
        acts = self.audit_actions()
        self.assertIn('password_change', acts)
        for r in self.sql('SELECT * FROM audit_log'):
            self.assertNotIn('brandnew1', ' '.join(str(v) for v in tuple(r)))

    def test_page_is_admin_only(self):
        self.assertEqual(self.login(STAFF).get('/admin/audit').status_code, 302)
        self.assertEqual(self.admin.get('/admin/audit').status_code, 200)

    def test_filters_and_csv_export(self):
        fid = self.make_flight(40)
        self.post(self.admin, f'/admin/flight/{fid}/status', data={'action': 'delay', 'minutes': '30'})
        html = self.admin.get('/admin/audit?action=flight_delay').get_data(as_text=True)
        self.assertIn('flight_delay', html)
        self.assertNotIn('<span class="code">login</span>', html)
        none = self.admin.get('/admin/audit?q=zzz-nothing').get_data(as_text=True)
        self.assertIn('Nothing logged', none)
        csv_text = self.admin.get('/admin/export/audit.csv?action=flight_delay').get_data(as_text=True)
        self.assertIn('When,Who,Role,Action,Target,Detail', csv_text)
        self.assertIn('flight_delay', csv_text)
        self.assertNotIn('login', csv_text.split('\n', 1)[1])

    def test_staff_check_in_is_attributed_to_staff(self):
        fid = self.make_flight(30)
        self.assign(fid)
        t = self.book(fid)
        self.post(self.login(STAFF), f'/staff/ticket/{t}/checkin')
        row = self.sql("SELECT * FROM audit_log WHERE action='checkin'")[0]
        self.assertEqual((row['actor'], row['role']), ('staff', 'STAFF'))


class SearchAndPaginationTests(AppTestCase):
    def test_admin_flights_are_paged(self):
        a = self.login(ADMIN)
        total = len(self.sql('SELECT 1 FROM flights'))
        self.assertGreater(total, 12)
        p1 = a.get('/flights').get_data(as_text=True)
        p2 = a.get('/flights?page=2').get_data(as_text=True)
        self.assertEqual(p1.count('data-flight-id='), 12)
        self.assertEqual(p2.count('data-flight-id='), total - 12)
        self.assertIn('Page 1 of 2', p1)

    def test_page_number_is_clamped(self):
        a = self.login(ADMIN)
        self.assertEqual(a.get('/flights?page=999').status_code, 200)
        self.assertEqual(a.get('/flights?page=-4').status_code, 200)
        self.assertEqual(a.get('/flights?page=abc').status_code, 200)

    def test_search_and_status_filter(self):
        a = self.login(ADMIN)
        fid = self.make_flight(80, 2, 'ZZ-777')
        html = a.get('/flights?q=zz-777').get_data(as_text=True)
        self.assertEqual(html.count('data-flight-id='), 1)
        self.assertIn('ZZ-777', html)
        self.sql("UPDATE flights SET ops_status='CANCELLED' WHERE f_id=?", (fid,))
        only = a.get('/flights?status=Cancelled').get_data(as_text=True)
        self.assertEqual(only.count('data-flight-id='), 1)
        self.assertIn('No flights match', a.get('/flights?q=nothing-here-xyz').get_data(as_text=True))

    def test_staff_passenger_search(self):
        fid = self.make_flight(50)
        self.assign(fid)
        self.book(fid, 'riya', '12A', 'Riya Shah')
        self.book(fid, 'amit', '12B', 'Amit Rao')
        s = self.login(STAFF)
        html = s.get(f'/staff/flight/{fid}?q=amit').get_data(as_text=True)
        self.assertIn('Amit Rao', html)
        self.assertNotIn('Riya Shah', html)
        self.assertIn('No passengers match', s.get(f'/staff/flight/{fid}?q=nobody').get_data(as_text=True))

    def test_passenger_list_is_paged(self):
        fid = self.make_flight(50)
        self.assign(fid)
        for i in range(23):
            self.book(fid, f'user{i}', f'{i // 6 + 1}{"ABCDEF"[i % 6]}', f'Pax {i:02d}')
        s = self.login(STAFF)
        self.assertEqual(s.get(f'/staff/flight/{fid}').get_data(as_text=True).count('<td class="code">'), 20)
        self.assertEqual(s.get(f'/staff/flight/{fid}?page=2').get_data(as_text=True).count('<td class="code">'), 3)

    def test_audit_log_is_paged(self):
        a = self.login(ADMIN)
        for i in range(30):
            self.sql("INSERT INTO audit_log (ts, actor, role, action, target) VALUES ('2030-01-01 00:00:00','admin','ADMIN','x',?)", (f't{i}',))
        self.assertIn('Page 1 of 2', a.get('/admin/audit').get_data(as_text=True))


class IntegrityTests(AppTestCase):
    def test_foreign_keys_are_enforced(self):
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            with main.get_db() as conn:
                conn.execute('''INSERT INTO tickets (p_id,f_id,price,class,seat) VALUES ('nobody', 99999, 1, 'Economy', '1A')''')

    def test_passenger_with_bookings_cannot_be_deleted(self):
        fid = self.make_flight(50)
        self.book(fid)
        pid = self.sql("SELECT id FROM passengers WHERE username='riya'")[0]['id']
        r = self.post(self.login(ADMIN), '/admin/delete_user', json={'role': 'PASSENGER', 'id': pid})
        self.assertIn('bookings on record', r.get_json()['message'])
        self.assertEqual(len(self.sql("SELECT 1 FROM passengers WHERE username='riya'")), 1)

    def test_real_booking_flow_still_works(self):
        p = self.register_passenger('frank')
        fid = self.far_flight()
        r = self.post(p, f'/book_flight/{fid}', data={'passenger_name': 'Frank Lee', 'passenger_age': '30',
                                                      'passenger_gender': 'M', 'seat': '10C', 'meal': 'VEG'})
        self.assertEqual(r.status_code, 302)
        t = self.sql("SELECT * FROM tickets WHERE p_id='frank'")[0]
        self.assertEqual((t['seat'], t['status']), ('10C', 'CONFIRMED'))
        self.assertEqual(p.get(f'/boarding_pass/{t["t_id"]}').status_code, 200)
        self.post(p, f'/cancel_ticket/{t["t_id"]}')
        self.assertEqual(self.sql('SELECT status FROM tickets WHERE t_id=?', (t['t_id'],))[0]['status'], 'CANCELLED')
