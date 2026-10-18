from tests.base import AppTestCase, ADMIN, STAFF


class StaffScheduleTests(AppTestCase):
    def test_staff_only_see_assigned_flights(self):
        c = self.login(STAFF)
        mine = {r['staff_username'] for r in self.sql('SELECT staff_username FROM staff_assignments')}
        self.assertEqual(mine, {'staff'})
        n = len(self.sql("SELECT 1 FROM staff_assignments WHERE staff_username='staff'"))
        html = c.get('/flights').get_data(as_text=True)
        self.assertEqual(html.count('/staff/flight/'), n)

    def test_unassigned_flight_is_blocked_everywhere(self):
        c = self.login(STAFF)
        fid = self.far_flight()
        self.assertEqual(c.get(f'/staff/flight/{fid}').status_code, 302)
        self.assertEqual(c.get(f'/manifest/{fid}.csv').status_code, 302)
        t = self.book(self.far_flight())
        self.assertEqual(self.post(c, f'/staff/ticket/{t}/checkin').status_code, 302)
        self.assertIsNone(self.sql('SELECT checked_in_at FROM tickets WHERE t_id=?', (t,))[0]['checked_in_at'])

    def test_admin_assigns_and_unassigns(self):
        a, s = self.login(ADMIN), self.login(STAFF)
        fid = self.far_flight()
        self.assertEqual(s.get(f'/staff/flight/{fid}').status_code, 302)
        self.post(a, f'/admin/flight/{fid}/staff', data={'staff': ['staff', 'ghost']})
        rows = [r['staff_username'] for r in self.sql('SELECT staff_username FROM staff_assignments WHERE f_id=?', (fid,))]
        self.assertEqual(rows, ['staff'])  # unknown usernames are ignored
        self.assertEqual(s.get(f'/staff/flight/{fid}').status_code, 200)
        self.post(a, f'/admin/flight/{fid}/staff', data={})
        self.assertEqual(s.get(f'/staff/flight/{fid}').status_code, 302)

    def test_admin_can_open_any_flight_passengers(self):
        self.assertEqual(self.login(ADMIN).get(f'/staff/flight/{self.far_flight()}').status_code, 200)

    def test_passenger_list_shows_who_booked_with_contact(self):
        fid = self.make_flight(50)
        self.assign(fid)
        self.book(fid)
        html = self.login(STAFF).get(f'/staff/flight/{fid}').get_data(as_text=True)
        for text in ('Riya Shah', '9800000000', 'riya@example.com', '12A', '@riya'):
            self.assertIn(text, html)

    def test_manifest_includes_booker(self):
        fid = self.make_flight(50)
        self.assign(fid)
        self.book(fid)
        csv_text = self.login(STAFF).get(f'/manifest/{fid}.csv').get_data(as_text=True)
        self.assertIn('Booked by', csv_text)
        self.assertIn('riya@example.com', csv_text)

    def test_deleting_flight_and_staff_cleans_assignments(self):
        a = self.login(ADMIN)
        fid = self.make_flight(60)
        self.assign(fid)
        self.post(a, f'/delete_flight/{fid}')
        self.assertEqual(len(self.sql('SELECT 1 FROM staff_assignments WHERE f_id=?', (fid,))), 0)
        sid = self.sql("SELECT id FROM employees WHERE username='staff'")[0]['id']
        self.post(a, '/admin/delete_user', json={'role': 'STAFF', 'id': sid})
        self.assertEqual(len(self.sql("SELECT 1 FROM staff_assignments WHERE staff_username='staff'")), 0)
