from tests.base import AppTestCase, ADMIN, STAFF, main


class CheckInBoardingTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.fid = self.make_flight(30)
        self.assign(self.fid)
        self.t = self.book(self.fid)
        self.staff = self.login(STAFF)
        self.state = lambda: tuple(self.sql('SELECT checked_in_at, boarded_at FROM tickets WHERE t_id=?', (self.t,))[0])
        self.act = lambda action, who=None: self.post(who or self.staff, f'/staff/ticket/{self.t}/{action}')

    def test_full_flow_checkin_board_undo(self):
        self.act('checkin')
        ci, bo = self.state()
        self.assertTrue(ci and not bo)
        self.act('board')
        self.assertTrue(all(self.state()))
        self.act('undo')
        ci, bo = self.state()
        self.assertTrue(ci and not bo)
        self.act('undo')
        self.assertEqual(self.state(), (None, None))
        self.assertEqual([a for a in self.audit_actions() if a != 'login'], ['checkin', 'board', 'undo_board', 'undo_checkin'])

    def test_cannot_board_before_check_in(self):
        self.act('board')
        self.assertEqual(self.state(), (None, None))

    def test_counts_show_on_schedule_and_passenger_page(self):
        self.act('checkin')
        self.act('board')
        with main.get_db() as conn:
            f = next(x for x in main.flight_rows(conn) if x['f_id'] == self.fid)
        self.assertEqual((f['checked_in'], f['boarded']), (1, 1))
        self.assertIn('Boarded', self.staff.get(f'/staff/flight/{self.fid}').get_data(as_text=True))

    def test_other_staff_cannot_check_in_unassigned_flight(self):
        self.sql('DELETE FROM staff_assignments WHERE f_id=?', (self.fid,))
        self.act('checkin')
        self.assertEqual(self.state(), (None, None))

    def test_admin_may_check_in_any_flight(self):
        self.sql('DELETE FROM staff_assignments WHERE f_id=?', (self.fid,))
        self.act('checkin', self.login(ADMIN))
        self.assertTrue(self.state()[0])

    def test_closed_for_cancelled_and_departed_flights(self):
        air = self.make_flight(-1, 3, 'AIR-2')
        self.assign(air)
        t = self.book(air, 'amit', '3A', 'Amit Rao')
        self.post(self.staff, f'/staff/ticket/{t}/checkin')
        self.assertIsNone(self.sql('SELECT checked_in_at FROM tickets WHERE t_id=?', (t,))[0]['checked_in_at'])
        self.sql("UPDATE flights SET ops_status='CANCELLED' WHERE f_id=?", (self.fid,))
        self.act('checkin')
        self.assertEqual(self.state(), (None, None))

    def test_cancelled_booking_cannot_check_in(self):
        self.sql("UPDATE tickets SET status='CANCELLED' WHERE t_id=?", (self.t,))
        self.act('checkin')
        self.assertEqual(self.state(), (None, None))

    def test_unknown_action_is_404(self):
        self.assertEqual(self.post(self.staff, f'/staff/ticket/{self.t}/explode').status_code, 404)

    def test_boarded_passenger_cannot_cancel_ticket(self):
        p = self.login(('/login', 'riya', 'x'))  # booked via SQL with a dummy hash, so log in properly:
        p = self.register_passenger('carol')
        t = self.book(self.fid, 'carol', '14C', 'Carol Dsouza')
        self.post(self.staff, f'/staff/ticket/{t}/checkin')
        self.post(self.staff, f'/staff/ticket/{t}/board')
        self.post(p, f'/cancel_ticket/{t}')
        self.assertEqual(self.sql('SELECT status FROM tickets WHERE t_id=?', (t,))[0]['status'], 'CONFIRMED')

    def test_passenger_sees_check_in_status(self):
        p = self.register_passenger('dave')
        t = self.book(self.fid, 'dave', '13A', 'Dave Roy')
        self.post(self.staff, f'/staff/ticket/{t}/checkin')
        self.assertIn('checked in', p.get(f'/boarding_pass/{t}').get_data(as_text=True))

    def test_strict_mode_enforces_windows(self):
        main.STRICT_WINDOWS = True
        far = self.make_flight(100, 2, 'FAR-1')
        self.assign(far)
        t = self.book(far, 'erin', '5A', 'Erin Das')
        self.post(self.staff, f'/staff/ticket/{t}/checkin')  # more than 24h out
        self.assertIsNone(self.sql('SELECT checked_in_at FROM tickets WHERE t_id=?', (t,))[0]['checked_in_at'])
        self.sql("UPDATE tickets SET checked_in_at='2026-01-01 00:00:00' WHERE t_id=?", (t,))
        self.post(self.staff, f'/staff/ticket/{t}/board')  # boarding not open yet
        self.assertIsNone(self.sql('SELECT boarded_at FROM tickets WHERE t_id=?', (t,))[0]['boarded_at'])
