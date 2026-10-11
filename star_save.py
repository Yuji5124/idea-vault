"""Owner-authenticated capture, deterministic retries and Storage read-back."""
import base64
import binascii
import hashlib
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def capture_status(vault, payload):
    identifier = payload.get('id', '')
    if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}', identifier):
        raise ValueError('保存IDが不正です。')
    record = vault.get(identifier)
    # Read the actual private objects, not just metadata or a UI acknowledgment.
    return {'id': record['id'], 'hashes': [digest(vault.read_file(record, item)) for item in record['files']]}


def save_capture(vault, payload):
    source = payload.get('source_url', '')
    parsed = urlsplit(source) if isinstance(source, str) else None
    if not parsed or parsed.scheme != 'https' or parsed.netloc != 'chatgpt.com' or not re.fullmatch(r'/c/[a-zA-Z0-9-]{1,100}', parsed.path) or parsed.query or parsed.fragment:
        raise ValueError('通常のChatGPT会話URLが必要です。一時チャットには対応していません。')
    title, body, images = (payload.get(key) for key in ('title', 'body', 'images'))
    if not isinstance(title, str) or not title.strip() or len(title) > 200 or not isinstance(body, str) or not body.strip() or len(body.encode()) > 2 * 1024 * 1024:
        raise ValueError('タイトルまたは本文の形式・サイズを確認してください。')
    if not isinstance(images, list) or len(images) > 8:
        raise ValueError('画像は8枚までです。')
    filename = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', title).strip()[:100] or 'idea'
    day = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    files = [{'name': filename + '.md', 'data': base64.b64encode(body.encode()).decode()}]
    hashes = [digest(body.encode())]
    total = 0
    for index, item in enumerate(images):
        try:
            mime, encoded = item['mime'], item['data']
            if not isinstance(encoded, str) or len(encoded) > 28 * 1024 * 1024:
                raise ValueError()
            raw = base64.b64decode(encoded, validate=True)
        except (KeyError, TypeError, ValueError, binascii.Error):
            raise ValueError('画像データが不正です。') from None
        extension = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}.get(mime)
        valid = raw.startswith(b'\x89PNG\r\n\x1a\n') if mime == 'image/png' else raw.startswith(b'\xff\xd8\xff') if mime == 'image/jpeg' else raw.startswith(b'RIFF') and raw[8:12] == b'WEBP' if mime == 'image/webp' else False
        total += len(raw)
        if not extension or not valid or not raw or len(raw) > 20 * 1024 * 1024 or total > 30 * 1024 * 1024:
            raise ValueError('画像はPNG・JPEG・WebP、1枚20MB、合計30MBまでです。')
        hashes.append(digest(raw))
        files.append({'name': filename + f'_{index+1:02}' + extension, 'data': encoded})
    identifier = digest((source + '\n' + '\n'.join(hashes)).encode())[:32]
    existing = next((r for r in vault.records() if r['id'] == identifier), None)
    if existing and existing.get('deleted_at'):
        raise ValueError('ゴミ箱の記録です。IDEA VAULTで復元してください。')
    if not existing:
        vault.create(title, files=files, kind='IDEA', inbox=True, body=body, record_date=day, source_url=source, identifier=identifier)
    status = capture_status(vault, {'id': identifier})
    if status['hashes'] != hashes:
        raise ValueError('保存済みファイルの再取得検証に失敗しました。')
    return {**status, 'already_saved': bool(existing), 'texts': 1, 'images': len(images), 'verified': True}
