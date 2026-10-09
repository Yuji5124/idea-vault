"""Recovery contracts against a provider double, not a live Supabase project."""
import contextlib
import io
import json
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from test_cloud import start_fixture


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.provider, self.app, self.threads = start_fixture()
        self.base = f'http://127.0.0.1:{self.app.server_port}'

    def tearDown(self):
        for server in (self.app, self.provider):
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join()

    def post(self, path, body, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        with urlopen(Request(self.base + path, data=json.dumps(body).encode(), headers=headers)) as response:
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
            return json.load(response)

    def reset(self, **fields):
        return self.post('/api/reset-password', {'type': 'recovery', 'password': 'new-test-password-456', **fields})

    def test_fragment_session_verified_and_owner_password_updated(self):
        self.assertEqual(self.post('/api/recovery-check', {'type': 'recovery', 'access_token': 'owner-token'}), {'valid': True})
        result = self.reset(access_token='owner-token')
        self.assertEqual(result, {'updated': True, 'sessions_revoked': True})
        self.assertEqual(self.provider.password_updates, [('Bearer owner-token', {'password': 'new-test-password-456'})])
        self.post('/api/login', {'email': 'owner@example.test', 'password': 'new-test-password-456'})
        with self.assertRaises(HTTPError):
            self.post('/api/login', {'email': 'owner@example.test', 'password': 'test-password'})

    def test_recovery_hash_verified_once_and_no_tokens_returned(self):
        result = self.reset(token_hash='owner-recovery-hash-123456789')
        self.assertEqual(set(result), {'updated', 'sessions_revoked'})
        with self.assertRaises(HTTPError):
            self.reset(token_hash='owner-recovery-hash-123456789')
        self.assertEqual(len(self.provider.password_updates), 1)

    def test_invalid_and_expired_links_rejected(self):
        for fields in ({'access_token': 'invalid'}, {'access_token': 'expired'}, {'token_hash': 'expired-recovery-hash-123456789'}, {'token_hash': 'invalid-recovery-hash-123456789'}, {}, {'code': 'pkce-code'}):
            with self.subTest(kind=list(fields)):
                with self.assertRaises(HTTPError) as error:
                    self.reset(**fields)
                self.assertEqual(error.exception.code, 400)
        self.assertEqual(self.provider.password_updates, [])

    def test_other_user_rejected_before_any_password_update(self):
        for fields in ({'access_token': 'other-token'}, {'token_hash': 'other-recovery-hash-123456789'}):
            with self.assertRaises(HTTPError):
                self.reset(**fields)
        self.assertEqual(self.provider.password_updates, [])

    def test_invalid_type_ambiguous_token_and_short_password_rejected(self):
        for body in ({'type': 'signup', 'access_token': 'owner-token', 'password': 'long-new-password'}, {'type': 'recovery', 'access_token': 'owner-token', 'token_hash': 'owner-recovery-hash-123456789', 'password': 'long-new-password'}, {'type': 'recovery', 'access_token': 'owner-token', 'password': 'short'}, []):
            with self.assertRaises(HTTPError):
                self.post('/api/reset-password', body)
        self.assertEqual(self.provider.password_updates, [])

    def test_cross_origin_recovery_rejected(self):
        with self.assertRaises(HTTPError) as error:
            self.post('/api/reset-password', {'type': 'recovery', 'access_token': 'owner-token', 'password': 'long-new-password'}, 'https://evil.example')
        self.assertEqual(error.exception.code, 403)
        self.assertEqual(self.provider.password_updates, [])

    def test_no_private_api_access_or_tokens_in_response_or_logs(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = self.reset(access_token='owner-token')
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + '/api/records')
            self.assertEqual(error.exception.code, 401)
            with self.assertRaises(HTTPError) as error:
                self.reset(access_token='expired-sensitive-test-token')
            body = error.exception.read().decode()
        for secret in ('owner-token', 'new-test-password-456', 'expired-sensitive-test-token'):
            self.assertNotIn(secret, json.dumps(result) + body + out.getvalue() + err.getvalue())
        self.assertFalse(hasattr(self.app, 'vault'), 'cloud fixture must not create a disk vault')

    def test_public_recovery_script_contains_no_personal_data(self):
        with urlopen(self.base + '/recovery.js') as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
