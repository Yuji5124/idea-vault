import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from record_trash import manage
from server import Vault


def upload(name, contents=b'private attachment'):
    import base64
    return {'name': name, 'data': base64.b64encode(contents).decode()}


class TrashTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.vault = Vault(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_trash_hides_record_but_keeps_data_and_restore_returns_it(self):
        record = self.vault.create('保管する記録', [upload('note.txt')], body='本文')
        original_file = self.vault.root / record['folder'] / record['files'][0]['path']

        trashed = manage(self.vault, {'id': record['id'], 'action': 'trash'})
        self.assertTrue(trashed['deleted_at'])
        self.assertTrue(original_file.exists())
        self.assertTrue(self.vault.get(record['id'])['deleted_at'])

        restored = manage(self.vault, {'id': record['id'], 'action': 'restore'})
        self.assertTrue(restored['restored'])
        self.assertNotIn('deleted_at', self.vault.get(record['id']))
        self.assertTrue(original_file.exists())

    def test_permanent_delete_requires_exact_name_and_no_relation_references(self):
        source = self.vault.create('参照元')
        target = self.vault.create('対象')
        self.vault.update(source['id'], {'relations': [target['id']]})
        manage(self.vault, {'id': target['id'], 'action': 'trash'})

        with self.assertRaisesRegex(ValueError, '記録名'):
            manage(self.vault, {'id': target['id'], 'action': 'purge', 'confirmation': '違う名前'})
        with self.assertRaisesRegex(ValueError, '関連されています'):
            manage(self.vault, {'id': target['id'], 'action': 'purge', 'confirmation': '対象'})
        self.assertEqual(self.vault.get(target['id'])['title'], '対象')

    def test_confirmed_purge_removes_only_trashed_record_folder(self):
        record = self.vault.create('完全削除する記録', [upload('note.txt')], body='本文')
        other = self.vault.create('残す記録')
        folder = self.vault.root / record['folder']
        manage(self.vault, {'id': record['id'], 'action': 'trash'})

        result = manage(self.vault, {'id': record['id'], 'action': 'purge', 'confirmation': record['title']})
        self.assertEqual(result, {'id': record['id'], 'purged': True})
        self.assertFalse(folder.exists())
        self.assertEqual(self.vault.get(other['id'])['title'], '残す記録')
        with self.assertRaisesRegex(ValueError, '見つかりません'):
            self.vault.get(record['id'])

    def test_cloud_trash_unpublishes_before_hiding_record(self):
        from cloud_store import CloudVault
        owner = '11111111-1111-4111-8111-111111111111'
        cloud = CloudVault('https://example.supabase.co', 'publishable', 'owner-jwt', owner)
        record = {'id': 'idea-1', 'title': '公開中の記録', 'files': [], 'updated_at': 'old'}
        with patch.object(cloud, 'get', return_value=record), \
             patch.object(cloud, 'mutopia_publications', return_value=[{'id': 'idea-1'}]), \
             patch.object(cloud, 'unpublish_from_mutopia') as unpublish, \
             patch.object(cloud, 'save') as save:
            result = manage(cloud, {'id': 'idea-1', 'action': 'trash'})
        unpublish.assert_called_once_with('idea-1')
        save.assert_called_once()
        self.assertTrue(record['deleted_at'])
        self.assertEqual(result['id'], 'idea-1')


if __name__ == '__main__':
    unittest.main()
