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

    def create(self, title, files=(), kind='IDEA', inbox=True, body=''):
        if kind not in KINDS:
            raise ValueError('分類が不正です')
        if not isinstance(title, str) or not title.strip():
            raise ValueError('タイトルを入力してください')
        now = stamp()
        day = now[:10]
        area = 'inbox' if inbox else {'SOURCE': 'sources', 'PRINCIPLE': 'principles'}.get(kind, 'ideas')
        with self.lock:
            destination = unique_path(self.root / area, dated(title, day))
            staging = self.root / '.staging' / uuid.uuid4().hex
            staging.mkdir()
            record = {'schema_version': 1, 'id': uuid.uuid4().hex, 'title': title.strip(),
                      'type': kind, 'inbox': inbox, 'category': '', 'tags': [],
                      'body': body, 'relations': [], 'jima_filter': '未評価', 'comment': '',
                      'created_at': now, 'imported_at': now, 'updated_at': now, 'files': []}
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
            for key in ('title', 'type', 'category', 'tags', 'body', 'relations', 'jima_filter', 'comment', 'inbox'):
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
    def allowed_hosts(self):
        hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if getattr(self.server, 'public_host', None):
            hosts.add(self.server.public_host)
        return hosts

    def authenticated(self):
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
        if self.headers.get('Host', '') not in self.allowed_hosts():
            self.send(403, {'error': 'ローカルからアクセスしてください'})
            return
        parsed = urlsplit(self.path)
        if parsed.path == '/healthz':
            self.send(200, {'status': 'ok'})
            return
        if not self.authenticated():
            return
        try:
            if parsed.path == '/api/records':
                with self.server.vault.lock:
                    records = self.server.vault.records()
                self.send(200, {'records': records})
            elif parsed.path.startswith('/api/file/'):
                parts = unquote(parsed.path).split('/')
                if len(parts) != 5:
                    raise ValueError('ファイルが見つかりません')
                record = self.server.vault.get(parts[3])
                file = next((f for f in record['files'] if f['id'] == parts[4]), None)
                if not file:
                    raise ValueError('ファイルが見つかりません')
                path = (self.server.vault.root / record['folder'] / file['path']).resolve()
                if not path.is_relative_to(self.server.vault.root):
                    raise ValueError('不正なパスです')
                safe_mimes = {'image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/avif', 'video/mp4', 'video/quicktime', 'video/webm', 'audio/mpeg', 'audio/wav', 'audio/ogg'}
                mime = file['mime'] if file['mime'] in safe_mimes else 'application/octet-stream'
                download = 'download' in parse_qs(parsed.query, keep_blank_values=True) or mime == 'application/octet-stream'
                self.send(200, path.read_bytes(), mime, file['name'] if download else None)
            else:
                name = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}.get(parsed.path)
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
        if not self.authenticated():
            return
        if not self.headers.get('Content-Type', '').startswith('application/json'):
            self.send(415, {'error': 'JSON形式で送信してください'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= MAX_REQUEST:
                self.send(413, {'error': '1回の投入は合計140MB程度までです。分けて投入してください。'})
                return
            payload = json.loads(self.rfile.read(size))
            vault = self.server.vault
            with vault.lock:
                if self.path == '/api/import':
                    groups = payload['groups']
                    if not isinstance(groups, list) or not groups:
                        raise ValueError('ファイルを選択してください')
                    # Report per-group results so an interrupted batch is never silently lost.
                    saved = []
                    errors = []
                    for group in groups:
                        try:
                            if not group.get('files'):
                                raise ValueError('空のフォルダは取り込めません')
                            saved.append(vault.create(group['title'], group['files']))
                        except (ValueError, KeyError, TypeError, OSError, binascii.Error) as error:
                            errors.append({'title': group.get('title', ''), 'error': str(error)})
                    self.send(200, {'records': saved, 'errors': errors})
                elif self.path == '/api/create':
                    self.send(201, vault.create(payload['title'], kind=payload.get('type', 'IDEA'), body=payload.get('body', '')))
                elif self.path == '/api/update':
                    self.send(200, vault.update(payload['id'], payload['changes']))
                elif self.path == '/api/transfer':
                    self.send(200, vault.transfer(payload['source'], payload['target'], payload['files']))
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
    if public and (not public_host or not password or len(password) < 24):
        parser.error('Render公開にはRENDER_EXTERNAL_HOSTNAMEと24文字以上のIDEA_VAULT_PASSWORDが必要です')
    if public and (not args.data_dir.startswith('/var/data/') or not Path('/var/data').is_mount()):
        parser.error('Render公開には/var/dataのPersistent Diskとその中の保存先が必要です')
    server = ThreadingHTTPServer(('0.0.0.0' if public else '127.0.0.1', args.port), Handler)
    server.public_host = public_host
    server.password = password
    server.vault = Vault(args.data_dir)
    print(f'IDEA VAULT: http://127.0.0.1:{args.port} / data: {server.vault.root}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
