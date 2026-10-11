"""Non-destructive revisions, retained image bytes and retryable purging."""
import base64
import binascii
import copy
import hashlib
import re
import uuid
from pathlib import Path
from urllib.parse import quote

EDITABLE = ('title','body','summary','category','status','experience','principle','appeal','development','production','variant','relations','tags','record_date','inbox','type','jima_filter','comment','missing_images','image_links')
STATUSES = ('未指定','未着手','検討中','試作中','検証中','保留','未完成','失敗','完成')


def revision(record, reason='編集'):
    from server import stamp
    previous={key:copy.deepcopy(record.get(key)) for key in EDITABLE if key in record}
    previous.update({'files':copy.deepcopy(record.get('files',[])), 'at':record.get('updated_at'), 'reason':reason})
    record.setdefault('history',[]).append(previous)
    record['updated_at']=stamp()


def validate_changes(changes):
    for key in ('summary','experience','principle','appeal','development','production','variant'):
        if key in changes and (not isinstance(changes[key],str) or len(changes[key].encode())>2*1024*1024):
            raise ValueError('説明の形式・サイズを確認してください。')
    if 'status' in changes and changes['status'] not in STATUSES:
        raise ValueError('状態の指定が不正です。')
    if 'variant' in changes and changes['variant'] not in ('','原案','改善案','派生案','別作品'):
        raise ValueError('案の区分が不正です。')


def read_bytes(vault,record,file):
    if hasattr(vault,'read_file'): return vault.read_file(record,file)
    return (vault.root/record['folder']/file['path']).read_bytes()


def retained_files(record):
    found={}
    for file in record.get('files',[])+record.get('archived_files',[])+[f for h in record.get('history',[]) for f in h.get('files',[])]:
        found[file['id']]=file
        if file.get('thumbnail'):found[file['thumbnail']['id']]=file['thumbnail']
    return list(found.values())


def image_data(item, thumbnail=False):
    try: raw=base64.b64decode(item['data'],validate=True)
    except (TypeError,KeyError,ValueError,binascii.Error): raise ValueError('画像データが不正です。') from None
    name=item.get('name','thumbnail.webp' if thumbnail else '')
    extension=Path(name).suffix.lower()
    mime={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp'}.get(extension)
    valid=raw.startswith(b'\x89PNG\r\n\x1a\n') if mime=='image/png' else raw.startswith(b'\xff\xd8\xff') if mime=='image/jpeg' else raw.startswith(b'RIFF') and raw[8:12]==b'WEBP' if mime=='image/webp' else False
    if not valid or not raw or len(raw)>(256*1024 if thumbnail else 20*1024*1024):raise ValueError('PNG・JPEG・WebP画像の形式・サイズを確認してください。')
    return raw,mime,extension


def thumbnail_descriptor(item):
    from server import stamp
    raw,mime,extension=image_data(item,True);identifier=uuid.uuid4().hex
    return {'id':identifier,'name':'thumbnail'+extension,'original_name':'thumbnail'+extension,'path':'images/'+identifier+extension,'storage_path':'images/'+identifier+extension,'mime':mime,'size':len(raw),'created_at':stamp(),'text':''},raw


def upload_file(vault,record,item):
    from server import dated,stamp
    raw,mime,extension=image_data(item)
    identifier=uuid.uuid4().hex
    name=dated(Path(item['name']).name,record.get('record_date',record['imported_at'][:10]))
    file={'id':identifier,'name':name,'original_name':Path(item['name']).name,'original_path':item.get('relativePath',item['name']), 'path':'images/'+identifier+'_'+name,'storage_path':'images/'+identifier+extension,'mime':mime,'size':len(raw),'created_at':stamp(),'text':'','sha256':hashlib.sha256(raw).hexdigest()}
    def store(f,data):
        if hasattr(vault,'upload'):vault.upload(record,f,data)
        else:
            dest=vault.root/record['folder']/f['path'];dest.parent.mkdir(exist_ok=True);dest.write_bytes(data)
    store(file,raw)
    if item.get('thumbnail'):
        thumb_raw,thumb_mime,thumb_ext=image_data(item['thumbnail'],True)
        thumb_id=uuid.uuid4().hex
        thumb={'id':thumb_id,'name':'thumbnail'+thumb_ext,'original_name':'thumbnail'+thumb_ext,'path':'images/'+thumb_id+thumb_ext,'storage_path':'images/'+thumb_id+thumb_ext,'mime':thumb_mime,'size':len(thumb_raw),'created_at':stamp(),'text':''}
        store(thumb,thumb_raw);file['thumbnail']=thumb
    return file


def manage(vault,payload):
    from server import stamp
    record=vault.get(payload['id']);action=payload.get('action')
    if action=='trash':
        if record.get('purging'):raise ValueError('完全削除処理中です。')
        if not record.get('deleted_at'):record['deleted_at']=stamp();record['updated_at']=stamp();vault.save(record)
    elif action=='restore':
        if record.get('purging'):raise ValueError('完全削除処理中の記録は復元できません。完全削除を再試行してください。')
        record.pop('deleted_at',None);record['updated_at']=stamp();vault.save(record)
    elif action=='purge':
        if not record.get('deleted_at') or payload.get('confirmation')!=record['title']:raise ValueError('ゴミ箱の記録名を入力して確認してください。')
        all_records=vault.records()
        if any(record['id'] in r.get('relations',[]) for r in all_records if r['id']!=record['id']):raise ValueError('他のアイデアの関連先です。関連を解除してから完全削除してください。')
        record['purging']=True;vault.save(record)
        others={vault.object_path(r,f) if hasattr(vault,'object_path') else str(vault.root/r['folder']/f['path']) for r in all_records if r['id']!=record['id'] for f in retained_files(r)}
        deletable=[f for f in retained_files(record) if (vault.object_path(record,f) if hasattr(vault,'object_path') else str(vault.root/record['folder']/f['path'])) not in others]
        if hasattr(vault,'remove'):
            vault.remove(record,deletable)
            vault.call('/rest/v1/vault_records?id=eq.'+quote(record['id'],safe='')+'&owner_id=eq.'+quote(vault.owner,safe=''),'DELETE')
            if any(r['id']==record['id'] for r in vault.records()):raise ValueError('完全削除の確定を確認できません。再試行してください。')
        else:
            import shutil
            if len(deletable)!=len(retained_files(record)):raise ValueError('共有ファイルがあるため削除できません。')
            shutil.rmtree(vault.root/record['folder'])
        return {'purged':True}
    elif action=='resolve_images':
        associations=payload.get('associations')
        if record.get('deleted_at') or payload.get('confirmed') is not True or not isinstance(associations,list) or not associations:
            raise ValueError('画像との照合を確認してください。')
        image_ids={f['id'] for f in record['files'] if f['mime'].startswith('image/')}
        if any(not isinstance(a,dict) or a.get('ref') not in record.get('missing_images',[]) or a.get('file_id') not in image_ids for a in associations):
            raise ValueError('未取得参照と本人の添付画像を指定してください。')
        revision(record,'未取得画像の照合')
        for item in associations: record.setdefault('image_links',{})[item['ref']]=item['file_id']
        record['missing_images']=[ref for ref in record.get('missing_images',[]) if ref not in record.get('image_links',{})]
        vault.save(record)
    elif action=='files':
        if record.get('deleted_at'):raise ValueError('ゴミ箱の記録は先に復元してください。')
        add=payload.get('add',[]);remove=payload.get('remove',[]);order=payload.get('order')
        if not isinstance(add,list) or len(add)>8 or not isinstance(remove,list):raise ValueError('画像の指定が不正です。')
        total=0
        for item in add:
            raw,_,_=image_data(item);total+=len(raw)
            if item.get('thumbnail'):image_data(item['thumbnail'],True)
        if total>30*1024*1024:raise ValueError('画像合計は30MBまでです。')
        ids={f['id'] for f in record['files']}
        if not all(i in ids for i in remove):raise ValueError('添付の指定が不正です。')
        remaining=[f for f in record['files'] if f['id'] not in remove]
        if order is not None and (not isinstance(order,list) or len(order)!=len(remaining) or set(order)!={f['id'] for f in remaining}):raise ValueError('画像の順序が不正です。')
        existing={hashlib.sha256(read_bytes(vault,record,f)).hexdigest() for f in remaining if f['mime'].startswith('image/')}
        revision(record,'画像の変更')
        record.setdefault('archived_files',[]).extend(f for f in record['files'] if f['id'] in remove)
        record['files']=remaining if order is None else [next(f for f in remaining if f['id']==i) for i in order]
        added=duplicates=0
        for item in add:
            raw,_,_=image_data(item);sha=hashlib.sha256(raw).hexdigest()
            if sha in existing:duplicates+=1;continue
            record['files'].append(upload_file(vault,record,item));existing.add(sha);added+=1
        vault.save(record)
        return {'record':record,'added':added,'duplicates':duplicates}
    else:raise ValueError('操作を確認してください。')
    return {'record':record}
