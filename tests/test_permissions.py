from tests.base import AppTestCase, ADMIN, STAFF, main


class RolePermissionTests(AppTestCase):
    def test_anonymous_users_are_sent_to_login(self):
        c = main.app.test_client()
        for url in ('/add_flight', '/admin/shops', '/admin/audit', '/flights', '/staff/flight/1'):
            self.assertEqual(c.get(url).status_code, 302, url)

    def test_staff_cannot_use_admin_pages(self):
        c = self.login(STAFF)
        for url in ('/add_flight', '/admin/shops', '/admin/audit', '/admin/flight/1/staff', '/admin/flight/1/status'):
            r = c.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertTrue(r.headers['Location'].endswith('/'), url)

    def test_staff_cannot_change_data(self):
        c = self.login(STAFF)
        fid = self.far_flight()
        self.assertEqual(self.post(c, f'/delete_flight/{fid}').status_code, 302)
        self.assertEqual(len(self.sql('SELECT 1 FROM flights WHERE f_id=?', (fid,))), 1)
        r = self.post(c, '/edit_flight/1', json={'flight_number': 'X'})
        self.assertEqual(r.get_json()['message'], 'Unauthorized')
        self.post(c, '/admin/shops/add', data={'name': 'Hack', 'city': 'Mumbai', 'category': 'x', 'zone': 'airside', 'pos': 5, 'hours': '24 hours'})
        self.assertEqual(len(self.sql("SELECT 1 FROM airport_shops WHERE name='Hack'")), 0)
        self.post(c, f'/admin/flight/{fid}/status', data={'action': 'cancel', 'confirm': 'yes'})
        self.assertIsNone(self.sql('SELECT ops_status FROM flights WHERE f_id=?', (fid,))[0]['ops_status'])

    def test_staff_navigation_has_no_management_links(self):
        html = self.login(STAFF).get('/').get_data(as_text=True)
        for label in ('Add Flight', 'Airport Shops', 'Audit Log'):
            self.assertNotIn(label, html)
        self.assertIn('My Schedule', html)

    def test_admin_can_use_admin_pages(self):
        c = self.login(ADMIN)
        for url in ('/add_flight', '/admin/shops', '/admin/audit', '/flights', '/admin/flight/1/staff', '/admin/flight/1/status'):
            self.assertEqual(c.get(url).status_code, 200, url)
        html = c.get('/').get_data(as_text=True)
        for label in ('Add Flight', 'Airport Shops', 'Audit Log'):
            self.assertIn(label, html)

    def test_passenger_cannot_reach_staff_or_admin_pages(self):
        c = self.register_passenger()
        for url in ('/add_flight', '/admin/shops', '/admin/audit', '/staff/flight/1', '/manifest/1.csv'):
            self.assertEqual(c.get(url).status_code, 302, url)
        self.assertEqual(self.post(c, '/staff/ticket/1/checkin').status_code, 302)

    def test_admin_cannot_book_flights(self):
        c = self.login(ADMIN)
        self.assertEqual(c.get(f'/book_flight/{self.far_flight()}').status_code, 302)
