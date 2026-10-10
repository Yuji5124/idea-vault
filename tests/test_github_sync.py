import io
import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from test_cloud import start_fixture
from test_document_import import URL, ITEM, RAW
import document_import as documents


class GithubListingTests(unittest.TestCase):
    def test_regular_markdown_only_and_no_vault_credentials_forwarded(self):
        tree = {'truncated': False, 'tree': [
            {'path': 'ideas/2026-10-10_example.md', 'type': 'blob', 'mode': '100644'},
            {'path': 'ideas/sub/星.markdown', 'type': 'blob', 'mode': '100644'},
            {'path': 'README.md', 'type': 'blob', 'mode': '100644'},
            {'path': 'ideas/image.png', 'type': 'blob', 'mode': '100644'},
            {'path': 'ideas/symlink.md', 'type': 'blob', 'mode': '120000'},
            {'path': 'ideas/sub', 'type': 'tree', 'mode': '040000'},
        ]}
        with patch('document_import.build_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(json.dumps(tree).encode())
            result = documents.list_github_documents()
            request = opener.return_value.open.call_args.args[0]
            self.assertNotIn('Authorization', dict(request.header_items()))
            self.assertEqual(request.full_url, 'https://api.github.com/repos/Yuji5124/idea-vault/git/trees/main?recursive=1')
        self.assertEqual(len(result), 2)
        self.assertIn(URL, result)
        self.assertTrue(all(documents.github_location(url)[0] == url for url in result))

    def test_incomplete_oversize_and_invalid_listing_are_errors(self):
        for raw in (b'{"truncated":true,"tree":[]}', b'{"tree":[]}', b'invalid json', b'x'*(documents.MAX_TREE_BYTES+1)):
            with patch('document_import.build_opener') as opener:
                opener.return_value.open.return_value = io.BytesIO(raw)
                with self.assertRaises(ValueError):
                    documents.list_github_documents()
        with patch('document_import.build_opener') as opener:
            opener.return_value.open.side_effect = HTTPError('https://api.github.com/', 403, 'rate limit', {}, None)
            with self.assertRaises(ValueError) as error:
                documents.list_github_documents()
            self.assertIn('既存資料', str(error.exception))


class GithubSyncTests(unittest.TestCase):
    def setUp(self):
        self.provider, self.app, self.threads = start_fixture()
        self.base = f'http://127.0.0.1:{self.app.server_port}'

    def tearDown(self):
        for server in (self.app, self.provider):
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join()

    def call(self, path, body, token='owner-token'):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer '+token
        with urlopen(Request(self.base+path, data=json.dumps(body).encode(), headers=headers)) as response:
            return json.load(response)

    def test_sync_imports_new_only_and_preserves_edited_records(self):
        with patch('document_import.list_github_documents', return_value=[URL]), patch('document_import.fetch_github', return_value=(URL, documents.markdown_metadata(ITEM['name'], RAW), ITEM)) as download:
            first = self.call('/api/sync-github', {})
            self.assertEqual((first['imported'], first['failed'], first['remaining']), (1, 0, 0))
            record = next(iter(self.provider.rows.values()))
            self.call('/api/update', {'id': record['id'], 'changes': {'title': 'Edited', 'body': 'My notes', 'record_date': '2026-10-12'}})
            second = self.call('/api/sync-github', {})
            self.assertEqual((second['imported'], second['already_imported']), (0, 1))
            download.assert_called_once()
            saved = next(iter(self.provider.rows.values()))
            self.assertEqual((saved['title'], saved['body'], saved['record_date']), ('Edited', 'My notes', '2026-10-12'))
            self.assertEqual(len(self.provider.objects), 1)
            self.assertFalse(hasattr(self.app, 'vault'))

    def test_batch_failure_does_not_block_later_documents_or_repeat(self):
        urls = [URL.replace('example.md', f'{n}.md') for n in range(7)]
        def download(source):
            if source == urls[0]:
                raise ValueError('private provider details that must not be returned')
            return source, documents.markdown_metadata(ITEM['name'], RAW), ITEM
        with patch('document_import.list_github_documents', return_value=urls), patch('document_import.fetch_github', side_effect=download) as fetch:
            first = self.call('/api/sync-github', {})
            self.assertEqual((first['imported'], first['failed'], first['remaining']), (4, 1, 2))
            self.assertNotIn('private provider details', json.dumps(first))
            second = self.call('/api/sync-github', {'attempted': first['attempted']})
            self.assertEqual((second['imported'], second['failed'], second['remaining']), (2, 0, 0))
            self.assertEqual(fetch.call_count, 7)
            self.assertEqual(len(self.provider.rows), 6)

    def test_unsigned_other_owner_and_cross_site_do_not_list_or_download(self):
        with patch('document_import.list_github_documents') as listing, patch('document_import.fetch_github') as download:
            for token in (None, 'other-token', 'invalid'):
                with self.assertRaises(HTTPError) as error:
                    self.call('/api/sync-github', {}, token)
                self.assertEqual(error.exception.code, 401)
            headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer owner-token', 'Origin': 'https://evil.example'}
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(self.base+'/api/sync-github', data=b'{}', headers=headers))
            self.assertEqual(error.exception.code, 403)
            listing.assert_not_called()
            download.assert_not_called()

    def test_invalid_attempts_rejected_before_network_and_listing_failure_leaves_data(self):
        with patch('document_import.list_github_documents') as listing:
            for attempts in ('invalid', [URL]*101, ['http://127.0.0.1/private']):
                with self.assertRaises(HTTPError):
                    self.call('/api/sync-github', {'attempted': attempts})
            listing.assert_not_called()
        self.call('/api/create', {'title': 'Existing'})
        with patch('document_import.list_github_documents', side_effect=ValueError('GitHubの自動取り込みを確認できません。')):
            with self.assertRaises(HTTPError):
                self.call('/api/sync-github', {})
        self.assertEqual(next(iter(self.provider.rows.values()))['title'], 'Existing')


if __name__ == '__main__':
    provider, app, threads = start_fixture(8772)
    patch('document_import.list_github_documents', return_value=[URL]).start()
    patch('document_import.fetch_github', return_value=(URL, documents.markdown_metadata(ITEM['name'], RAW), ITEM)).start()
    print('Auto-sync browser fixture running on port 8772', flush=True)
    threading.Event().wait()
