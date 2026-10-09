"""Markdown metadata and bounded GitHub import; no private data is cached on disk."""
import base64
from datetime import date
from pathlib import PurePosixPath
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024


def record_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('資料の日付はYYYY-MM-DD形式で入力してください')
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError('資料の日付が存在する日付ではありません') from None


def markdown_metadata(name, raw):
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError('Markdown資料は2MB以内にしてください')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeError:
        raise ValueError('Markdown資料はUTF-8で保存してください') from None
    stem = PurePosixPath(name).stem
    filename_date = re.match(r'^(\d{4}-\d{2}-\d{2})[_ -](.+)$', stem)
    title = filename_date[2] if filename_date else stem
    saved_date = record_date(filename_date[1]) if filename_date else None
    # Metadata is deliberately bounded to the document header. Dates in the
    # main text (experiments/history) must not change the record's date.
    header = text.splitlines()[:20]
    frontmatter = len(header) > 1 and header[0].strip() == '---'
    for index, line in enumerate(header):
        if frontmatter and index != 0 and line.strip() == '---':
            frontmatter = False
            continue
        if frontmatter:
            match = re.fullmatch(r'title:\s*(.+)', line)
            if match:
                title = match[1].strip().strip('"\'')
            match = re.fullmatch(r'date:\s*["\']?(\d{4}-\d{2}-\d{2})["\']?\s*', line)
            if match:
                saved_date = record_date(match[1])
        elif re.match(r'^#\s+', line):
            title = re.sub(r'^#\s+', '', line).strip().rstrip('#').strip()
            title = re.sub(r'\s*[—–－]\s*アイデア保存$', '', title)
            break
    # A 保存日 label below the heading is more authoritative than filename.
    for line in header:
        clean = re.sub(r'[*`]', '', line).strip().lstrip('- ').strip()
        match = re.fullmatch(r'保存日\s*[：:]\s*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?\s*', clean)
        if match:
            saved_date = record_date(f'{int(match[1]):04d}-{int(match[2]):02d}-{int(match[3]):02d}')
            break
    if not title.strip():
        raise ValueError('資料のタイトルを確認してください')
    return {'title': title.strip(), 'body': text, 'record_date': saved_date}


def markdown_group(group):
    files = group.get('files', [])
    if len(files) != 1:
        return None
    item = files[0]
    name = item.get('name', '')
    if PurePosixPath(name).suffix.lower() not in {'.md', '.markdown'} or '/' in item.get('relativePath', name):
        return None  # Preserve folder grouping and mixed-file imports.
    try:
        raw = base64.b64decode(item['data'], validate=True)
    except (ValueError, TypeError):
        raise ValueError('Markdown資料のファイル形式を確認してください') from None
    return markdown_metadata(name, raw)


def github_location(url):
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError('GitHub資料のリンクを入力してください')
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc != 'github.com' or parsed.query or parsed.fragment:
        raise ValueError('github.comの資料リンクを使用してください（クエリ・フラグメント不可）')
    prefix = '/Yuji5124/idea-vault/blob/main/ideas/'
    path = unquote(parsed.path)
    if not path.startswith(prefix):
        raise ValueError('Yuji5124/idea-vaultのmainブランチにあるideas内のMarkdown資料を指定してください')
    relative = path[len(prefix):]
    if any(part in {'', '.', '..'} for part in relative.split('/')) or any(char in relative for char in ('\\', '\x00', '\r', '\n', '?', '#')) or PurePosixPath(relative).suffix.lower() not in {'.md', '.markdown'}:
        raise ValueError('Markdown資料のパスを確認してください')
    encoded = quote(relative, safe='/')
    return ('https://github.com' + prefix + encoded,
            'https://raw.githubusercontent.com/Yuji5124/idea-vault/main/ideas/' + encoded,
            PurePosixPath(relative).name)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch_github(url):
    source, raw_url, name = github_location(url)
    try:
        # Never forward the vault JWT or platform credentials to GitHub.
        with build_opener(NoRedirect()).open(Request(raw_url, headers={'Accept': 'text/plain'}), timeout=20) as response:
            raw = response.read(MAX_DOCUMENT_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError):
        raise ValueError('GitHub資料を取得できません。公開範囲とリンクを確認してください。非公開の場合はMarkdownをダウンロードしてドロップしてください') from None
    metadata = markdown_metadata(name, raw)
    item = {'name': name, 'relativePath': name, 'data': base64.b64encode(raw).decode('ascii')}
    return source, metadata, item
