#!/usr/bin/env python3
"""Download an owner's private cloud vault into a new local backup directory."""
import argparse
from getpass import getpass
import json
import os
from pathlib import Path
import uuid
from cloud_store import request, CloudVault


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', default='backups')
    args = parser.parse_args()
    names = ('SUPABASE_URL', 'SUPABASE_PUBLISHABLE_KEY', 'IDEA_VAULT_OWNER_ID')
    config = tuple(os.environ.get(name, '') for name in names)
    if not all(config):
        parser.error('SupabaseのURL・publishable/anonキー・本人UUIDを環境変数で設定してください')
    email = input('Supabase login email: ')
    password = getpass('Supabase login password: ')
    session = request(config[0], config[1], None, '/auth/v1/token?grant_type=password', 'POST', {'email': email, 'password': password})
    vault = CloudVault(config[0], config[1], session['access_token'], config[2])
    vault.verify()
    root = Path(args.destination).resolve() / ('cloud-' + uuid.uuid4().hex[:12])
    root.mkdir(parents=True)
    count = 0
    for record in vault.records():
        # IDs distinguish identical titles while preserving dates and file names.
        folder = Path(record['folder'])
        if folder.is_absolute() or '..' in folder.parts:
            raise ValueError('不正な保存先の記録があります')
        folder = root / folder.parent / (folder.name + '_' + record['id'][:8])
        folder.mkdir(parents=True)
        for file in record['files']:
            path = (folder / file['path']).resolve()
            if not path.is_relative_to(folder):
                raise ValueError('不正なファイルパスがあります')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(vault.read_file(record, file))
        (folder / 'metadata.json').write_text(json.dumps({k: v for k, v in record.items() if k != 'folder'}, ensure_ascii=False, indent=2), encoding='utf-8')
        (folder / 'idea.md').write_text(record['body'], encoding='utf-8')
        count += 1
    (root / 'BACKUP_COMPLETE.json').write_text(json.dumps({'records': count}), encoding='utf-8')
    print(f'Backup complete: {count} records. Save this directory securely: {root}')


if __name__ == '__main__':
    main()
