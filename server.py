#!/usr/bin/env python3
"""IDEA VAULT: a local, dependency-free file and metadata store."""
import argparse
import base64
import binascii
import hmac
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit, parse_qs

WEB = Path(__file__).parent / 'web'
KINDS = {'SOURCE', 'PRINCIPLE', 'IDEA', 'VISUAL'}
RATINGS = {'未評価', 'GOOD', 'HOLD', 'BAD'}
MAX_REQUEST = 200 * 1024 * 1024


def stamp():
    return datetime.now().astimezone().isoformat(timespec='microseconds')


def safe_name(name):
    name = re.sub(r'[\\/\x00-\x1f<>:"|?*]', '_', name).strip(' .')
    if not name or name in {'.', '..'}:
        name = 'untitled'
    # Keep filenames within common filesystem byte limits, including date/suffix.
    suffix = Path(name).suffix[:20]
    stem = name[:-len(suffix)] if suffix else name
    while len((stem + suffix).encode('utf-8')) > 190:
        stem = stem[:-1]
    return stem + suffix


def dated(name, day):
    name = safe_name(name)
    return name if re.match(r'^\d{4}-\d{2}-\d{2}_', name) else day + '_' + name


def unique_path(directory, name):
    path = directory / name
    number = 1
    while path.exists():
        path = directory / f'{Path(name).stem}_{number:02d}{Path(name).suffix}'
        number += 1
    return path


def atomic_json(path, value):
    temp = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    try:
        with temp.open('x', encoding='utf-8') as out:
            json.dump(value, out, ensure_ascii=False, indent=2)
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class Vault:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        for area in ('inbox', 'ideas', 'sources', 'principles', '.staging'):
            (self.root / area).mkdir(exist_ok=True)

    def records(self):
        records = []
        for area in ('inbox', 'ideas', 'sources', 'principles'):
            for path in (self.root / area).glob('*/metadata.json'):
                data = json.loads(path.read_text(encoding='utf-8'))
                data['folder'] = str(path.parent.relative_to(self.root))
                records.append(data)
        return sorted(records, key=lambda x: x['imported_at'], reverse=True)

    def get(self, identifier):
        for record in self.records():
            if record['id'] == identifier:
                return record
        raise ValueError('記録が見つかりません')

    def save(self, record):
        folder = record['folder']
        data = {k: v for k, v in record.items() if k != 'folder'}
        atomic_json(self.root / folder / 'metadata.json', data)

    def create(self, title, files=(), kind='IDEA', inbox=True, body='', record_date=None, source_url=None):
        if kind not in KINDS:
            raise ValueError('分類が不正です')
        if not isinstance(title, str) or not title.strip():
            raise ValueError('タイトルを入力してください')
        from document_import import record_date as validate_date
        document_date = validate_date(record_date) if record_date is not None else None
        now = stamp()
        day = document_date or now[:10]
        area = 'inbox' if inbox else {'SOURCE': 'sources', 'PRINCIPLE': 'principles'}.get(kind, 'ideas')
        with self.lock:
            destination = unique_path(self.root / area, dated(title, day))
            staging = self.root / '.staging' / uuid.uuid4().hex
            staging.mkdir()
            record = {'schema_version': 1, 'id': uuid.uuid4().hex, 'title': title.strip(),
                      'type': kind, 'inbox': inbox, 'category': '', 'tags': [],
                      'body': body, 'relations': [], 'jima_filter': '未評価', 'comment': '',
                      'created_at': now, 'imported_at': now, 'updated_at': now, 'files': []}
            record['record_date'] = document_date or now[:10]
            if source_url is not None:
                record['source_url'] = source_url
            try:
                for item in files:
                    raw = base64.b64decode(item['data'], validate=True)
                    original = item['name']
                    mime = mimetypes.guess_type(original)[0] or 'application/octet-stream'
                    subdir = 'images' if mime.startswith('image/') else 'files'
                    (staging / subdir).mkdir(exist_ok=True)
                    path = unique_path(staging / subdir, dated(original, day))
                    with path.open('xb') as out:
                        out.write(raw)
                        out.flush()
                        os.fsync(out.fileno())
                    text = ''
                    if Path(original).suffix.lower() in {'.txt', '.md', '.markdown', '.html', '.htm', '.csv', '.json'}:
                        text = raw[:200000].decode('utf-8', errors='replace')
                    created = now
                    if item.get('lastModified'):
                        created = datetime.fromtimestamp(item['lastModified'] / 1000).astimezone().isoformat()
                    record['files'].append({'id': uuid.uuid4().hex, 'name': path.name,
                        'original_name': original, 'original_path': item.get('relativePath', original),
                        'path': str(path.relative_to(staging)), 'mime': mime, 'size': len(raw),
                        'created_at': created, 'text': text})
                if record['files']:
                    record['created_at'] = min(f['created_at'] for f in record['files'])
                (staging / 'idea.md').write_text(body, encoding='utf-8')
                atomic_json(staging / 'metadata.json', record)
                staging.rename(destination)
            except Exception:
                shutil.rmtree(staging)
                raise
            record['folder'] = str(destination.relative_to(self.root))
            return record

    def update(self, identifier, changes):
        with self.lock:
            record = self.get(identifier)
            if changes.get('type', record['type']) not in KINDS:
                raise ValueError('分類が不正です')
            if changes.get('jima_filter', record['jima_filter']) not in RATINGS:
                raise ValueError('JIMA FILTER が不正です')
            if 'record_date' in changes:
                from document_import import record_date as validate_date
                changes = {**changes, 'record_date': validate_date(changes['record_date'])}
            for key in ('title', 'category', 'body', 'comment'):
                if key in changes and not isinstance(changes[key], str):
                    raise ValueError('テキスト形式が不正です')
            if 'title' in changes and not changes['title'].strip():
                raise ValueError('タイトルを入力してください')
            if 'tags' in changes and (not isinstance(changes['tags'], list) or not all(isinstance(t, str) for t in changes['tags'])):
                raise ValueError('タグ形式が不正です')
            if 'relations' in changes:
                ids = {r['id'] for r in self.records()} - {identifier}
                if not isinstance(changes['relations'], list) or not all(isinstance(r, str) and r in ids for r in changes['relations']):
                    raise ValueError('関連先が不正です')
            if 'inbox' in changes and not isinstance(changes['inbox'], bool):
                raise ValueError('INBOX の指定が不正です')
            for key in ('title', 'type', 'category', 'tags', 'body', 'relations', 'jima_filter', 'comment', 'inbox', 'record_date'):
                if key in changes:
                    record[key] = changes[key]
            record['updated_at'] = stamp()
            # Metadata is authoritative; Markdown is a human-readable mirror.
            self.save(record)
            (self.root / record['folder'] / 'idea.md').write_text(record['body'], encoding='utf-8')
            area = 'inbox' if record['inbox'] else {'SOURCE': 'sources', 'PRINCIPLE': 'principles'}.get(record['type'], 'ideas')
            current = self.root / record['folder']
            if current.parent.name != area:
                target = unique_path(self.root / area, current.name)
                current.rename(target)
                record['folder'] = str(target.relative_to(self.root))
            return record

    def transfer(self, source_id, target_id, file_ids):
        """Copy first, commit destination, then source; failures retain file bytes."""
        with self.lock:
            if source_id == target_id:
                raise ValueError('別の記録を選択してください')
            source, target = self.get(source_id), self.get(target_id)
            selected = [f for f in source['files'] if f['id'] in file_ids]
            if not selected:
                raise ValueError('移動するファイルを選択してください')
            copied = []
            try:
                for file in selected:
                    directory = self.root / target['folder'] / Path(file['path']).parent
                    directory.mkdir(exist_ok=True)
                    path = unique_path(directory, file['name'])
                    shutil.copy2(self.root / source['folder'] / file['path'], path)
                    copied.append(path)
                    target['files'].append({**file, 'name': path.name, 'path': str(path.relative_to(self.root / target['folder']))})
                target['relations'] = sorted(set(target['relations'] + [source_id]))
                target['updated_at'] = stamp()
                self.save(target)
            except Exception:
                for path in copied:
                    path.unlink(missing_ok=True)
                raise
            source['files'] = [f for f in source['files'] if f['id'] not in file_ids]
            source['relations'] = sorted(set(source['relations'] + [target_id]))
            source['updated_at'] = stamp()
            self.save(source)
            # Retain the source note/evaluation and relation, even when empty.
            for file in selected:
                (self.root / source['folder'] / file['path']).unlink()
            return target


class Handler(BaseHTTPRequestHandler):
    def cloud_config(self):
        return getattr(self.server, 'cloud_config', None)

    def vault(self):
        return self.remote_vault if self.cloud_config() else self.server.vault

    def allowed_hosts(self):
        hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if getattr(self.server, 'public_host', None):
            hosts.add(self.server.public_host)
        return hosts

    def authenticated(self):
        config = self.cloud_config()
        if config:
            from cloud_store import CloudVault, CloudError
            authorization = self.headers.get('Authorization', '')
            if not authorization.startswith('Bearer ') or len(authorization) > 16384:
                self.send(401, {'error': 'ログインが必要です'})
                return False
            self.remote_vault = CloudVault(*config[:2], authorization[7:], config[2], self.server.cloud_lock)
            try:
                self.remote_vault.verify()
            except CloudError:
                self.send(401, {'error': 'ログインが必要です。接続設定または認証を確認してください。'})
                return False
            return True
        password = getattr(self.server, 'password', None)
        if password is None:
            return True
        try:
            scheme, encoded = self.headers.get('Authorization', '').split(' ', 1)
            decoded = base64.b64decode(encoded, validate=True).decode('utf-8')
            username, supplied = decoded.split(':', 1)
            valid = scheme.lower() == 'basic' and hmac.compare_digest(username.encode(), b'jima') and hmac.compare_digest(supplied.encode(), password.encode())
        except (ValueError, UnicodeError, binascii.Error):
            valid = False
        if not valid:
            self.send(401, {'error': 'ログインが必要です'}, authenticate=True)
        return valid

    def log_message(self, fmt, *args):
        # Avoid logging titles, filenames, and queries from a private vault.
        pass

    def send(self, status, body, mime='application/json; charset=utf-8', attachment=None, authenticate=False):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        if getattr(self.server, 'public_host', None):
            self.send_header('Strict-Transport-Security', 'max-age=31536000')
        if authenticate:
            self.send_header('WWW-Authenticate', 'Basic realm="IDEA VAULT", charset="UTF-8"')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob:; media-src 'self' blob:; style-src 'self'; script-src 'self'; frame-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if attachment:
            from urllib.parse import quote
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(attachment))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == '/healthz':
            self.send(200, {'status': 'ok'})
            return
        if self.headers.get('Host', '') not in self.allowed_hosts():
            self.send(403, {'error': 'ローカルからアクセスしてください'})
            return
        if parsed.path == '/api/config':
            self.send(200, {'storage': 'cloud' if self.cloud_config() else 'local'})
            return
        public_files = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css', '/recovery.js': 'recovery.js'}
        if self.cloud_config() and parsed.path in public_files:
            name = public_files[parsed.path]
            self.send(200, (WEB / name).read_bytes(), mimetypes.guess_type(name)[0] + '; charset=utf-8')
            return
        if parsed.path == '/api/mutopia/public-records':
            config = self.cloud_config()
            if not config:
                self.send(503, {'code': 'MUTOPIA_PUBLICATION_UNAVAILABLE'})
                return
            try:
                from cloud_store import CloudVault
                records = CloudVault.public_mutopia_records(config[0], config[1])
                self.send(200, {'records': records})
            except Exception:
                self.send(503, {'error': 'MUTOPIA公開データを読み込めません。公開テーブルの設定を確認してください。'})
            return
        if not self.authenticated():
            return
        try:
            if parsed.path == '/api/records':
                vault = self.vault()
                with vault.lock:
                    records = vault.records()
                self.send(200, {'records': records})
            elif parsed.path == '/api/mutopia/publications':
                if not self.cloud_config():
                    self.send(503, {'error': 'MUTOPIA公開にはクラウド版IDEA VAULTが必要です。'})
                    return
                self.send(200, {'ids': [row['id'] for row in self.remote_vault.mutopia_publications()]})
            elif parsed.path.startswith('/api/file/'):
                parts = unquote(parsed.path).split('/')
                if len(parts) != 5:
                    raise ValueError('ファイルが見つかりません')
                vault = self.vault()
                record = vault.get(parts[3])
                file = next((f for f in record['files'] if f['id'] == parts[4]), None)
                if not file:
                    raise ValueError('ファイルが見つかりません')
                if self.cloud_config():
                    contents = vault.read_file(record, file)
                else:
                    path = (vault.root / record['folder'] / file['path']).resolve()
                    if not path.is_relative_to(vault.root):
                        raise ValueError('不正なパスです')
                    contents = path.read_bytes()
                safe_mimes = {'image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/avif', 'video/mp4', 'video/quicktime', 'video/webm', 'audio/mpeg', 'audio/wav', 'audio/ogg'}
                mime = file['mime'] if file['mime'] in safe_mimes else 'application/octet-stream'
                download = 'download' in parse_qs(parsed.query, keep_blank_values=True) or mime == 'application/octet-stream'
                self.send(200, contents, mime, file['name'] if download else None)
            else:
                name = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css', '/recovery.js': 'recovery.js'}.get(parsed.path)
                if not name:
                    self.send(404, {'error': '見つかりません'})
                    return
                self.send(200, (WEB / name).read_bytes(), mimetypes.guess_type(name)[0] + '; charset=utf-8')
        except (ValueError, FileNotFoundError) as error:
            self.send(404, {'error': str(error)})
        except Exception:
            self.send(500, {'error': '保存データを読み込めません。サーバー側の保存先を確認してください。'})

    def do_POST(self):
        # Reject cross-site writes and DNS rebinding to the loopback service.
        host = self.headers.get('Host', '')
        allowed = self.allowed_hosts()
        origin = self.headers.get('Origin')
        origins = {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}
        if getattr(self.server, 'public_host', None):
            origins.add('https://' + self.server.public_host)
        if host not in allowed or (origin and origin not in origins):
            self.send(403, {'error': 'ローカルの同一オリジンからアクセスしてください'})
            return
        auth_operation = bool(self.cloud_config() and self.path in {'/api/login', '/api/refresh', '/api/recovery-check', '/api/reset-password'})
        if not auth_operation and not self.authenticated():
            return
        if not self.headers.get('Content-Type', '').startswith('application/json'):
            self.send(415, {'error': 'JSON形式で送信してください'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if auth_operation and size > 16384:
                self.send(413, {'error': 'リクエストが大きすぎます'})
                return
            limit = 72 * 1024 * 1024 if self.cloud_config() else MAX_REQUEST
            if not 0 < size <= limit:
                self.send(413, {'error': '投入サイズが大きすぎます。クラウドでは合計50MB、ローカルでは合計140MBまでに分けて投入してください。'})
                return
            payload = json.loads(self.rfile.read(size))
            if auth_operation:
                from cloud_store import request, CloudVault, CloudError
                config = self.cloud_config()
                if self.path in {'/api/recovery-check', '/api/reset-password'}:
                    # No admin credentials, local persistence, or recovery session
                    # promoted into a normal vault login. Supabase is authoritative.
                    token = None
                    try:
                        if not isinstance(payload, dict):
                            raise CloudError('Invalid request')
                        password = payload.get('password')
                        if self.path == '/api/reset-password' and (not isinstance(password, str) or not 12 <= len(password) <= 1024):
                            self.send(400, {'error': 'パスワードは12文字以上1024文字以内で入力してください。'})
                            return
                        if payload.get('type') != 'recovery':
                            raise CloudError('Invalid recovery type')
                        if 'token_hash' in payload:
                            # Verify only on explicit submission: mail scanners and
                            # page loads must not consume a one-time recovery link.
                            hashed = payload['token_hash']
                            if self.path != '/api/reset-password' or not isinstance(hashed, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,512}', hashed) or 'access_token' in payload:
                                raise CloudError('Invalid recovery hash')
                            recovered = request(config[0], config[1], None, '/auth/v1/verify', 'POST', {'token_hash': hashed, 'type': 'recovery'})
                            token = recovered['access_token']
                        else:
                            token = payload.get('access_token')
                            if not isinstance(token, str) or not token or len(token) > 12000:
                                raise CloudError('Invalid session')
                        vault = CloudVault(config[0], config[1], token, config[2])
                        vault.verify()  # GET /user validates signature/expiry AND owner UUID.
                        if self.path == '/api/recovery-check':
                            self.send(200, {'valid': True})
                            return
                        request(config[0], config[1], token, '/auth/v1/user', 'PUT', {'password': password})
                    except (CloudError, KeyError, TypeError):
                        self.send(400, {'error': '再設定リンクが無効・期限切れ、またはこの保管庫の本人用ではありません。パスワード要件・接続設定を確認し、新しいメールを発行してください。'})
                        return
                    # Best-effort global refresh-session revocation. Supabase access
                    # JWTs may still live until expiry; never claim immediate revocation.
                    try:
                        request(config[0], config[1], token, '/auth/v1/logout?scope=global', 'POST', {})
                        revoked = True
                    except CloudError:
                        revoked = False
                    self.send(200, {'updated': True, 'sessions_revoked': revoked})
                    return
                grant = 'password' if self.path == '/api/login' else 'refresh_token'
                fields = {'email': payload.get('email', ''), 'password': payload.get('password', '')} if grant == 'password' else {'refresh_token': payload.get('refresh_token', '')}
                try:
                    session = request(config[0], config[1], None, '/auth/v1/token?grant_type=' + grant, 'POST', fields)
                    CloudVault(config[0], config[1], session['access_token'], config[2]).verify()
                except (CloudError, KeyError):
                    self.send(401, {'error': 'ログインできませんでした。認証情報・接続設定を確認してください。'})
                    return
                self.send(200, {field: session[field] for field in ('access_token', 'refresh_token', 'expires_in')})
                return
            vault = self.vault()
            with vault.lock:
                if self.path == '/api/import':
                    groups = payload['groups']
                    if not isinstance(groups, list) or not groups:
                        raise ValueError('ファイルを選択してください')
                    if self.cloud_config():
                        encoded_files = [item.get('data', '') for group in groups if isinstance(group, dict) for item in group.get('files', []) if isinstance(item, dict)]
                        total = sum((len(value) // 4) * 3 - len(value) + len(value.rstrip('=')) for value in encoded_files if isinstance(value, str))
                        if total > 50 * 1024 * 1024:
                            self.send(413, {'error': '無料クラウド版は1回の投入合計50MBまでです'})
                            return
                    # Report per-group results so an interrupted batch is never silently lost.
                    saved = []
                    errors = []
                    for group in groups:
                        try:
                            if not group.get('files'):
                                raise ValueError('空のフォルダは取り込めません')
                            from document_import import markdown_group
                            metadata = markdown_group(group)
                            if metadata:
                                saved.append(vault.create(files=group['files'], **metadata))
                            else:
                                saved.append(vault.create(group['title'], group['files']))
                        except (ValueError, KeyError, TypeError, OSError, binascii.Error) as error:
                            errors.append({'title': group.get('title', ''), 'error': str(error)})
                    self.send(200, {'records': saved, 'errors': errors})
                elif self.path == '/api/github-pending':
                    from document_import import github_pending
                    self.send(200, github_pending(vault))
                elif self.path == '/api/sync-github':
                    from document_import import sync_github_documents
                    self.send(200, sync_github_documents(vault, payload.get('attempted', [])))
                elif self.path == '/api/import-github':
                    from document_import import fetch_github_bundle, github_location
                    source, _, _ = github_location(payload.get('url'))
                    existing = next((record for record in vault.records() if record.get('source_url') == source), None)
                    if existing:
                        self.send(200, {'record': existing, 'already_imported': True})
                    else:
                        source, metadata, files = fetch_github_bundle(source)
                        record = vault.create(files=files, source_url=source, **metadata)
                        self.send(201, {'record': record, 'already_imported': False})
                elif self.path == '/api/create':
                    self.send(201, vault.create(payload['title'], kind=payload.get('type', 'IDEA'), body=payload.get('body', ''), record_date=payload.get('record_date')))
                elif self.path == '/api/update':
                    self.send(200, vault.update(payload['id'], payload['changes']))
                elif self.path == '/api/transfer':
                    self.send(200, vault.transfer(payload['source'], payload['target'], payload['files']))
                elif self.path == '/api/mutopia/publish':
                    if not self.cloud_config():
                        self.send(503, {'error': 'MUTOPIA公開にはクラウド版IDEA VAULTが必要です。'})
                    elif not isinstance(payload.get('record_id'), str) or len(payload['record_id']) > 128:
                        self.send(400, {'error': '公開する記録を確認してください。'})
                    elif payload.get('published') is True:
                        self.send(200, vault.publish_to_mutopia(payload['record_id']))
                    elif payload.get('published') is False:
                        self.send(200, vault.unpublish_from_mutopia(payload['record_id']))
                    else:
                        self.send(400, {'error': '公開状態を指定してください。'})
                elif self.path == '/api/logout' and self.cloud_config():
                    vault.call('/auth/v1/logout', 'POST', {})
                    self.send(200, {'status': 'signed_out'})
                else:
                    self.send(404, {'error': '見つかりません'})
        except (ValueError, KeyError, TypeError) as error:
            self.send(400, {'error': str(error)})
        except OSError:
            self.send(500, {'error': '保存できませんでした。空き容量と保存先の権限を確認してください。'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', '8765')))
    parser.add_argument('--data-dir', default=os.environ.get('IDEA_VAULT_DATA', str(Path(__file__).parent / 'vault')))
    args = parser.parse_args()
    public_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
    public = bool(public_host or os.environ.get('RENDER'))
    password = os.environ.get('IDEA_VAULT_PASSWORD')
    cloud = os.environ.get('IDEA_VAULT_STORAGE') == 'supabase'
    config = None
    if cloud:
        url, public_key, owner = (os.environ.get(n, '') for n in ('SUPABASE_URL', 'SUPABASE_PUBLISHABLE_KEY', 'IDEA_VAULT_OWNER_ID'))
        if not re.fullmatch(r'https://[a-z0-9-]+\.supabase\.co', url) or not public_key or not owner:
            parser.error('SupabaseのURL・publishable/anonキー・本人のユーザーUUIDを設定してください')
        try:
            uuid.UUID(owner)
        except ValueError:
            parser.error('IDEA_VAULT_OWNER_IDは本人のSupabaseユーザーUUIDにしてください')
        if public_key.startswith('sb_secret_'):
            parser.error('service-role/secretキーを使わずpublishable/anonキーを設定してください')
        if public_key.startswith('eyJ'):
            try:
                claims = public_key.split('.')[1]
                role = json.loads(base64.urlsafe_b64decode(claims + '=' * (-len(claims) % 4))).get('role')
                if role != 'anon':
                    parser.error('Supabaseキーはanonキーを使用してください')
            except (ValueError, IndexError):
                parser.error('Supabaseの公開キー形式を確認してください')
        config = (url, public_key, owner)
    if public and (not public_host or not cloud):
        parser.error('Render無料公開ではSupabase保存と本人ログインの設定が必須です。ローカル保存へは切り替えません')
    server = ThreadingHTTPServer(('0.0.0.0' if public else '127.0.0.1', args.port), Handler)
    server.public_host = public_host
    server.password = password if not cloud else None
    server.cloud_config = config
    server.cloud_lock = threading.RLock()
    if not cloud:
        server.vault = Vault(args.data_dir)
    print(f'IDEA VAULT: port {args.port} / storage: {"Supabase (private)" if cloud else server.vault.root}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
