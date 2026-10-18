import os
from tests.base import AppTestCase, ADMIN, STAFF, main


class SecurityTests(AppTestCase):
    def test_secret_key_is_not_the_old_hardcoded_value(self):
        self.assertNotEqual(main.app.secret_key, 'secret_key')

    def test_post_without_csrf_token_is_rejected(self):
        c = main.app.test_client()
        r = c.post('/employee_login', data={'username': 'staff', 'password': 'staff123'})
        self.assertEqual(r.status_code, 302)
        self.assertIn(b'Login', c.get('/').data)  # still on the public page, not logged in

    def test_json_post_needs_the_header(self):
        a = self.login(ADMIN)
        self.assertEqual(a.post('/edit_flight/1', json={}).status_code, 400)
        self.assertEqual(self.post(a, '/edit_flight/1', json={}).status_code, 200)

    def test_forms_get_a_hidden_token(self):
        html = main.app.test_client().get('/employee_login').get_data(as_text=True)
        self.assertIn('name="csrf_token"', html)

    def test_backup_and_restore_are_post_only(self):
        a = self.login(ADMIN)
        self.assertEqual(a.get('/backup_database').status_code, 405)
        self.assertEqual(a.get('/restore_backup/x.db').status_code, 405)
        self.assertEqual(self.post(a, '/backup_database', json={}).get_json()['status'], 'success')

    def test_login_lockout_after_five_failures(self):
        c = main.app.test_client()
        for _ in range(5):
            c.post('/employee_login', data={'username': 'staff', 'password': 'bad', 'csrf_token': self.token(c, '/employee_login')})
        r = c.post('/employee_login', data={'username': 'staff', 'password': 'staff123', 'csrf_token': self.token(c, '/employee_login')})
        self.assertIn(b'Too many failed attempts', r.data)
        self.assertIn('login_locked', self.audit_actions())

    def test_security_headers(self):
        h = self.login(STAFF).get('/').headers
        self.assertEqual(h['X-Frame-Options'], 'SAMEORIGIN')
        self.assertEqual(h['X-Content-Type-Options'], 'nosniff')

    def test_change_password_needs_current_password(self):
        s = self.login(STAFF)
        bad = self.post(s, '/change_password', json={'current_password': 'nope', 'new_password': 'newpass1'}).get_json()
        self.assertEqual(bad['message'], 'Current password is incorrect')
        short = self.post(s, '/change_password', json={'current_password': 'staff123', 'new_password': 'abc'}).get_json()
        self.assertIn('at least 6', short['message'])
        ok = self.post(s, '/change_password', json={'current_password': 'staff123', 'new_password': 'newpass1'}).get_json()
        self.assertEqual(ok['status'], 'success')
        c = main.app.test_client()
        r = c.post('/employee_login', data={'username': 'staff', 'password': 'staff123', 'csrf_token': self.token(c, '/employee_login')})
        self.assertIn(b'Invalid username or password', r.data)
        self.assertEqual(self.login(('/employee_login', 'staff', 'newpass1')).get('/').status_code, 200)

    def test_passenger_profile_password_needs_current(self):
        p = self.register_passenger()
        body = {'name': 'R', 'phone': '1', 'email': 'r@e.com', 'password': 'newpass9'}
        self.assertEqual(self.post(p, '/update_profile', json=body).get_json()['message'], 'Current password is incorrect')
        self.assertEqual(self.post(p, '/update_profile', json={**body, 'current_password': 'pass123'}).get_json()['status'], 'success')
        plain = {'name': 'Riya S', 'phone': '1', 'email': 'r@e.com'}
        self.assertEqual(self.post(p, '/update_profile', json=plain).get_json()['status'], 'success')
