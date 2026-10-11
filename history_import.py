"""Memory-only, non-AI export parsing; preview and explicit source-identity updates."""
import base64
import binascii
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime,timezone,timedelta
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import unquote,urlsplit
from record_management import image_data, upload_file, read_bytes, revision, validate_changes

JST=timezone(timedelta(hours=9))
MAX_TOTAL=50*1024*1024


def sha(raw):return hashlib.sha256(raw).hexdigest()

def day(value):
    if value is None:return None
    try:
        if isinstance(value,str) and re.fullmatch(r'\d{4}-\d{1,2}-\d{1,2}',value):
            y,m,d=map(int,value.split('-'));return datetime(y,m,d,tzinfo=JST).date().isoformat()
        if isinstance(value,(int,float)):return datetime.fromtimestamp(value,JST).date().isoformat()
        return datetime.fromisoformat(str(value).replace('Z','+00:00')).replace(tzinfo=JST).date().isoformat() if not re.search(r'(Z|[+-]\d\d:\d\d)$',str(value)) else datetime.fromisoformat(str(value).replace('Z','+00:00')).astimezone(JST).date().isoformat()
    except (ValueError,TypeError,OverflowError,OSError):return None


def safe_name(name):
    if not isinstance(name,str) or '\\' in name or '\x00' in name:raise ValueError('ファイル名が不正です。')
    path=PurePosixPath(name)
    if path.is_absolute() or any(p in ('..','.') for p in name.split('/')) or not name or ':' in name:raise ValueError('ZIP内のパスが不正です。')
    return str(path)


def unpack(payload):
    entries=payload.get('files')
    if not isinstance(entries,list) or not 1<=len(entries)<=1000:raise ValueError('ファイルを選択してください（最大1000件）。')
    result={};total=0
    def add(name,raw):
        nonlocal total
        name=safe_name(name)
        if name in result:raise ValueError('同じパスのファイルが複数あります。')
        total+=len(raw)
        if total>MAX_TOTAL or len(result)>=1000:raise ValueError('展開後50MB・1000ファイル以内で分割してください。')
        result[name]=raw
    for item in entries:
        try:
            encoded=item['data']
            if not isinstance(encoded,str) or len(encoded)>45*1024*1024:raise ValueError()
            raw=base64.b64decode(encoded,validate=True);name=safe_name(item['name'])
        except (KeyError,TypeError,ValueError,binascii.Error):raise ValueError('投入ファイルの形式・サイズを確認してください。') from None
        if name.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    infos=archive.infolist()
                    if len(infos)>1000:raise ValueError('ZIPは1000エントリ以内で分割してください。')
                    if sum(i.file_size for i in infos)>MAX_TOTAL:raise ValueError('ZIPの展開後サイズは50MBまでです。')
                    for info in infos:
                        safe_name(info.filename.rstrip('/'))
                        if ((info.external_attr>>16)&0o170000)==0o120000 or info.flag_bits&1:raise ValueError('リンク・暗号化ZIPには対応していません。')
                        if not info.is_dir() and not info.filename.startswith('__MACOSX/'):
                            add(info.filename,archive.read(info))
            except (zipfile.BadZipFile,RuntimeError,NotImplementedError):raise ValueError('ZIPを展開できません。') from None
        else:add(name,raw)
    return result


class TextHTML(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.images=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
        elif not self.skip:
            if tag in ('p','div','h1','h2','h3','li','br','tr'):self.parts.append('\n')
            if tag=='img':self.images.append(dict(attrs).get('src',''))
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.skip:self.skip-=1
        elif tag in ('p','div','li','tr'):self.parts.append('\n')
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)


def parse(payload):
    from document_import import record_date,markdown_metadata
    begin=record_date(payload.get('from','2026-09-11'));end=record_date(payload.get('to','2026-10-11'))
    if begin>end:raise ValueError('期間の開始と終了を確認してください。')
    assets=unpack(payload);candidates=[];used=set();has_conversations=any(PurePosixPath(n).name=='conversations.json' for n in assets)
    def candidate(key,title,body,date,refs=(),source=None,origin=None,details=None):
        if date and not begin<=date<=end:return
        if len(candidates)>=500:raise ValueError('候補が500件を超えています。ファイルを分割してください。')
        if not isinstance(title,str) or len(title)>200 or not isinstance(body,str) or len(body.encode())>2*1024*1024:raise ValueError('候補のタイトル・本文を確認してください（本文2MBまで）。')
        if source is not None and (not isinstance(source,str) or len(source)>4096):raise ValueError('出典URLの形式を確認してください。')
        if not isinstance(refs,(list,tuple)) or any(ref is not None and not isinstance(ref,str) for ref in refs):raise ValueError('画像参照は文字列の配列にしてください。')
        details=details or {}
        if any(not isinstance(v,str) for v in details.values()):raise ValueError('説明項目は文字列にしてください。')
        validate_changes(details)
        files=[];missing=[]
        for ref in dict.fromkeys(refs):
            if not isinstance(ref,str) or not ref:continue
            pointer=ref.removeprefix('file-service://').removeprefix('sediment://')
            local=unquote(pointer)
            matches=[]
            if not urlsplit(local).scheme and not local.startswith('/') and '..' not in local.split('/'):
                relative=str(PurePosixPath(origin or '').parent/local)
                matches=[n for n in assets if n in (local,relative) or PurePosixPath(n).name==local]
                if not matches and re.fullmatch(r'file[-_][a-zA-Z0-9-]+',local):matches=[n for n in assets if PurePosixPath(n).stem==local or PurePosixPath(n).name.startswith(local+'-')]
            if len(matches)!=1:missing.append(ref);continue
            name=matches[0]
            used.add(name)
            if payload.get('text_only') is True:
                missing.append(ref)
                continue
            item={'name':PurePosixPath(name).name,'relativePath':name,'data':base64.b64encode(assets[name]).decode()}
            image_data(item)
            thumb=payload.get('thumbnails',{}).get(sha(assets[name]))
            if thumb: image_data(thumb,True);item['thumbnail']=thumb
            files.append(item);used.add(name)
        if sum(len(base64.b64decode(f['data'])) for f in files)>30*1024*1024:raise ValueError('1候補の画像合計は30MBまでです。')
        fingerprint=sha(json.dumps({'body':body,'title':title,'details':details,'images':[sha(base64.b64decode(f['data'])) for f in files],'missing':missing},ensure_ascii=False,sort_keys=True).encode())
        candidates.append({'key':key,'title':title or '無題','body':body,'record_date':date,'files':files,'missing_images':missing,'source_url':source,'origin':origin,'hash':fingerprint,'undated':not bool(date),'details':details})
        return candidates[-1]
    for name,raw in assets.items():
        suffix=PurePosixPath(name).suffix.lower()
        if suffix in ('.png','.jpg','.jpeg','.webp'):continue
        if suffix not in ('.json','.md','.markdown','.txt','.html','.htm'):continue
        if has_conversations and suffix=='.json' and PurePosixPath(name).name!='conversations.json':continue
        if has_conversations and PurePosixPath(name).name=='chat.html':continue # same official export rendering
        try:text=raw.decode('utf-8-sig')
        except UnicodeError:raise ValueError('UTF-8テキストを指定してください。') from None
        if suffix=='.json':
            try:data=json.loads(text)
            except ValueError:raise ValueError('JSONを解析できません。') from None
            if not isinstance(data,list):raise ValueError('JSONは公式conversations.jsonまたは候補配列形式にしてください。')
            for index,conversation in enumerate(data):
                if not isinstance(conversation,dict):raise ValueError('会話の形式が不正です。')
                if isinstance(conversation.get('mapping'),dict):
                    messages=[n.get('message') for n in conversation['mapping'].values() if isinstance(n,dict) and isinstance(n.get('message'),dict)]
                    messages.sort(key=lambda m:(m.get('create_time') or 0,str(m.get('id',''))))
                    paragraphs=[];refs=[];dates=[]
                    for message in messages:
                        role=message.get('author',{}).get('role')
                        if role not in ('user','assistant','tool'):continue
                        date=day(message.get('create_time'))
                        if date and not begin<=date<=end:continue
                        if date:dates.append(date)
                        parts=message.get('content',{}).get('parts',[]);texts=[]
                        for part_index,part in enumerate(parts):
                            if isinstance(part,str):texts.append(part)
                            elif isinstance(part,dict):
                                if isinstance(part.get('text'),str):texts.append(part['text'])
                                if part.get('asset_pointer'):refs.append(part['asset_pointer'])
                                elif str(part.get('content_type','')).startswith('image'):
                                    refs.append('画像参照不明:'+str(message.get('id','unknown'))+':'+str(part_index))
                        for attachment_index,attachment in enumerate(message.get('metadata',{}).get('attachments',[])):
                            if isinstance(attachment,dict) and str(attachment.get('mime_type','')).startswith('image/'):
                                refs.append(attachment.get('id') or attachment.get('name') or '画像参照不明:'+str(message.get('id','unknown'))+':attachment'+str(attachment_index))
                        if texts:paragraphs.append('## '+role+('｜'+date if date else '｜日時不明')+'\n\n'+'\n'.join(texts))
                    if not paragraphs and not refs:continue
                    identifier=conversation.get('id') or conversation.get('conversation_id')
                    key='chatgpt:'+identifier if isinstance(identifier,str) and re.fullmatch(r'[A-Za-z0-9-]+',identifier) else 'uncertain:json:'+name+':'+sha(json.dumps(conversation,sort_keys=True,ensure_ascii=False).encode())
                    created=candidate(key,conversation.get('title') or 'ChatGPT会話','\n\n'.join(paragraphs),min(dates) if dates else None,refs,'https://chatgpt.com/c/'+str(identifier) if identifier and re.fullmatch(r'[A-Za-z0-9-]+',str(identifier)) else None,name)
                    if created:
                        for source,target in (('create_time','source_created_at'),('update_time','source_updated_at')):
                            value=conversation.get(source)
                            if isinstance(value,(float,int)):
                                try:created[target]=datetime.fromtimestamp(value,JST).isoformat()
                                except (ValueError,OverflowError,OSError):pass
                else:
                    candidate(('json:'+name+':'+conversation['id']) if isinstance(conversation.get('id'),str) and conversation['id'] else 'uncertain:json:'+name+':'+sha(json.dumps(conversation,sort_keys=True,ensure_ascii=False).encode()),conversation.get('title') or '無題',conversation.get('body',''),day(conversation.get('created_at') or conversation.get('date')),conversation.get('images',[]),conversation.get('source_url'),name,{key:conversation[key] for key in ('category','summary','status','experience','principle','appeal','development','production','variant') if key in conversation})
        elif suffix in ('.md','.markdown'):
            metadata=markdown_metadata(PurePosixPath(name).name,raw)
            explicit=bool(re.search(r'\d{4}[-年]\d{1,2}[-月]\d{1,2}',name+'\n'+'\n'.join(text.splitlines()[:20])))
            candidate('file:'+name,metadata['title'],text,metadata['record_date'] if explicit else None,re.findall(r'!\[[^\]]*\]\(([^)]+)\)',text),None,name)
        else:
            refs=[]
            if suffix in ('.html','.htm'):
                parser=TextHTML();parser.feed(text);text=''.join(parser.parts).strip();refs=parser.images
            match=re.search(r'(\d{4})[-年](\d{1,2})[-月](\d{1,2})',name)
            date=day('-'.join(match.groups())) if match else None
            candidate('file:'+name,PurePosixPath(name).stem,text,date,refs,None,name)
    for name,raw in assets.items():
        if payload.get('text_only') is True:continue
        if name in used or PurePosixPath(name).suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):continue
        match=re.search(r'(\d{4})[-年](\d{1,2})[-月](\d{1,2})',name)
        date=day('-'.join(match.groups())) if match else None
        candidate('image:'+name,PurePosixPath(name).stem,'',date,[name],None,name)
    return candidates


def preview(vault,payload):
    candidates=parse(payload);records=vault.records()
    for c in candidates:
        matches=[r for r in records if r.get('import_key')==c['key']]
        old=matches[0] if len(matches)==1 else None
        c['target_id']=old['id'] if old else None
        c['expected_updated_at']=old.get('updated_at') if old else None
        c['before']=old.get('body','') if old else ''
        c['suggestion']='duplicate' if old and old.get('import_hash')==c['hash'] else 'update' if old else 'new'
        if ((c['undated'] or c['key'].startswith('uncertain:')) and c['suggestion']!='duplicate') or len(matches)>1 or old and old.get('deleted_at'):c['suggestion']='hold'
    return {'candidates':candidates,'notice':'会話単位の候補です。途中の発想・修正指示・分岐も残します。意味による選別や統合はしません。'}


def commit(vault,payload):
    if payload.get('confirmed') is not True:raise ValueError('プレビューを確認してから確定してください。')
    selections=payload.get('selections')
    if not isinstance(selections,list) or not 1<=len(selections)<=5:raise ValueError('1回の確定は5件までです。')
    candidates={c['key']:c for c in preview(vault,payload)['candidates']}
    counts={'new':0,'updated':0,'duplicates':0,'missing_images':0,'images':0,'held':0,'errors':0};results=[]
    for selected in selections:
        try:
            c=candidates[selected['key']];action=selected['action']
            if action=='hold':counts['held']+=1;continue
            if c['suggestion']=='duplicate':counts['duplicates']+=1;continue
            old=vault.get(c['target_id']) if c['target_id'] else None
            if old and old.get('deleted_at'):raise ValueError('ゴミ箱の資料は先に復元してください。')
            if action=='update' and old:
                if selected.get('expected_updated_at')!=old['updated_at']:raise ValueError('プレビュー後に編集されました。再確認してください。')
                record=old
                revision(record,'履歴インポート更新')
                existing={sha(read_bytes(vault,record,f)) for f in record['files'] if f['mime'].startswith('image/')}
                added=0
                for item in c['files']:
                    raw=base64.b64decode(item['data']);fingerprint=sha(raw)
                    if fingerprint in existing:continue
                    record['files'].append(upload_file(vault,record,item));existing.add(fingerprint);added+=1
                record['body']=c['body'];record['import_hash']=c['hash'];record['missing_images']=[ref for ref in c['missing_images'] if ref not in record.get('image_links',{})];record['source_updated_at']=c.get('source_updated_at');vault.save(record)
                counts['updated']+=1;counts['images']+=added
            elif action=='new' and not old:
                identifier=sha(c['key'].encode())[:32]
                if any(r['id']==identifier for r in vault.records()):raise ValueError('取り込み済みの資料です。再確認してください。')
                record=vault.create(c['title'],files=c['files'],body=c['body'],record_date=c['record_date'] or datetime.now(JST).date().isoformat(),source_url=c['source_url'],identifier=identifier,extra_metadata={**c['details'],'import_key':c['key'],'import_hash':c['hash'],'missing_images':c['missing_images'],'import_origin':c['origin'],'source_date_unknown':c['undated'],'source_created_at':c.get('source_created_at'),'source_updated_at':c.get('source_updated_at')})
                counts['new']+=1;counts['images']+=len(c['files'])
            else:raise ValueError('新規・更新・保留の指定を再確認してください。')
            counts['missing_images']+=len(c['missing_images'])
            results.append({'id':record['id'],'status':'saved'})
        except (KeyError,TypeError,ValueError,OSError) as error:
            counts['errors']+=1;results.append({'status':'error','error':str(error) if isinstance(error,ValueError) else '取り込めません。保存先とデータを確認してください。'})
    return {**counts,'results':results}
