import base64
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import test_vault


class AuthenticationTests(test_vault.ApiTests):
    def setUp(self):
        super().setUp()
        self.server.public_host = 'idea-vault.example.com'
        self.server.password = 'test-only-long-password-123456'

    def request(self, path, payload=None, origin=None, password=None, host=None):
        headers = {'Content-Type': 'application/json'}
        if password:
            headers['Authorization'] = 'Basic ' + base64.b64encode(('jima:' + password).encode()).decode()
        else:
            headers['Authorization'] = 'Basic ' + base64.b64encode(('jima:' + self.server.password).encode()).decode()
        if origin:
            headers['Origin'] = origin
        if host:
            headers['Host'] = host
        return urlopen(Request(self.base + path, data=json.dumps(payload).encode() if payload else None, headers=headers))

    def test_no_auth_cannot_read_ui_metadata_or_files_or_write(self):
        record = self.server.vault.create('private', [test_vault.file('secret.txt')])
        paths = ['/', '/app.js', '/api/records', f"/api/file/{record['id']}/{record['files'][0]['id']}"]
        for path in paths:
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + path)
            self.assertEqual(error.exception.code, 401)
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.base + '/api/create', data=b'{"title":"bad"}', headers={'Content-Type': 'application/json'}))
        self.assertEqual(error.exception.code, 401)
        self.assertEqual(len(self.server.vault.records()), 1)

    def test_wrong_password_is_rejected(self):
        with self.assertRaises(HTTPError) as error:
            self.request('/api/records', password='incorrect')
        self.assertEqual(error.exception.code, 401)

    def test_public_https_origin_works_http_origin_rejected(self):
        with self.request('/api/create', {'title': 'private note'}, origin='https://idea-vault.example.com', host='idea-vault.example.com') as response:
            self.assertEqual(response.status, 201)
        with self.assertRaises(HTTPError) as error:
            self.request('/api/create', {'title': 'bad'}, origin='http://idea-vault.example.com', host='idea-vault.example.com')
        self.assertEqual(error.exception.code, 403)

    def test_health_has_no_private_data(self):
        with urlopen(self.base + '/healthz') as response:
            self.assertEqual(json.load(response), {'status': 'ok'})
