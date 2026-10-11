import base64
import io
import json
import struct
import threading
import unittest
import zipfile
import zlib
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from test_cloud import start_fixture
from cloud_store import CloudError
from history_import import parse,day


def png():
    def chunk(tag,raw):return struct.pack('!I',len(raw))+tag+raw+struct.pack('!I',zlib.crc32(tag+raw)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xff\x00\x00'))+chunk(b'IEND',b'')
PNG=png()


def uploaded(name,raw):return {'name':name,'data':base64.b64encode(raw).decode()}

def zipped(entries):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for name,raw in entries.items():z.writestr(name,raw)
    return uploaded('export.zip',out.getvalue())


def export_data(body='完成前の案',image=True):
    parts=[body]+([{'asset_pointer':'file-service://file-image'}] if image else [])
    return [{'id':'history-test','title':'途中のゲーム案','mapping':{'one':{'message':{'id':'one','create_time':1789095600,'author':{'role':'assistant'},'content':{'parts':parts}}}}}]


class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.provider,self.app,self.threads=start_fixture()
        self.base=f'http://127.0.0.1:{self.app.server_port}'
    def tearDown(self):
        for s in (self.app,self.provider):s.shutdown();s.server_close()
        for t in self.threads:t.join()
    def call(self,path,payload=None,token='owner-token'):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        with urlopen(Request(self.base+path,data=json.dumps(payload).encode() if payload is not None else None,headers=headers)) as response:
            raw=response.read();return raw if response.headers['Content-Type'].startswith('application/zip') else json.loads(raw)
    def create(self):return self.call('/api/create',{'title':'原案','body':'失敗も残す'})
    def test_text_only_import_skips_present_images_and_is_idempotent(self):
        payload={'text_only':True,'from':'2026-09-11','to':'2026-10-11','files':[zipped({'conversations.json':json.dumps(export_data()).encode(),'file-image.png':PNG,'unrelated.png':PNG})]}
        candidate=self.call('/api/history-preview',payload)['candidates'][0]
        self.assertEqual(len(self.call('/api/history-preview',payload)['candidates']),1)
        self.assertEqual(candidate['files'],[])
        self.assertTrue(candidate['missing_images'])
        request={**payload,'confirmed':True,'selections':[{'key':candidate['key'],'action':'new'}]}
        result=self.call('/api/history-commit',request)
        self.assertEqual(result['new'],1);self.assertEqual(result['images'],0)
        record=next(iter(self.provider.rows.values()))
        self.assertIn('完成前の案',record['body']);self.assertEqual(record['files'],[])
        self.assertEqual(self.call('/api/history-commit',request)['duplicates'],1)

    def test_edit_history_retains_before_and_optimistic_conflict(self):
        r=self.create();updated=self.call('/api/update',{'id':r['id'],'expected_updated_at':r['updated_at'],'changes':{'body':'改善案','summary':'ひとこと','status':'失敗','principle':'原理','variant':'改善案'}})
        self.assertEqual(updated['history'][0]['body'],'失敗も残す');self.assertEqual(updated['status'],'失敗')
        with self.assertRaises(HTTPError):self.call('/api/update',{'id':r['id'],'expected_updated_at':r['updated_at'],'changes':{'body':'古い画面'}})
        self.assertEqual(self.provider.rows[r['id']]['body'],'改善案')
    def test_trash_restore_and_no_unconfirmed_permanent_delete(self):
        r=self.create();self.call('/api/manage',{'id':r['id'],'action':'trash'})
        self.assertIn('deleted_at',self.provider.rows[r['id']])
        with self.assertRaises(HTTPError):self.call('/api/update',{'id':r['id'],'changes':{'body':'不可'}})
        with self.assertRaises(HTTPError):self.call('/api/manage',{'id':r['id'],'action':'purge','confirmation':'wrong'})
        self.call('/api/manage',{'id':r['id'],'action':'restore'});self.assertNotIn('deleted_at',self.provider.rows[r['id']]);self.assertEqual(self.provider.rows[r['id']]['body'],'失敗も残す')
    def test_add_duplicate_remove_reorder_backup_and_purge(self):
        r=self.create();r2=self.create();item=uploaded('2026-10-10_原画.png',PNG)
        first=self.call('/api/manage',{'id':r['id'],'action':'files','add':[item]});f=first['record']['files'][0]
        self.assertEqual(self.call('/api/manage',{'id':r['id'],'action':'files','add':[item]})['duplicates'],1)
        self.call('/api/manage',{'id':r2['id'],'action':'files','add':[item]})
        self.call('/api/manage',{'id':r['id'],'action':'files','order':[f['id']]})
        self.call('/api/manage',{'id':r['id'],'action':'files','remove':[f['id']]})
        self.assertEqual(self.provider.rows[r['id']]['files'],[]);self.assertEqual(len(self.provider.objects),2)
        backup=self.call('/api/backup',{})
        with zipfile.ZipFile(io.BytesIO(backup)) as z:self.assertIn(PNG,[z.read(n) for n in z.namelist()])
        self.call('/api/manage',{'id':r['id'],'action':'trash'});self.call('/api/manage',{'id':r['id'],'action':'purge','confirmation':'原案'})
        self.assertNotIn(r['id'],self.provider.rows);self.assertEqual(len(self.provider.objects),1);self.assertIn(r2['id'],self.provider.rows)
    def test_failed_image_upload_keeps_metadata_and_retryable_purge(self):
        r=self.create()
        with patch('cloud_store.CloudVault.upload',side_effect=CloudError('mock failure')):
            with self.assertRaises(HTTPError):self.call('/api/manage',{'id':r['id'],'action':'files','add':[uploaded('image.png',PNG)]})
        self.assertEqual(self.provider.rows[r['id']]['files'],[])
        self.call('/api/manage',{'id':r['id'],'action':'trash'})
        with patch('cloud_store.CloudVault.remove',side_effect=CloudError('mock failure')):
            with self.assertRaises(HTTPError):self.call('/api/manage',{'id':r['id'],'action':'purge','confirmation':'原案'})
        self.assertTrue(self.provider.rows[r['id']]['purging'])
        with self.assertRaises(HTTPError):self.call('/api/manage',{'id':r['id'],'action':'restore'})
        self.call('/api/manage',{'id':r['id'],'action':'purge','confirmation':'原案'});self.assertNotIn(r['id'],self.provider.rows)
    def test_purge_rejects_incoming_relation(self):
        r=self.create();other=self.create();self.call('/api/update',{'id':other['id'],'changes':{'relations':[r['id']]}})
        self.call('/api/manage',{'id':r['id'],'action':'trash'})
        with self.assertRaises(HTTPError):self.call('/api/manage',{'id':r['id'],'action':'purge','confirmation':'原案'})
        self.assertIn(r['id'],self.provider.rows)
    def test_owner_required_for_all_new_apis(self):
        r=self.create()
        for token in (None,'other-token','bad'):
            for path,payload in (('/api/manage',{'id':r['id'],'action':'trash'}),('/api/history-preview',{'files':[]}),('/api/history-commit',{'confirmed':True}),('/api/backup',{})):
                with self.assertRaises(HTTPError) as e:self.call(path,payload,token)
                self.assertEqual(e.exception.code,401)
        self.assertNotIn('deleted_at',self.provider.rows[r['id']])
    def test_zip_preview_commit_duplicate_and_explicit_update_history(self):
        payload={'files':[zipped({'conversations.json':json.dumps(export_data()).encode(),'file-image.png':PNG})],'from':'2026-09-11','to':'2026-10-11'}
        preview=self.call('/api/history-preview',payload);self.assertEqual(len(preview['candidates']),1);self.assertEqual(self.provider.rows,{})
        c=preview['candidates'][0];self.assertEqual(len(c['files']),1);self.assertEqual(c['missing_images'],[])
        chosen={**payload,'confirmed':True,'selections':[{'key':c['key'],'action':'new'}]}
        result=self.call('/api/history-commit',chosen);self.assertEqual((result['new'],result['images']),(1,1))
        self.assertEqual(self.call('/api/history-commit',chosen)['duplicates'],1)
        payload['files']=[zipped({'conversations.json':json.dumps(export_data('改善した未完成案')).encode(),'file-image.png':PNG})]
        c=self.call('/api/history-preview',payload)['candidates'][0];self.assertEqual(c['suggestion'],'update')
        result=self.call('/api/history-commit',{**payload,'confirmed':True,'selections':[{'key':c['key'],'action':'update','expected_updated_at':c['expected_updated_at']}]})
        self.assertEqual(result['updated'],1);record=next(iter(self.provider.rows.values()));self.assertIn('完成前の案',record['history'][0]['body']);self.assertIn('改善した未完成案',record['body']);self.assertEqual(len(record['files']),1)
    def test_missing_images_saved_as_missing_and_no_confirmation_no_commit(self):
        payload={'files':[uploaded('conversations.json',json.dumps(export_data()).encode())]}
        c=self.call('/api/history-preview',payload)['candidates'][0];self.assertEqual(len(c['missing_images']),1)
        with self.assertRaises(HTTPError):self.call('/api/history-commit',{**payload,'selections':[{'key':c['key'],'action':'new'}]})
        result=self.call('/api/history-commit',{**payload,'confirmed':True,'selections':[{'key':c['key'],'action':'new'}]});self.assertEqual((result['new'],result['missing_images'],result['images']),(1,1,0))
    def test_later_image_association_requires_explicit_valid_file(self):
        payload={'files':[uploaded('conversations.json',json.dumps(export_data()).encode())]}
        c=self.call('/api/history-preview',payload)['candidates'][0]
        result=self.call('/api/history-commit',{**payload,'confirmed':True,'selections':[{'key':c['key'],'action':'new'}]})
        identifier=result['results'][0]['id'];ref=c['missing_images'][0]
        image=self.call('/api/manage',{'id':identifier,'action':'files','add':[uploaded('later.png',PNG)]})['record']['files'][0]
        with self.assertRaises(HTTPError):self.call('/api/manage',{'id':identifier,'action':'resolve_images','associations':[{'ref':ref,'file_id':image['id']}]})
        self.call('/api/manage',{'id':identifier,'action':'resolve_images','confirmed':True,'associations':[{'ref':ref,'file_id':image['id']}]})
        self.assertEqual(self.provider.rows[identifier]['missing_images'],[])
        self.assertEqual(self.provider.rows[identifier]['image_links'][ref],image['id'])

    def test_import_image_upload_failure_not_marked_complete(self):
        payload={'files':[zipped({'2026-10-10_案.md':b'# Title\n![image](pic.png)','pic.png':PNG})]}
        c=self.call('/api/history-preview',payload)['candidates'][0]
        request={**payload,'confirmed':True,'selections':[{'key':c['key'],'action':'new'}]}
        with patch('cloud_store.CloudVault.upload',side_effect=CloudError('mock failure')):
            result=self.call('/api/history-commit',request);self.assertEqual(result['errors'],1)
        self.assertEqual(self.provider.rows,{})
        self.assertEqual(self.call('/api/history-commit',request)['new'],1)


class LocalManagementTests(unittest.TestCase):
    def test_local_import_edit_images_trash_restore_and_purge(self):
        import tempfile
        from server import Vault
        from history_import import preview,commit
        from record_management import manage
        with tempfile.TemporaryDirectory() as directory:
            vault=Vault(directory)
            payload={'files':[uploaded('2026-10-10_local.md',b'# Local\noriginal')]}
            candidate=preview(vault,payload)['candidates'][0]
            result=commit(vault,{**payload,'confirmed':True,'selections':[{'key':candidate['key'],'action':'new'}]})
            self.assertEqual(result['new'],1);identifier=result['results'][0]['id']
            self.assertEqual(commit(vault,{**payload,'confirmed':True,'selections':[{'key':candidate['key'],'action':'new'}]})['duplicates'],1)
            record=vault.update(identifier,{'body':'updated'});self.assertIn('original',record['history'][0]['body'])
            manage(vault,{'id':identifier,'action':'files','add':[uploaded('local.png',PNG)]})
            manage(vault,{'id':identifier,'action':'trash'});manage(vault,{'id':identifier,'action':'restore'})
            self.assertEqual(len(vault.get(identifier)['files']),1)
            manage(vault,{'id':identifier,'action':'trash'});manage(vault,{'id':identifier,'action':'purge','confirmation':'Local'})
            self.assertEqual(vault.records(),[])


class ParserTests(unittest.TestCase):
    def test_jst_period_boundaries_and_all_branches_preserved(self):
        self.assertEqual(day('2026-09-10T15:00:00Z'),'2026-09-11');self.assertEqual(day('2026-10-11T14:59:59Z'),'2026-10-11');self.assertEqual(day('2026-10-11T15:00:00Z'),'2026-10-12')
        data=export_data(image=False);mapping=data[0]['mapping'];mapping['two']={'message':{'id':'two','create_time':1789100000,'author':{'role':'user'},'content':{'parts':['迷走と修正指示']}}}
        candidates=parse({'files':[zipped({'conversations.json':json.dumps(data).encode(),'user.json':b'{"account":"not an idea"}','chat.html':b'<p>same export rendering</p>'})]});self.assertIn('迷走と修正指示',candidates[0]['body'])
    def test_archive_traversal_symlink_bomb_and_duplicate_paths_refused(self):
        for archive in (zipped({'../outside.md':b'# no'}),zipped({'/outside.md':b'# no'})):
            with self.assertRaises(ValueError):parse({'files':[archive]})
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            info=zipfile.ZipInfo('link.md');info.create_system=3;info.external_attr=(0o120777<<16);z.writestr(info,b'outside')
        with self.assertRaises(ValueError):parse({'files':[uploaded('bad.zip',out.getvalue())]})
        with self.assertRaises(ValueError):parse({'files':[uploaded('same.md',b'# A'),uploaded('same.md',b'# B')]})
        with patch('history_import.MAX_TOTAL',1024):
            with self.assertRaises(ValueError):parse({'files':[zipped({'large.md':b'x'*2048})]})
    def test_supplied_structured_details_preserved_without_generation(self):
        entry={'id':'source','title':'Toy','body':'原文','created_at':'2026-10-10','summary':'実際の概要','status':'未完成','principle':'元の原理'}
        candidate=parse({'files':[uploaded('ideas.json',json.dumps([entry]).encode())]})[0]
        self.assertEqual(candidate['details'],{'summary':'実際の概要','status':'未完成','principle':'元の原理'})
        self.assertNotIn('appeal',candidate['details'])
        unknown=export_data(image=False);unknown[0].pop('id');unknown[0]['mapping']['one']['message']['content']['parts'].append({'content_type':'image_asset_pointer'})
        uncertain=parse({'files':[uploaded('conversations.json',json.dumps(unknown).encode())]})[0]
        self.assertTrue(uncertain['key'].startswith('uncertain:'));self.assertEqual(len(uncertain['missing_images']),1)
        from history_import import preview
        stored={'id':'existing','body':uncertain['body'],'import_key':uncertain['key'],'import_hash':uncertain['hash'],'updated_at':'test-time'}
        mock=type('Records',(),{'records':lambda self:[stored]})()
        repeated=preview(mock,{'files':[uploaded('conversations.json',json.dumps(unknown).encode())]})
        self.assertEqual(repeated['candidates'][0]['suggestion'],'duplicate')

    def test_undated_html_external_images_and_unmatched_image_not_invented(self):
        candidates=parse({'files':[uploaded('idea.html',b'<h1>Idea</h1><script>evil()</script><p>unfinished</p><img src="https://evil.example/image.png">'),uploaded('unmatched.png',PNG)]})
        self.assertEqual(len(candidates),2);self.assertTrue(candidates[0]['undated']);self.assertNotIn('evil()',candidates[0]['body']);self.assertEqual(len(candidates[0]['missing_images']),1);self.assertEqual(len(candidates[1]['files']),1)

if __name__=='__main__':
    provider,app,threads=start_fixture(8777)
    from pathlib import Path
    Path('/tmp/idea-vault-import-test.zip').write_bytes(base64.b64decode(zipped({'2026-10-10_未完成ゲーム.md':'# 未完成ゲーム\n保存日：2026年10月10日\n\n未完成も保管する。\n![原画](原画.png)'.encode(),'原画.png':PNG})['data']))
    Path('/tmp/idea-vault-original-test.png').write_bytes(PNG)
    print('History management synthetic Supabase fixture on port 8777',flush=True)
    threading.Event().wait()
