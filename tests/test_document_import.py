import base64
import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from test_cloud import start_fixture
import document_import as documents
from urllib.request import Request, urlopen
import json

URL = 'https://github.com/Yuji5124/idea-vault/blob/main/ideas/2026-10-10_example.md'
TEXT = '# Example — アイデア保存\n\n保存日：2026-10-10\n\n## 構想\n実験の本文。画像ファイルは未添付。\n'
RAW = TEXT.encode()
ITEM = {'name': '2026-10-10_example.md', 'relativePath': '2026-10-10_example.md', 'data': base64.b64encode(RAW).decode()}


class MarkdownTests(unittest.TestCase):
    def test_heading_saved_date_body_and_filename_fallback(self):
        self.assertEqual(documents.markdown_metadata(ITEM['name'], RAW), {'title': 'Example', 'body': TEXT, 'record_date': '2026-10-10'})
        self.assertEqual(documents.markdown_metadata('2026-09-01_other.md', b'Plain text')['title'], 'other')
        self.assertEqual(documents.markdown_metadata('2026-09-01_other.md', b'Plain text')['record_date'], '2026-09-01')

    def test_japanese_date_and_frontmatter(self):
        self.assertEqual(documents.markdown_metadata('idea.md', '# 星の研究\n- **保存日：** 2026年10月10日\n'.encode())['record_date'], '2026-10-10')
        self.assertEqual(documents.markdown_metadata('idea.md', b'---\ntitle: "Space lab"\ndate: 2026-10-09\n---\nBody')['title'], 'Space lab')
        self.assertEqual(documents.markdown_metadata('idea.md', b'---\ndate: 2026-10-09\n---\nBody')['record_date'], '2026-10-09')

    def test_invalid_dates_encoding_and_oversized_documents_rejected(self):
        for name, raw in [('2026-02-30_bad.md', b'data'), ('bad.md', '保存日：2026-02-30'.encode()), ('bad.md', b'\xff'), ('big.md', b'x'*(documents.MAX_DOCUMENT_BYTES+1))]:
            with self.assertRaises(ValueError):
                documents.markdown_metadata(name, raw)

    def test_folder_and_mixed_file_groups_preserved(self):
        self.assertIsNone(documents.markdown_group({'files': [ITEM, ITEM]}))
        self.assertIsNone(documents.markdown_group({'files': [{**ITEM, 'relativePath': 'folder/file.md'}]}))
        self.assertIsNone(documents.markdown_group({'files': [{**ITEM, 'name': 'file.png'}]}))

    def test_github_url_canonicalization_and_ssrf_protection(self):
        canonical, raw_url, name = documents.github_location(URL)
        self.assertEqual(canonical, URL)
        self.assertTrue(raw_url.startswith('https://raw.githubusercontent.com/Yuji5124/idea-vault/main/ideas/'))
        self.assertEqual(name, '2026-10-10_example.md')
        for url in ('http://127.0.0.1/private.md', 'https://github.com@evil.example/x', URL+'?token=secret', URL+'#secret', URL.replace('/main/', '/other/'), URL.replace('ideas/', 'ideas/../'), URL.replace('ideas/', 'ideas/%2e%2e/'), URL.replace('.md', '.html'), URL.replace('Yuji5124', 'Other'), URL.replace('ideas/', 'ideas/%0a/')):
            with self.subTest(url_kind=url.split('/')[2]):
                with self.assertRaises(ValueError):
                    documents.github_location(url)

    def test_bounded_download_does_not_forward_authentication(self):
        fake = io.BytesIO(RAW)
        with patch('document_import.build_opener') as build:
            build.return_value.open.return_value = fake
            source, metadata, item = documents.fetch_github(URL)
            requested = build.return_value.open.call_args.args[0]
            self.assertNotIn('Authorization', dict(requested.header_items()))
            self.assertEqual(source, URL)
            self.assertEqual(metadata['body'], TEXT)
            self.assertEqual(base64.b64decode(item['data']), RAW)
        with patch('document_import.build_opener') as build:
            build.return_value.open.side_effect = HTTPError(URL, 404, 'not found', {}, None)
            with self.assertRaises(ValueError) as error:
                documents.fetch_github(URL)
            self.assertIn('ドロップ', str(error.exception))
        self.assertIsNone(documents.NoRedirect().redirect_request(None, None, 302, 'redirect', {}, 'https://evil.example'))


class DocumentCloudTests(unittest.TestCase):
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
            headers['Authorization'] = 'Bearer '+token
        with urlopen(Request(self.base+path, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)) as response:
            body = response.read()
            return json.loads(body) if response.headers['Content-Type'].startswith('application/json') else body

    def test_markdown_drop_persists_title_date_body_original_and_edits(self):
        record = self.call('/api/import', {'groups': [{'title': 'filename', 'files': [ITEM]}]})['records'][0]
        self.assertEqual((record['title'], record['record_date'], record['body']), ('Example', '2026-10-10', TEXT))
        self.assertEqual(len(record['files']), 1, 'No invented image attachments')
        self.assertEqual(self.call(f"/api/file/{record['id']}/{record['files'][0]['id']}"), RAW)
        self.call('/api/update', {'id': record['id'], 'changes': {'record_date': '2026-10-11', 'title': 'Edited', 'category': 'ゲーム', 'inbox': False}})
        saved = self.call('/api/records')['records'][0]
        self.assertEqual((saved['record_date'], saved['title'], saved['category'], saved['inbox']), ('2026-10-11', 'Edited', 'ゲーム', False))
        self.assertEqual(saved['imported_at'], record['imported_at'])
        with self.assertRaises(HTTPError):
            self.call('/api/update', {'id': record['id'], 'changes': {'record_date': '2026-02-30'}})
        self.assertEqual(self.call('/api/records')['records'][0]['record_date'], '2026-10-11')

    def test_github_import_deduplicates_and_preserves_edits(self):
        with patch('document_import.fetch_github', return_value=(URL, documents.markdown_metadata(ITEM['name'], RAW), ITEM)) as download:
            result = self.call('/api/import-github', {'url': URL})
            self.assertFalse(result['already_imported'])
            record = result['record']
            self.call('/api/update', {'id': record['id'], 'changes': {'title': 'My title', 'body': 'My notes'}})
            repeat = self.call('/api/import-github', {'url': URL})
            self.assertTrue(repeat['already_imported'])
            self.assertEqual((repeat['record']['title'], repeat['record']['body']), ('My title', 'My notes'))
            self.assertEqual(download.call_count, 1)
        self.assertEqual(len(self.provider.rows), 1)
        self.assertFalse(hasattr(self.app, 'vault'))

    def test_unauthorized_import_rejected_before_network_access(self):
        with patch('document_import.fetch_github') as download:
            for token in (None, 'other-token', 'invalid'):
                with self.assertRaises(HTTPError) as error:
                    self.call('/api/import-github', {'url': URL}, token)
                self.assertEqual(error.exception.code, 401)
            download.assert_not_called()
        self.assertEqual(self.provider.rows, {})

class DocumentLocalTests(unittest.TestCase):
    def test_local_storage_preserves_metadata_and_original_file(self):
        import tempfile
        from server import Vault
        with tempfile.TemporaryDirectory() as root:
            vault = Vault(root)
            record = vault.create(files=[ITEM], **documents.markdown_metadata(ITEM['name'], RAW))
            self.assertEqual((record['title'], record['record_date'], record['body']), ('Example', '2026-10-10', TEXT))
            saved = Vault(root).records()[0]
            from pathlib import Path
            self.assertEqual((Path(root)/saved['folder']/saved['files'][0]['path']).read_bytes(), RAW)
            self.assertEqual((Path(root)/saved['folder']/'idea.md').read_text(), TEXT)


class StorageKeyTests(unittest.TestCase):
    def test_unicode_names_have_ascii_storage_keys_and_legacy_paths_still_work(self):
        from cloud_store import CloudVault
        from test_cloud import OWNER
        from test_vault import file
        stored = {}
        class MemoryVault(CloudVault):
            def upload(self, record, attachment, raw):
                key = self.object_path(record, attachment)
                self.assert_ascii(key)
                stored[key] = raw
            def assert_ascii(self, key):
                import re
                if not re.fullmatch(r"[A-Za-z0-9_/!.*'() &$=@;:+,?-]*", key):
                    raise AssertionError('Storage key is incompatible with Supabase')
            def save(self, record, new=False):
                pass
        vault = MemoryVault('https://example.supabase.co', 'test-publishable', 'owner-token', OWNER)
        record = vault.create('日本語タイトル', [file('ふしぎのほし研究所.md', b'markdown'), file('宇宙の画像.png', b'image')])
        for attachment in record['files']:
            self.assertTrue(attachment['storage_path'].isascii())
            self.assertIn(attachment['original_name'], attachment['name'])
            self.assertEqual(stored[vault.object_path(record, attachment)], b'image' if attachment['mime'].startswith('image/') else b'markdown')
        legacy = {'path': 'files/2026-10-10_old.md', 'id': 'old'}
        self.assertEqual(vault.object_path(record, legacy), OWNER+'/'+record['id']+'/'+legacy['path'])

    def test_real_http_contract_uploads_japanese_markdown(self):
        provider, app, threads = start_fixture()
        try:
            from test_vault import file
            item = file('2026-10-10_ふしぎのほし研究所.md', '# ふしぎのほし研究所\n保存日：2026-10-10\n'.encode())
            payload = {'groups': [{'title': '資料', 'files': [item]}]}
            headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer owner-token'}
            base = f'http://127.0.0.1:{app.server_port}'
            with urlopen(Request(base+'/api/import', data=json.dumps(payload).encode(), headers=headers)) as response:
                result = json.load(response)
            self.assertEqual(result['errors'], [])
            record = result['records'][0]
            self.assertEqual(record['title'], 'ふしぎのほし研究所')
            self.assertTrue(all(key.isascii() for key in provider.objects))
            with urlopen(Request(base+f"/api/file/{record['id']}/{record['files'][0]['id']}", headers=headers)) as response:
                self.assertEqual(response.read(), base64.b64decode(item['data']))
        finally:
            for server in (app, provider):
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join()


if __name__ == '__main__':
    import threading
    provider, app, threads = start_fixture(8771)
    patcher = patch('document_import.fetch_github', return_value=(URL, documents.markdown_metadata(ITEM['name'], RAW), ITEM))
    patcher.start()
    print('Document browser fixture running on port 8771', flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
