"""Owner-only recoverable trash and explicitly confirmed permanent deletion."""
from pathlib import Path
import shutil
from urllib.parse import quote


def _retained_files(record):
    found = {}
    groups = [record.get('files', []), record.get('archived_files', [])]
    groups.extend(item.get('files', []) for item in record.get('history', []))
    for files in groups:
        for item in files:
            found[item['id']] = item
            thumbnail = item.get('thumbnail')
            if thumbnail:
                found[thumbnail['id']] = thumbnail
    return list(found.values())


def _file_key(vault, record, item):
    if hasattr(vault, 'object_path'):
        return vault.object_path(record, item)
    return str((vault.root / record['folder'] / item['path']).resolve())


def manage(vault, payload):
    from server import stamp

    identifier = payload.get('id')
    action = payload.get('action')
    if not isinstance(identifier, str) or not identifier or len(identifier) > 128:
        raise ValueError('記録を確認してください。')
    record = vault.get(identifier)

    if action == 'trash':
        if record.get('purging'):
            raise ValueError('完全削除処理中です。')
        if not record.get('deleted_at'):
            if hasattr(vault, 'mutopia_publications'):
                try:
                    published = {row['id'] for row in vault.mutopia_publications()}
                except ValueError as error:
                    if 'HTTP 404' not in str(error):
                        raise
                    published = set()  # Older Supabase projects may not have the optional publication table yet.
                if identifier in published:
                    vault.unpublish_from_mutopia(identifier)
            record['deleted_at'] = stamp()
            record['updated_at'] = record['deleted_at']
            vault.save(record)
        return {'id': identifier, 'deleted_at': record['deleted_at']}

    if action == 'restore':
        if not record.get('deleted_at'):
            raise ValueError('この記録はゴミ箱にありません。')
        if record.get('purging'):
            raise ValueError('完全削除処理中の記録は復元できません。完全削除を再試行してください。')
        record.pop('deleted_at', None)
        record['updated_at'] = stamp()
        vault.save(record)
        return {'id': identifier, 'restored': True}

    if action != 'purge':
        raise ValueError('操作を確認してください。')
    if not record.get('deleted_at') or payload.get('confirmation') != record.get('title'):
        raise ValueError('ゴミ箱の記録名を入力して確認してください。')
    all_records = vault.records()
    if any(identifier in other.get('relations', []) for other in all_records if other['id'] != identifier):
        raise ValueError('他の記録から関連されています。関連を解除してから完全削除してください。')

    files = _retained_files(record)
    keys_used_elsewhere = {
        _file_key(vault, other, item)
        for other in all_records if other['id'] != identifier
        for item in _retained_files(other)
    }
    deletable = [item for item in files if _file_key(vault, record, item) not in keys_used_elsewhere]
    if len(deletable) != len(files):
        raise ValueError('他の記録と共有されている添付があるため完全削除できません。')

    record['purging'] = True
    record['updated_at'] = stamp()
    vault.save(record)
    if hasattr(vault, 'object_path'):
        vault.remove(record, deletable)
        vault.call(
            '/rest/v1/vault_records?id=eq.' + quote(identifier, safe='')
            + '&owner_id=eq.' + quote(vault.owner, safe=''),
            'DELETE',
        )
        if any(item['id'] == identifier for item in vault.records()):
            raise ValueError('完全削除の確定を確認できません。安全のためゴミ箱に保持しました。')
    else:
        folder = (vault.root / record['folder']).resolve()
        if not folder.is_relative_to(vault.root) or folder == vault.root:
            raise ValueError('保存先を安全に確認できないため削除を中止しました。')
        shutil.rmtree(folder)
    return {'id': identifier, 'purged': True}
