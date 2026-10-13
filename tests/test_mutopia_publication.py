import unittest
from unittest.mock import patch
from pathlib import Path

from cloud_store import CloudVault

OWNER = '11111111-1111-4111-8111-111111111111'


class PublicationStorageTests(unittest.TestCase):
    def setUp(self):
        self.vault = CloudVault('https://example.supabase.co', 'publishable-only', 'owner-jwt', OWNER)

    def test_publish_copies_one_image_and_only_the_explicit_public_fields(self):
        record = {
            'id': 'idea-1', 'title': '薄膜', 'type': 'VISUAL', 'category': '生命',
            'tags': ['虹色'], 'body': '公開説明', 'comment': 'PRIVATE COMMENT',
            'jima_filter': 'BAD', 'source_url': 'PRIVATE SOURCE',
            'relations': ['already-public', 'still-private'],
            'created_at': '2026-10-14T00:00:00Z',
            'files': [
                {'id': 'img', 'name': 'membrane.webp', 'original_name': 'PRIVATE NAME',
                 'path': 'images/membrane.webp', 'mime': 'image/webp', 'size': 123},
                {'id': 'secret', 'name': 'private.png', 'path': 'private.png',
                 'mime': 'image/png', 'size': 12},
            ],
        }
        seen = []

        def call(path, method='GET', payload=None, raw=None, mime=None, binary=False,
                 prefer=None, extra_headers=None):
            seen.append((path, method, payload, raw, mime, prefer))
            if path.startswith('/storage/v1/object/mutopia-public/'):
                return {}
            if 'select=image_path' in path:
                return []
            if 'select=id&limit=500' in path:
                return [{'id': 'already-public'}]
            if method == 'POST' and path.startswith('/rest/v1/mutopia_public_records'):
                return [payload]
            raise AssertionError(f'unexpected request: {method} {path}')

        with patch.object(self.vault, 'get', return_value=record), \
             patch.object(self.vault, 'read_file', return_value=b'webp-bytes') as read_file, \
             patch.object(self.vault, 'call', side_effect=call):
            result = self.vault.publish_to_mutopia('idea-1')

        self.assertTrue(result['published'])
        self.assertIn('/storage/v1/object/public/mutopia-public/', result['image_url'])
        read_file.assert_called_once_with(record, record['files'][0])
        row = next(item[2] for item in seen if item[1] == 'POST' and item[2])
        self.assertEqual(set(row), {
            'id', 'owner_id', 'title', 'type', 'category', 'tags', 'body',
            'relations', 'created_at', 'image_path',
        })
        self.assertEqual(row['relations'], ['already-public'])
        self.assertNotIn('PRIVATE COMMENT', str(row))
        self.assertNotIn('PRIVATE SOURCE', str(row))
        insert = next(item for item in seen if item[1] == 'POST' and item[0].startswith('/rest/'))
        self.assertEqual(insert[5], 'resolution=merge-duplicates,return=representation')

    def test_publish_rejects_oversized_images_before_copying(self):
        record = {
            'id': 'large', 'files': [
                {'id': 'large-image', 'name': 'large.webp', 'path': 'large.webp',
                 'mime': 'image/webp', 'size': 5 * 1024 * 1024 + 1},
            ],
        }
        with patch.object(self.vault, 'get', return_value=record), \
             patch.object(self.vault, 'read_file') as read_file:
            with self.assertRaisesRegex(ValueError, '5MB以下'):
                self.vault.publish_to_mutopia('large')
        read_file.assert_not_called()

    def test_public_feed_uses_anon_credentials_and_hides_unpublished_relations(self):
        rows = [
            {'id': 'public-a', 'image_path': 'owner/public-a/image.webp', 'relations': ['public-b', 'private-c']},
            {'id': 'public-b', 'image_path': None, 'relations': []},
        ]
        with patch('cloud_store.request', return_value=rows) as request:
            records = CloudVault.public_mutopia_records('https://example.supabase.co', 'anon-key')
        self.assertIsNone(request.call_args.args[2], 'public feed must not use an owner JWT')
        self.assertIn('mutopia_public_records?select=', request.call_args.args[3])
        self.assertEqual(records[0]['relations'], ['public-b'])
        self.assertEqual(
            records[0]['image_url'],
            'https://example.supabase.co/storage/v1/object/public/mutopia-public/owner/public-a/image.webp',
        )
        self.assertIsNone(records[1]['image_url'])
        self.assertNotIn('image_path', records[0])

    def test_unpublish_removes_only_public_copy_and_public_index(self):
        calls = []

        def call(path, method='GET', payload=None, **kwargs):
            calls.append((path, method, payload))
            if method == 'GET':
                return [{'image_path': f'{OWNER}/idea-1/image.webp'}]
            return {}

        with patch.object(self.vault, 'call', side_effect=call):
            result = self.vault.unpublish_from_mutopia('idea-1')
        self.assertEqual(result, {'id': 'idea-1', 'published': False})
        self.assertTrue(calls[1][0].startswith('/storage/v1/object/mutopia-public'))
        self.assertIn(f'{OWNER}/idea-1/image.webp', calls[1][2]['prefixes'])
        self.assertIn('owner_id=eq.' + OWNER, calls[2][0])
        self.assertEqual(calls[2][1], 'DELETE')

    def test_sql_adds_a_separate_public_channel_without_relaxing_private_storage(self):
        sql = (Path(__file__).resolve().parents[1] / 'supabase.sql').read_text()
        self.assertIn("values ('idea-vault', 'idea-vault', false", sql)
        self.assertIn('alter table public.vault_records enable row level security', sql)
        self.assertIn('using ((select auth.uid()) = owner_id)', sql)
        self.assertIn('alter table public.mutopia_public_records enable row level security', sql)
        self.assertIn('for select to anon, authenticated using (true)', sql)
        self.assertIn('values (\'mutopia-public\', \'mutopia-public\', true, 5242880)', sql)
        self.assertIn("bucket_id = 'mutopia-public' and (storage.foldername(name))[1]", sql)
        self.assertNotRegex(sql, r'grant\s+[^;]*\b(?:insert|update|delete)\b[^;]*\bto\s+anon\b')


if __name__ == '__main__':
    unittest.main()
