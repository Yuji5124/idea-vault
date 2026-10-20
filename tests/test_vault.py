import base64
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Vault, Handler, ThreadingHTTPServer, stamp


def file(name, content=b'hello', path=None):
    return {'name': name, 'data': base64.b64encode(content).decode(),
            'relativePath': path or name, 'lastModified': 1700000000000}


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.vault = Vault(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_multiple_files_dates_collision_and_original_bytes(self):
        record = self.vault.create('蜘蛛ゲーム', [file('蜘蛛.png', b'one'), file('蜘蛛.png', b'two'), file('2026-10-07_memo.md', b'# note')])
        names = [f['name'] for f in record['files']]
        self.assertEqual(names[:2], [stamp()[:10] + '_蜘蛛.png', stamp()[:10] + '_蜘蛛_01.png'])
        self.assertEqual(names[2], '2026-10-07_memo.md')
        self.assertEqual((self.vault.root / record['folder'] / record['files'][0]['path']).read_bytes(), b'one')
        self.assertEqual((self.vault.root / record['folder'] / record['files'][1]['path']).read_bytes(), b'two')
        self.assertIn('# note', record['files'][2]['text'])
        self.assertTrue(record['inbox'])
        self.assertIn('created_at', record)
        self.assertNotEqual(record['created_at'], record['imported_at'])

    def test_dated_folder_and_same_title_no_overwrite(self):
        a = self.vault.create('2026-10-07_蜘蛛ゲーム', [file('memo.md', path='蜘蛛ゲーム/memo.md'), file('game.png', path='蜘蛛ゲーム/images/game.png')])
        b = self.vault.create('2026-10-07_蜘蛛ゲーム', [file('memo.md', b'new')])
        self.assertEqual(a['folder'], 'inbox/2026-10-07_蜘蛛ゲーム')
        self.assertNotEqual(a['folder'], b['folder'])
        self.assertEqual(len(a['files']), 2)
        self.assertEqual(a['files'][1]['original_path'], '蜘蛛ゲーム/images/game.png')

    def test_edit_classify_relate_and_restart(self):
        source = self.vault.create('蜘蛛の巣', kind='SOURCE')
        principle = self.vault.create('痕跡から推測する', kind='PRINCIPLE')
        idea = self.vault.create('探索ゲーム')
        result = self.vault.update(idea['id'], {'inbox': False, 'relations': [source['id'], principle['id']], 'tags': ['蜘蛛'], 'category': 'ゲーム', 'jima_filter': 'GOOD', 'comment': '一文で伝わる', 'body': 'prototype'})
        self.assertTrue(result['folder'].startswith('ideas/'))
        restored = Vault(self.temp.name).get(idea['id'])
        self.assertEqual(restored['jima_filter'], 'GOOD')
        self.assertEqual(restored['relations'], [source['id'], principle['id']])
        self.assertEqual((self.vault.root / result['folder'] / 'idea.md').read_text(), 'prototype')
        self.assertEqual(restored['imported_at'], idea['imported_at'])

    def test_failed_import_leaves_no_partial_record(self):
        with self.assertRaises(ValueError):
            self.vault.create('broken', [file('ok.txt'), {'name': 'bad.txt', 'data': 'not-base64!'}])
        self.assertEqual(self.vault.records(), [])
        self.assertEqual(list((self.vault.root / '.staging').iterdir()), [])

    def test_split_merge_preserves_notes_and_file_bytes(self):
        a = self.vault.create('original', [file('one.txt', b'one'), file('two.txt', b'two')], body='retain note')
        b = self.vault.create('split', [file('one.txt', b'existing')])
        self.vault.transfer(a['id'], b['id'], [a['files'][0]['id']])
        self.assertEqual(len(self.vault.get(a['id'])['files']), 1)
        target = self.vault.get(b['id'])
        self.assertEqual(len(target['files']), 2)
        self.assertNotEqual(target['files'][0]['name'], target['files'][1]['name'])
        self.vault.transfer(a['id'], b['id'], [a['files'][1]['id']])
        self.assertEqual(self.vault.get(a['id'])['body'], 'retain note')
        self.assertEqual(self.vault.get(a['id'])['files'], [])
        target = self.vault.get(b['id'])
        self.assertEqual({(self.vault.root / target['folder'] / f['path']).read_bytes() for f in target['files']}, {b'one', b'two', b'existing'})

    def test_names_cannot_escape_vault(self):
        record = self.vault.create('../outside', [file('../../escape.txt')])
        for f in record['files']:
            self.assertTrue((self.vault.root / record['folder'] / f['path']).resolve().is_relative_to(self.vault.root))

    def test_invalid_relations_and_rating(self):
        record = self.vault.create('note')
        for changes in ({'relations': ['missing']}, {'jima_filter': 'OTHER'}, {'title': ''}):
            with self.assertRaises(ValueError):
                self.vault.update(record['id'], changes)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.vault = Vault(self.temp.name)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, payload=None, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        return urlopen(Request(self.base + path, data=json.dumps(payload).encode() if payload else None, headers=headers))

    def test_actual_import_fetch_and_safe_html_download(self):
        with self.request('/api/import', {'groups': [{'title': 'folder', 'files': [file('prototype.html', b'<script>alert(1)</script>')]}]}) as response:
            result = json.load(response)
        self.assertEqual(result['errors'], [])
        record = result['records'][0]
        with self.request(f"/api/file/{record['id']}/{record['files'][0]['id']}") as response:
            self.assertIn('attachment', response.headers['Content-Disposition'])
            self.assertEqual(response.read(), b'<script>alert(1)</script>')
        with self.request('/api/records') as response:
            self.assertEqual(len(json.load(response)['records']), 1)
        with self.request('/') as response:
            self.assertIn(b'IDEA VAULT', response.read())

    def test_saved_thumbnail_is_served_separately_without_changing_original(self):
        from io import BytesIO
        from PIL import Image

        original = BytesIO()
        Image.new('RGB', (1200, 800), (30, 90, 150)).save(original, format='PNG')
        thumbnail = BytesIO()
        Image.new('RGB', (320, 213), (30, 90, 150)).save(thumbnail, format='WEBP')
        original_bytes, thumbnail_bytes = original.getvalue(), thumbnail.getvalue()
        image = file('idea.png', original_bytes)
        image['thumbnail'] = {'name': 'thumbnail.webp', 'data': base64.b64encode(thumbnail_bytes).decode()}
        record = self.server.vault.create('thumbnail fixture', [image])
        saved = record['files'][0]
        original_path = self.server.vault.root / record['folder'] / saved['path']

        with self.request(f"/api/file/{record['id']}/{saved['thumbnail']['id']}") as response:
            self.assertEqual(response.headers['Content-Type'], 'image/webp')
            self.assertEqual(response.read(), thumbnail_bytes)
        with self.request(f"/api/file/{record['id']}/{saved['id']}") as response:
            self.assertEqual(response.read(), original_bytes)
        self.assertEqual(original_path.read_bytes(), original_bytes)

    def test_cross_origin_write_rejected(self):
        with self.assertRaises(HTTPError) as raised:
            self.request('/api/create', {'title': 'bad'}, 'https://evil.example')
        self.assertEqual(raised.exception.code, 403)
        self.assertEqual(self.server.vault.records(), [])

    def test_partial_batch_reports_saved_and_failed_groups(self):
        with self.request('/api/import', {'groups': [{'title': 'ok', 'files': [file('a.txt')]}, {'title': 'bad', 'files': [{'name': 'x', 'data': '!'}]}]}) as response:
            result = json.load(response)
        self.assertEqual(len(result['records']), 1)
        self.assertEqual(len(result['errors']), 1)


if __name__ == '__main__':
    unittest.main()
