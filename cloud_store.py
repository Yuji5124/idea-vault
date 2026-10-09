"""Supabase REST storage using the signed-in owner's JWT, never a service-role key."""
import base64
import json
import mimetypes
import re
import threading
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class CloudError(ValueError):
    pass


def request(url, public_key, token, path, method='GET', payload=None, raw=None, mime=None, binary=False):
    headers = {'apikey': public_key, 'Authorization': 'Bearer ' + (token or public_key)}
    data = raw
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        headers['Content-Type'] = 'application/json'
    elif raw is not None:
        headers['Content-Type'] = mime or 'application/octet-stream'
    if path.startswith('/rest/'):
        headers['Prefer'] = 'return=representation'
    try:
        with urlopen(Request(url.rstrip('/') + path, data=data, headers=headers, method=method), timeout=45) as response:
            body = response.read()
            return json.loads(body) if not binary and response.headers.get('Content-Type', '').startswith('application/json') and body else body
    except HTTPError as error:
        # Avoid returning provider bodies containing user fields or secrets.
        stage = 'Storageの添付ファイル操作' if path.startswith('/storage/') else '記録DBの操作' if path.startswith('/rest/') else '認証操作'
        raise CloudError(f'クラウド保存先が{stage}を拒否しました（HTTP {error.code}）。接続設定・権限・利用枠を確認してください。') from None
    except URLError:
        raise CloudError('クラウド保存先へ接続できません。時間を置いて再試行してください。') from None


class CloudVault:
    def __init__(self, url, public_key, token, owner, lock=None):
        self.url, self.public_key, self.token, self.owner = url, public_key, token, owner
        self.lock = lock or threading.RLock()

    def call(self, path, method='GET', payload=None, raw=None, mime=None, binary=False):
        return request(self.url, self.public_key, self.token, path, method, payload, raw, mime, binary)

    def verify(self):
        user = self.call('/auth/v1/user')
        if user.get('id') != self.owner:
            raise CloudError('この保管庫へのアクセスは許可されていません。')

    def records(self):
        records, offset = [], 0
        while True:
            rows = self.call('/rest/v1/vault_records?select=metadata&owner_id=eq.' + quote(self.owner, safe='') + f'&order=id.asc&limit=500&offset={offset}')
            records.extend(row['metadata'] for row in rows)
            if len(rows) < 500:
                break
            offset += len(rows)
        return sorted(records, key=lambda r: r['imported_at'], reverse=True)

    def get(self, identifier):
        rows = self.call('/rest/v1/vault_records?select=metadata&id=eq.' + quote(identifier, safe='') + '&owner_id=eq.' + quote(self.owner, safe=''))
        if len(rows) == 1:
            return rows[0]['metadata']
        raise CloudError('記録が見つかりません。')

    def object_path(self, record, file):
        # IDs and paths originate from our generated metadata, not request paths.
        return self.owner + '/' + record['id'] + '/' + file.get('storage_path', file['path'])

    def read_file(self, record, file):
        return self.call('/storage/v1/object/authenticated/idea-vault/' + quote(self.object_path(record, file), safe='/'), binary=True)

    def upload(self, record, file, raw):
        self.call('/storage/v1/object/idea-vault/' + quote(self.object_path(record, file), safe='/'), 'POST', raw=raw, mime=file['mime'])

    def remove(self, record, files):
        if files:
            self.call('/storage/v1/object/idea-vault', 'DELETE', {'prefixes': [self.object_path(record, f) for f in files]})

    def save(self, record, new=False):
        if new:
            self.call('/rest/v1/vault_records', 'POST', {'id': record['id'], 'owner_id': self.owner, 'metadata': record})
        else:
            rows = self.call('/rest/v1/vault_records?id=eq.' + quote(record['id'], safe='') + '&owner_id=eq.' + quote(self.owner, safe=''), 'PATCH', {'metadata': record})
            if not rows:
                raise CloudError('記録を更新できませんでした。')

    def create(self, title, files=(), kind='IDEA', inbox=True, body='', record_date=None, source_url=None):
        from server import stamp, dated, KINDS
        if kind not in KINDS or not isinstance(title, str) or not title.strip() or not isinstance(body, str):
            raise CloudError('タイトル・分類・本文を確認してください。')
        from document_import import record_date as validate_date
        document_date = validate_date(record_date) if record_date is not None else None
        now = stamp()
        record = {'schema_version': 1, 'id': uuid.uuid4().hex, 'title': title.strip(), 'type': kind, 'inbox': inbox,
                  'category': '', 'tags': [], 'body': body, 'relations': [], 'jima_filter': '未評価', 'comment': '',
                  'created_at': now, 'imported_at': now, 'updated_at': now, 'files': [],
                  'folder': ('inbox' if inbox else {'SOURCE': 'sources', 'PRINCIPLE': 'principles'}.get(kind, 'ideas')) + '/' + dated(title, document_date or now[:10])}
        record['record_date'] = document_date or now[:10]
        if source_url is not None:
            record['source_url'] = source_url
        used = set()
        try:
            from pathlib import Path
            from datetime import datetime
            for item in files:
                raw = base64.b64decode(item['data'], validate=True)
                if len(raw) > 50 * 1024 * 1024:
                    raise CloudError('無料クラウド保存では1ファイル50MBまでです。')
                name = dated(item['name'], document_date or now[:10])
                candidate, number = name, 1
                while candidate in used:
                    candidate = f'{Path(name).stem}_{number:02d}{Path(name).suffix}'
                    number += 1
                used.add(candidate)
                mime = mimetypes.guess_type(item['name'])[0] or 'application/octet-stream'
                created = datetime.fromtimestamp(item['lastModified'] / 1000).astimezone().isoformat() if item.get('lastModified') else now
                file_id = uuid.uuid4().hex
                extension = Path(item['name']).suffix.lower()
                if not re.fullmatch(r'\.[a-z0-9]{1,16}', extension):
                    extension = ''
                area = 'images/' if mime.startswith('image/') else 'files/'
                # Supabase Storage rejects Unicode object keys. Keep the original
                # names/local backup paths in metadata, use ASCII IDs remotely.
                file = {'id': file_id, 'storage_path': area + file_id + extension, 'name': candidate, 'original_name': item['name'],
                        'original_path': item.get('relativePath', item['name']), 'path': ('images/' if mime.startswith('image/') else 'files/') + candidate,
                        'mime': mime, 'size': len(raw), 'created_at': created,
                        'text': raw[:200000].decode('utf-8', errors='replace') if Path(item['name']).suffix.lower() in {'.txt', '.md', '.markdown', '.html', '.htm', '.csv', '.json'} else ''}
                self.upload(record, file, raw)
                record['files'].append(file)
            if record['files']:
                record['created_at'] = min(f['created_at'] for f in record['files'])
            self.save(record, new=True)
        except Exception:
            # On ambiguous network failures retain uploaded bytes: the metadata
            # commit may have succeeded. Never delete potentially committed data.
            raise
        return record

    def update(self, identifier, changes):
        from server import KINDS, RATINGS, stamp
        record = self.get(identifier)
        if changes.get('type', record['type']) not in KINDS or changes.get('jima_filter', record['jima_filter']) not in RATINGS:
            raise CloudError('分類・評価を確認してください。')
        if 'record_date' in changes:
            from document_import import record_date as validate_date
            changes = {**changes, 'record_date': validate_date(changes['record_date'])}
        for name in ('title', 'category', 'body', 'comment'):
            if name in changes and not isinstance(changes[name], str):
                raise CloudError('テキスト形式が不正です。')
        if 'title' in changes and not changes['title'].strip():
            raise CloudError('タイトルを入力してください。')
        if 'tags' in changes and (not isinstance(changes['tags'], list) or not all(isinstance(t, str) for t in changes['tags'])):
            raise CloudError('タグ形式が不正です。')
        if 'inbox' in changes and not isinstance(changes['inbox'], bool):
            raise CloudError('INBOXの指定が不正です。')
        if 'relations' in changes:
            ids = {r['id'] for r in self.records()} - {identifier}
            if not isinstance(changes['relations'], list) or not all(isinstance(r, str) and r in ids for r in changes['relations']):
                raise CloudError('関連先を確認してください。')
        for field in ('title', 'type', 'category', 'body', 'comment', 'tags', 'inbox', 'relations', 'jima_filter', 'record_date'):
            if field in changes:
                record[field] = changes[field]
        record['updated_at'] = stamp()
        area = 'inbox' if record['inbox'] else {'SOURCE': 'sources', 'PRINCIPLE': 'principles'}.get(record['type'], 'ideas')
        record['folder'] = area + '/' + record['folder'].split('/', 1)[1]
        self.save(record)
        return record

    def transfer(self, source_id, target_id, file_ids):
        from server import stamp
        from pathlib import Path
        if source_id == target_id:
            raise CloudError('別の記録を選択してください。')
        source, target = self.get(source_id), self.get(target_id)
        selected = [f for f in source['files'] if f['id'] in file_ids]
        if not selected:
            raise CloudError('ファイルを選択してください。')
        used = {f['name'] for f in target['files']}
        existing_ids = {f['id'] for f in target['files']}
        for file in selected:
            if file['id'] in existing_ids:
                continue  # Retry after a destination commit: do not copy again.
            name, number = file['name'], 1
            while name in used:
                name = f'{Path(file["name"]).stem}_{number:02d}{Path(file["name"]).suffix}'
                number += 1
            used.add(name)
            copy = {**file, 'name': name, 'path': file['path'].split('/')[0] + '/' + name}
            self.upload(target, copy, self.read_file(source, file))
            target['files'].append(copy)
        target['relations'] = sorted(set(target['relations'] + [source_id]))
        target['updated_at'] = stamp()
        self.save(target)
        source['files'] = [f for f in source['files'] if f['id'] not in file_ids]
        source['relations'] = sorted(set(source['relations'] + [target_id]))
        source['updated_at'] = stamp()
        self.save(source)
        # Keep source object copies as recovery material. Their original record
        # metadata is no longer active; the bytes remain private under owner RLS.
        return target
