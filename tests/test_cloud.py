"""End-to-end HTTP contract tests against an in-memory Supabase test double.

These exercise owner isolation, JWT propagation and CRUD; they do not establish
the real hosted project's policies or readiness.
"""
import base64
import copy
import json
import re
import threading
import unittest
from unittest.mock import patch
import os
import tempfile
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit, parse_qs
from urllib.request import Request, urlopen
from test_vault import file
from server import Handler

OWNER = '11111111-1111-4111-8111-111111111111'


class SupabaseDouble(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def handle_request(self):
        path = urlsplit(self.path).path
        size = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(size) if size else b''
        data = json.loads(raw) if self.headers.get('Content-Type', '').startswith('application/json') and raw else None
        token = self.headers.get('Authorization')
        if path == '/rest/v1/mutopia_public_records' and token == 'Bearer test-publishable' and self.command == 'GET':
            query = parse_qs(urlsplit(self.path).query)
            rows = list(self.server.mutopia_rows.values())
            if 'id' in query:
                rows = [row for row in rows if row['id'] == query['id'][0][3:]]
            if 'owner_id' in query:
                rows = [row for row in rows if row['owner_id'] == query['owner_id'][0][3:]]
            limit = int(query.get('limit', ['500'])[0])
            fields = query.get('select', ['*'])[0].split(',')
            self.reply(200, [{key: value for key, value in row.items() if key in fields} for row in rows[:limit]])
            return
        public_image_prefix = '/storage/v1/object/public/mutopia-public/'
        if path.startswith(public_image_prefix) and self.command == 'GET':
            key = unquote(path[len(public_image_prefix):])
            contents = self.server.public_objects.get(key)
            if contents is None:
                self.reply(404, {})
            else:
                self.reply(200, contents, mime='image/webp' if key.endswith('.webp') else 'image/png')
            return
        if path == '/auth/v1/token':
            accepted = data.get('refresh_token') == 'owner-refresh' or (data.get('email') == 'owner@example.test' and data.get('password') == getattr(self.server, 'password', 'test-password'))
            if not accepted:
                self.reply(401, {})
                return
            self.reply(200, {'access_token': 'owner-token', 'refresh_token': 'owner-refresh', 'expires_in': 3600})
            return
        if path == '/auth/v1/verify':
            hashed = data.get('token_hash')
            if data.get('type') != 'recovery' or hashed not in {'owner-recovery-hash-123456789', 'other-recovery-hash-123456789'} or hashed in self.server.used_hashes:
                self.reply(403, {'error': 'test provider rejects invalid/expired/used token'})
                return
            self.server.used_hashes.add(hashed)
            self.reply(200, {'access_token': 'owner-token' if hashed.startswith('owner-') else 'other-token'})
            return
        if token not in {'Bearer owner-token', 'Bearer other-token'}:
            self.reply(401, {})
            return
        if path == '/auth/v1/user' and self.command == 'PUT':
            self.server.password_updates.append((token, data))
            self.server.password = data['password']
            self.reply(200, {'id': OWNER})
            return
        if path == '/auth/v1/user':
            self.reply(200, {'id': OWNER if token == 'Bearer owner-token' else '22222222-2222-4222-8222-222222222222'})
            return
        if token != 'Bearer owner-token':
            self.reply(403, {})
            return
        if path == '/auth/v1/logout':
            self.reply(200, {})
        elif path == '/rest/v1/vault_records':
            if self.command == 'GET':
                query = parse_qs(urlsplit(self.path).query)
                records = list(self.server.rows.values())
                if 'id' in query:
                    records = [r for r in records if r['id'] == query['id'][0][3:]]
                offset, limit = int(query.get('offset', ['0'])[0]), int(query.get('limit', ['500'])[0])
                self.reply(200, [{'metadata': copy.deepcopy(r)} for r in records[offset:offset+limit]])
            elif self.command == 'POST':
                self.server.rows[data['id']] = copy.deepcopy(data['metadata'])
                self.reply(201, [data])
            elif self.command == 'PATCH':
                identifier = parse_qs(urlsplit(self.path).query)['id'][0][3:]
                self.server.rows[identifier] = copy.deepcopy(data['metadata'])
                self.reply(200, [data])
            elif self.command == 'DELETE':
                query = parse_qs(urlsplit(self.path).query)
                identifier = query.get('id', [''])[0][3:]
                if query.get('owner_id', [''])[0][3:] == OWNER:
                    self.server.rows.pop(identifier, None)
                self.reply(200, [])
        elif path == '/rest/v1/mutopia_public_records':
            query = parse_qs(urlsplit(self.path).query)
            if self.command == 'GET':
                rows = list(self.server.mutopia_rows.values())
                if 'id' in query:
                    rows = [row for row in rows if row['id'] == query['id'][0][3:]]
                if 'owner_id' in query:
                    rows = [row for row in rows if row['owner_id'] == query['owner_id'][0][3:]]
                fields = query.get('select', ['*'])[0].split(',')
                self.reply(200, [{key: value for key, value in row.items() if key in fields} for row in rows])
            elif self.command == 'POST':
                if data.get('owner_id') != OWNER:
                    self.reply(403, {})
                    return
                self.server.mutopia_rows[data['id']] = copy.deepcopy(data)
                self.reply(201, [data])
            elif self.command == 'DELETE':
                identifier = query.get('id', [''])[0][3:]
                row = self.server.mutopia_rows.get(identifier)
                if row and row['owner_id'] == query.get('owner_id', [''])[0][3:]:
                    del self.server.mutopia_rows[identifier]
                self.reply(200, [])
        elif path.startswith('/storage/v1/object/mutopia-public/') and self.command == 'POST':
            key = unquote(path.split('/mutopia-public/', 1)[1])
            if not key.startswith(OWNER + '/'):
                self.reply(403, {})
                return
            self.server.public_objects[key] = raw
            self.reply(200, {})
        elif path == '/storage/v1/object/mutopia-public' and self.command == 'DELETE':
            for key in data.get('prefixes', []):
                if key.startswith(OWNER + '/'):
                    self.server.public_objects.pop(key, None)
            self.reply(200, {})
        elif path.startswith('/storage/v1/object/idea-vault/') and self.command == 'POST':
            name = unquote(path.split('/idea-vault/', 1)[1])
            if not re.fullmatch(r"[A-Za-z0-9_/!.*'() &$=@;:+,?-]*", name):
                self.reply(400, {'error': 'InvalidKey'})
                return
            if name in self.server.objects:
                self.reply(409, {})
                return
            self.server.objects[name] = raw
            self.reply(200, {})
        elif path == '/storage/v1/object/idea-vault' and self.command == 'DELETE':
            for name in data.get('prefixes', []):
                if name.startswith(OWNER + '/'):
                    self.server.objects.pop(name, None)
            self.reply(200, {})
        elif path.startswith('/storage/v1/object/authenticated/idea-vault/'):
            name = unquote(path.split('/idea-vault/', 1)[1])
            self.reply(200, self.server.objects[name], mime='application/json' if name.endswith('.json') else None)
        else:
            self.reply(404, {})

    def reply(self, status, body, mime=None):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime or ('application/octet-stream' if isinstance(body, bytes) else 'application/json'))
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    do_GET = do_POST = do_PATCH = do_DELETE = do_PUT = handle_request


def start_fixture(port=0):
    provider = ThreadingHTTPServer(('127.0.0.1', 0), SupabaseDouble)
    provider.rows, provider.objects = {}, {}
    provider.mutopia_rows, provider.public_objects = {}, {}
    provider.password_updates, provider.used_hashes = [], set()
    app = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    app.cloud_config = (f'http://127.0.0.1:{provider.server_port}', 'test-publishable', OWNER)
    app.cloud_lock = threading.RLock()
    listing = patch('document_import.list_github_documents', return_value=[])
    listing.start()
    original_close = app.server_close
    def close_with_listing_cleanup():
        listing.stop()
        original_close()
    app.server_close = close_with_listing_cleanup
    threads = []
    for server in (provider, app):
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        threads.append(thread)
    return provider, app, threads


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.provider, self.app, self.threads = start_fixture()
        self.base = f'http://127.0.0.1:{self.app.server_port}'

    def tearDown(self):
        for server in (self.app, self.provider):
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join()

    def call(self, path, payload=None, token='owner-token'):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        response = urlopen(Request(self.base + path, data=json.dumps(payload).encode() if payload is not None else None, headers=headers))
        with response:
            raw = response.read()
            return json.loads(raw) if response.headers['Content-Type'].startswith('application/json') else raw

    def test_login_and_refresh_return_no_provider_profile(self):
        session = self.call('/api/login', {'email': 'owner@example.test', 'password': 'test-password'}, token=None)
        self.assertEqual(set(session), {'access_token', 'refresh_token', 'expires_in'})
        self.assertEqual(self.call('/api/refresh', {'refresh_token': session['refresh_token']}, token=None)['access_token'], 'owner-token')

    def test_unsigned_and_other_user_cannot_access_records_files_or_write(self):
        record = self.call('/api/create', {'title': 'private'})
        for token in (None, 'other-token', 'invalid'):
            for path, payload in (('/api/records', None), ('/api/create', {'title': 'bad'}), (f'/api/file/{record["id"]}/file', None)):
                with self.assertRaises(HTTPError) as error:
                    self.call(path, payload, token)
                self.assertEqual(error.exception.code, 401)
        self.assertEqual(len(self.provider.rows), 1)

    def test_cloud_import_update_transfer_and_download(self):
        result = self.call('/api/import', {'groups': [{'title': '蜘蛛ゲーム', 'files': [file('same.txt', b'first'), file('same.txt', b'second')]}]})
        self.assertEqual(result['errors'], [])
        record = result['records'][0]
        self.assertNotEqual(record['files'][0]['name'], record['files'][1]['name'])
        self.assertEqual(self.call(f'/api/file/{record["id"]}/{record["files"][0]["id"]}'), b'first')
        updated = self.call('/api/update', {'id': record['id'], 'changes': {'inbox': False, 'jima_filter': 'GOOD', 'tags': ['蜘蛛']}})
        self.assertEqual(updated['jima_filter'], 'GOOD')
        self.assertTrue(updated['folder'].startswith('ideas/'))
        target = self.call('/api/create', {'title': 'new idea'})
        self.call('/api/transfer', {'source': record['id'], 'target': target['id'], 'files': [record['files'][0]['id']]})
        rows = self.call('/api/records')['records']
        self.assertEqual([len(r['files']) for r in rows], [1, 1])
        self.assertEqual(self.call(f'/api/file/{target["id"]}/{record["files"][0]["id"]}'), b'first')
        self.assertEqual(len(self.provider.objects), 3, 'retain original object for recovery')

    def test_restart_does_not_depend_on_render_local_disk(self):
        self.call('/api/create', {'title': 'survives restart'})
        other = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        other.cloud_config, other.cloud_lock = self.app.cloud_config, threading.RLock()
        thread = threading.Thread(target=other.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(Request(f'http://127.0.0.1:{other.server_port}/api/records', headers={'Authorization': 'Bearer owner-token'})) as response:
                self.assertEqual(json.load(response)['records'][0]['title'], 'survives restart')
        finally:
            other.shutdown()
            other.server_close()
            thread.join()

    def test_public_login_page_does_not_contain_personal_data(self):
        self.call('/api/create', {'title': 'SECRET-TITLE'})
        self.assertNotIn(b'SECRET-TITLE', self.call('/', token=None))
        self.assertEqual(self.call('/api/config', token=None), {'storage': 'cloud'})

    def test_mutopia_public_feed_is_anonymous_but_private_routes_stay_protected(self):
        from cloud_store import CloudVault
        public_record = {
            'id': 'published-id', 'title': '公開作品', 'type': 'VISUAL',
            'category': '生命', 'tags': ['膜'], 'body': '公開用の説明',
            'relations': [], 'created_at': '2026-10-14T00:00:00Z',
            'image_url': 'https://example.supabase.co/storage/v1/object/public/mutopia-public/owner/published-id/image.webp',
        }
        with patch.object(CloudVault, 'public_mutopia_records', return_value=[public_record]) as public_feed:
            response = urlopen(Request(self.base + '/api/mutopia/public-records'))
            with response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertEqual(json.load(response), {'records': [public_record]})
        public_feed.assert_called_once_with(self.app.cloud_config[0], self.app.cloud_config[1])
        for path in ('/api/records', '/api/mutopia/publications'):
            with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                urlopen(self.base + path)
            self.assertEqual(error.exception.code, 401)

    def test_mutopia_public_feed_reports_missing_configuration(self):
        self.app.cloud_config = None
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base + '/api/mutopia/public-records')
        self.assertEqual(error.exception.code, 503)
        self.assertEqual(json.loads(error.exception.read()), {'code': 'MUTOPIA_PUBLICATION_UNAVAILABLE'})

    def test_mutopia_publication_actions_require_owner_session(self):
        from cloud_store import CloudVault
        with patch.object(CloudVault, 'publish_to_mutopia', return_value={'id': 'owned', 'published': True}) as publish:
            result = self.call('/api/mutopia/publish', {'record_id': 'owned', 'published': True})
        self.assertEqual(result, {'id': 'owned', 'published': True})
        publish.assert_called_once()
        with patch.object(CloudVault, 'unpublish_from_mutopia', return_value={'id': 'owned', 'published': False}) as unpublish:
            result = self.call('/api/mutopia/publish', {'record_id': 'owned', 'published': False})
        self.assertEqual(result, {'id': 'owned', 'published': False})
        unpublish.assert_called_once()
        with self.assertRaises(HTTPError) as error:
            self.call('/api/mutopia/publish', {'record_id': 'owned', 'published': True}, token=None)
        self.assertEqual(error.exception.code, 401)

    def test_trash_restore_and_permanent_delete_are_owner_only_and_unpublish(self):
        image = file('cover.png', b'private-image-bytes')
        record = self.call('/api/import', {'groups': [{'title': 'trash target', 'files': [image, file('secret.txt', b'private')]}]})['records'][0]
        self.call('/api/mutopia/publish', {'record_id': record['id'], 'published': True})
        public_key = next(iter(self.provider.public_objects))
        with self.assertRaises(HTTPError) as error:
            self.call('/api/manage', {'id': record['id'], 'action': 'trash'}, token=None)
        self.assertEqual(error.exception.code, 401)

        result = self.call('/api/manage', {'id': record['id'], 'action': 'trash'})
        self.assertTrue(result['deleted_at'])
        self.assertNotIn(record['id'], self.provider.mutopia_rows)
        self.assertNotIn(public_key, self.provider.public_objects)
        self.assertTrue(self.provider.rows[record['id']]['deleted_at'])
        with self.assertRaises(HTTPError) as error:
            self.call('/api/update', {'id': record['id'], 'changes': {'title': 'changed'}})
        self.assertEqual(error.exception.code, 400)

        restored = self.call('/api/manage', {'id': record['id'], 'action': 'restore'})
        self.assertTrue(restored['restored'])
        self.assertNotIn('deleted_at', self.provider.rows[record['id']])
        self.assertEqual(self.provider.mutopia_rows, {}, 'restore must not silently republish')

        self.call('/api/manage', {'id': record['id'], 'action': 'trash'})
        with self.assertRaises(HTTPError) as error:
            self.call('/api/manage', {'id': record['id'], 'action': 'purge', 'confirmation': 'wrong'})
        self.assertEqual(error.exception.code, 400)
        self.assertIn(record['id'], self.provider.rows)
        self.call('/api/manage', {'id': record['id'], 'action': 'purge', 'confirmation': 'trash target'})
        self.assertNotIn(record['id'], self.provider.rows)
        self.assertFalse(self.provider.objects)
        self.assertEqual(self.call('/api/records')['records'], [])

    def test_backup_download_is_restorable_by_local_vault(self):
        import backup_cloud
        from server import Vault
        self.call('/api/import', {'groups': [{'title': 'cloud memo', 'files': [file('memo.md', b'private contents')]}]})
        with tempfile.TemporaryDirectory() as temp:
            env = dict(zip(('SUPABASE_URL', 'SUPABASE_PUBLISHABLE_KEY', 'IDEA_VAULT_OWNER_ID'), self.app.cloud_config))
            with patch.dict(os.environ, env), patch('sys.argv', ['backup_cloud.py', '--destination', temp]), patch('builtins.input', return_value='owner@example.test'), patch('backup_cloud.getpass', return_value='test-password'):
                backup_cloud.main()
            root = next(Path(temp).glob('cloud-*'))
            self.assertTrue((root / 'BACKUP_COMPLETE.json').exists())
            records = Vault(root).records()
            self.assertEqual(len(records), 1)
            self.assertEqual((root / records[0]['folder'] / records[0]['files'][0]['path']).read_bytes(), b'private contents')

    def test_json_attachment_original_bytes_preserved(self):
        raw = b'{ "note": "private", "spaces":  true }\n'
        record = self.call('/api/import', {'groups': [{'title': 'json', 'files': [file('original.json', raw)]}]})['records'][0]
        self.assertEqual(self.call(f'/api/file/{record["id"]}/{record["files"][0]["id"]}'), raw)


class StartupTests(unittest.TestCase):
    def test_public_startup_cannot_fall_back_to_ephemeral_disk(self):
        from server import main
        cases = [
            {'RENDER': 'true', 'RENDER_EXTERNAL_HOSTNAME': 'example.onrender.com'},
            {'RENDER': 'true', 'RENDER_EXTERNAL_HOSTNAME': 'example.onrender.com', 'IDEA_VAULT_STORAGE': 'supabase'},
            {'IDEA_VAULT_STORAGE': 'supabase', 'SUPABASE_URL': 'https://example.supabase.co', 'SUPABASE_PUBLISHABLE_KEY': 'sb_secret_never-use', 'IDEA_VAULT_OWNER_ID': OWNER},
        ]
        for env in cases:
            with self.subTest(env_names=list(env)), patch.dict(os.environ, env, clear=True), patch('sys.argv', ['server.py']):
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    provider, app, threads = start_fixture(8770)
    print('Cloud test double running on port 8770', flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
