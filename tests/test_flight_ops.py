from datetime import datetime, timedelta
from tests.base import AppTestCase, ADMIN, STAFF, main


class DelayCancelTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.login(ADMIN)
        self.fid = self.make_flight(72)
        self.row = lambda: self.sql('SELECT * FROM flights WHERE f_id=?', (self.fid,))[0]

    def test_delay_moves_times_and_marks_status(self):
        before = self.row()
        self.post(self.admin, f'/admin/flight/{self.fid}/status', data={'action': 'delay', 'minutes': '45', 'reason': 'Late aircraft'})
        after = self.row()
        shift = main.parse_dt(after['departure']) - main.parse_dt(before['departure'])
        self.assertEqual(shift, timedelta(minutes=45))
        self.assertEqual(main.parse_dt(after['arrival']) - main.parse_dt(before['arrival']), timedelta(minutes=45))
        self.assertEqual((after['ops_status'], after['delay_minutes'], after['ops_reason']), ('DELAYED', 45, 'Late aircraft'))
        with main.app.test_request_context():
            self.assertEqual(main.flight_status(after['departure'], after['arrival'], ops=after['ops_status']), 'Delayed')
        self.assertIn('flight_delay', self.audit_actions())

    def test_delays_add_up_and_can_be_cleared(self):
        original = self.row()['departure']
        for m in ('30', '20'):
            self.post(self.admin, f'/admin/flight/{self.fid}/status', data={'action': 'delay', 'minutes': m})
        self.assertEqual(self.row()['delay_minutes'], 50)
        self.post(self.admin, f'/admin/flight/{self.fid}/status', data={'action': 'clear'})
        r = self.row()
        self.assertEqual((r['departure'], r['ops_status'], r['delay_minutes']), (original, None, 0))

    def test_bad_delay_values_are_rejected(self):
        for bad in ('0', '4', '2000', 'abc', ''):
            self.post(self.admin, f'/admin/flight/{self.fid}/status', data={'action': 'delay', 'minutes': bad})
        self.assertIsNone(self.row()['ops_status'])

    def test_delayed_flight_is_still_bookable_and_shows_on_lists(self):
        self.post(self.admin, f'/admin/flight/{self.fid}/status', data={'action': 'delay', 'minutes': '60'})
        html = self.admin.get('/flights?q=TST-100').get_data(as_text=True)
        self.assertIn('Delayed', html)
        with main.get_db() as conn:
            f = next(x for x in main.flight_rows(conn) if x['f_id'] == self.fid)
        self.assertTrue(f['bookable'])

    def test_cancel_refunds_every_booking_in_full(self):
        t1 = self.book(self.fid, 'riya', '12A', price=5000)
        t2 = self.book(self.fid, 'amit', '12B', 'Amit Rao', price=4200)
        self.post(self.admin, f'/admin/flight/{self.fid}/status', data={'action': 'cancel', 'confirm': 'yes', 'reason': 'Weather'})
        self.assertEqual(self.row()['ops_status'], 'CANCELLED')
        for t_id, price in ((t1, 5000), (t2, 4200)):
            t = self.sql('SELECT * FROM tickets WHERE t_id=?', (t_id,))[0]
            self.assertEqual((t['status'], t['refund_amount']), ('CANCELLED', price))
        self.assertIn('flight_cancel', self.audit_actions())

    def test_cancel_needs_the_confirmation_box(self):
        t = self.book(self.fid)
        self.post(self.admin, f'/admin/flight/{self.fid}/status', data={'action': 'cancel'})
        self.assertIsNone(self.row()['ops_status'])
        self.assertEqual(self.sql('SELECT status FROM tickets WHERE t_id=?', (t,))[0]['status'], 'CONFIRMED')

    def test_cancelled_flight_cannot_be_booked_or_changed_again(self):
        self.post(self.admin, f'/admin/flight/{self.fid}/status', data={'action': 'cancel', 'confirm': 'yes'})
        p = self.register_passenger('bob')
        self.assertEqual(p.get(f'/book_flight/{self.fid}').status_code, 302)
        self.post(self.admin, f'/admin/flight/{self.fid}/status', data={'action': 'delay', 'minutes': '30'})
        self.assertEqual(self.row()['ops_status'], 'CANCELLED')

    def test_cancelled_flight_is_hidden_from_tracker(self):
        fid = self.make_flight(-1, 3, 'TRK-1')
        names = lambda: [f['flight_number'] for f in main.app.test_client().get('/get_active_flights').get_json()]
        self.assertIn('TRK-1', names())
        self.sql("UPDATE flights SET ops_status='CANCELLED' WHERE f_id=?", (fid,))
        self.assertNotIn('TRK-1', names())

    def test_flight_in_the_air_cannot_be_delayed(self):
        fid = self.make_flight(-1, 3, 'AIR-1')
        self.post(self.admin, f'/admin/flight/{fid}/status', data={'action': 'delay', 'minutes': '30'})
        self.assertIsNone(self.sql('SELECT ops_status FROM flights WHERE f_id=?', (fid,))[0]['ops_status'])

    def test_passenger_sees_delay_and_cancellation(self):
        p = self.register_passenger()
        self.book(self.fid)
        self.post(self.admin, f'/admin/flight/{self.fid}/status', data={'action': 'delay', 'minutes': '40', 'reason': 'Fog'})
        html = p.get('/tickets').get_data(as_text=True)
        self.assertIn('delayed by 40 minutes', html)
        self.assertIn('Fog', html)
        t_id = self.sql('SELECT t_id FROM tickets')[0]['t_id']
        self.assertIn('delayed by 40 minutes', p.get(f'/boarding_pass/{t_id}').get_data(as_text=True))
        self.post(self.admin, f'/admin/flight/{self.fid}/status', data={'action': 'cancel', 'confirm': 'yes', 'reason': 'Strike'})
        html = p.get('/tickets').get_data(as_text=True)
        self.assertIn('Flight cancelled by the airline', html)
        self.assertIn('Strike', html)

    def test_flights_with_bookings_cannot_be_deleted(self):
        self.book(self.fid)
        self.post(self.admin, f'/delete_flight/{self.fid}')
        self.assertEqual(len(self.sql('SELECT 1 FROM flights WHERE f_id=?', (self.fid,))), 1)
        self.post(self.admin, f'/admin/flight/{self.fid}/status', data={'action': 'cancel', 'confirm': 'yes'})
        self.post(self.admin, f'/delete_flight/{self.fid}')  # cancelled bookings are still history
        self.assertEqual(len(self.sql('SELECT 1 FROM flights WHERE f_id=?', (self.fid,))), 1)

    def test_empty_flight_can_be_deleted(self):
        self.post(self.admin, f'/delete_flight/{self.fid}')
        self.assertEqual(len(self.sql('SELECT 1 FROM flights WHERE f_id=?', (self.fid,))), 0)
