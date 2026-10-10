import base64
import copy
import hashlib
import json
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
from test_cloud import start_fixture
from test_github_images import PNG

EXT = 'chrome-extension://' + 'a'*32

class StarSaveTests(unittest.TestCase):
    def setUp(self):
        self.provider,self.app,self.threads=start_fixture()
        self.app.extension_ids=('a'*32,)
        self.base=f'http://127.0.0.1:{self.app.server_port}'
        self.payload={'title':'原文のアイデア','body':'# 原文\n\n**そのまま**\n\n- 日本語\n- line\n\n```js\nconst a = 1;\n```','source_url':'https://chatgpt.com/c/abc-123','images':[]}
    def tearDown(self):
        for s in (self.app,self.provider): s.shutdown();s.server_close()
        for t in self.threads:t.join()
    def call(self,path,payload,token='owner-token',origin=EXT):
        headers={'Content-Type':'application/json','Origin':origin}
        if token:headers['Authorization']='Bearer '+token
        with urlopen(Request(self.base+path,data=json.dumps(payload).encode(),headers=headers)) as r:
            return json.loads(r.read())
    def test_text_exact_source_inbox_and_storage_readback(self):
        result=self.call('/api/star-save',self.payload)
        self.assertTrue(result['verified'])
        record=self.provider.rows[result['id']]
        self.assertEqual(record['body'],self.payload['body'])
        self.assertEqual(record['source_url'],self.payload['source_url'])
        self.assertEqual((record['type'],record['inbox']),('IDEA',True))
        self.assertEqual(result['hashes'],[hashlib.sha256(self.payload['body'].encode()).hexdigest()])
        status=self.call('/api/star-status',{'id':result['id']})
        self.assertEqual(status['hashes'],result['hashes'])
        self.assertEqual(next(iter(self.provider.objects.values())),self.payload['body'].encode())
    def test_one_multiple_images_original_bytes_and_no_duplicate(self):
        for count in (1,3):
            payload={**self.payload,'body':str(count),'images':[{'mime':'image/png','data':base64.b64encode(PNG+bytes([n])).decode()} for n in range(count)]}
            result=self.call('/api/star-save',payload)
            self.assertEqual(result['images'],count)
            self.assertEqual(result['hashes'][1:],[hashlib.sha256(PNG+bytes([n])).hexdigest() for n in range(count)])
        self.assertEqual(len(self.provider.rows),2)
    def test_retry_after_lost_response_preserves_user_edits(self):
        result=self.call('/api/star-save',self.payload)
        self.call('/api/update',{'id':result['id'],'changes':{'title':'Edited','body':'Personal notes'}},origin=f'http://127.0.0.1:{self.app.server_port}')
        again=self.call('/api/star-save',self.payload)
        self.assertTrue(again['already_saved']);self.assertEqual(len(self.provider.rows),1)
        self.assertEqual(self.provider.rows[result['id']]['body'],'Personal notes')
    def test_unauthenticated_and_other_owner_refused(self):
        for token in (None,'invalid','other-token'):
            for path,payload in (('/api/star-save',self.payload),('/api/star-status',{'id':'b'*32})):
                with self.assertRaises(HTTPError) as e:self.call(path,payload,token)
                self.assertEqual(e.exception.code,401)
        self.assertEqual(self.provider.rows,{})
    def test_origin_exact_allowlist_and_preflight(self):
        for origin in ('https://chatgpt.com','chrome-extension://'+'b'*32,EXT+'.evil','null'):
            with self.assertRaises(HTTPError) as e:self.call('/api/star-save',self.payload,origin=origin)
            self.assertEqual(e.exception.code,403)
        request=Request(self.base+'/api/star-save',method='OPTIONS',headers={'Origin':EXT,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'authorization,content-type'})
        with urlopen(request) as r:self.assertEqual(r.status,204);self.assertEqual(r.headers['Access-Control-Allow-Origin'],EXT)
        request=Request(self.base+'/api/update',method='OPTIONS',headers={'Origin':EXT,'Access-Control-Request-Method':'POST'})
        with self.assertRaises(HTTPError):urlopen(request)
    def test_invalid_sources_and_images_leave_no_partial_record(self):
        invalid=[{**self.payload,'source_url':'https://evil.example/c/abc'}, {**self.payload,'source_url':'https://chatgpt.com/c/abc?token=secret'}, {**self.payload,'images':[{'mime':'image/png','data':base64.b64encode(b'not image').decode()}]}, {**self.payload,'images':[{}]}, {**self.payload,'images':[{'mime':'image/svg+xml','data':'YWJj'}]}, {**self.payload,'images':[{}]*9}]
        for payload in invalid:
            with self.assertRaises(HTTPError):self.call('/api/star-save',payload)
        self.assertEqual(self.provider.rows,{})
    def test_long_text_and_limits(self):
        payload={**self.payload,'body':'日本語の原文\n'*30000}
        result=self.call('/api/star-save',payload)
        self.assertEqual(self.provider.rows[result['id']]['body'],payload['body'])
        with self.assertRaises(HTTPError):self.call('/api/star-save',{**self.payload,'body':'x'*(2*1024*1024+1)})
    def test_storage_mismatch_does_not_report_success(self):
        with patch('cloud_store.CloudVault.read_file',return_value=b'corrupted'):
            with self.assertRaises(HTTPError):self.call('/api/star-save',self.payload)
        retry=self.call('/api/star-save',self.payload)
        self.assertTrue(retry['verified']);self.assertTrue(retry['already_saved']);self.assertEqual(len(self.provider.rows),1)

if __name__=='__main__':
    import threading
    provider,app,threads=start_fixture(8774)
    app.extension_ids=('a'*32,)
    print('Star-save synthetic Supabase fixture running on port 8774',flush=True)
    threading.Event().wait()
