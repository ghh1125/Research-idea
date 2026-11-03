"""HTTP and process-boundary tests; synthetic workers never call a model."""
import http.client
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from research_idea.config import load_config
from research_idea.locking import project_lock
from research_idea.store import Store
from research_idea.web import make_server


WORKER = r'''
import json, sys, time
from pathlib import Path
from research_idea.conversation import append_message
from research_idea.locking import project_lock
from research_idea.store import Store
request = json.load(sys.stdin)
with project_lock(Path(request['project'])):
    store = Store(Path(request['project']))
    mode = request['mode']
    if mode == 'chat':
        append_message(store, 'user', request['message'])
        print(json.dumps({'tag':'thinking','text':'fixture ready'}), flush=True)
        if request['message'] == 'slow':
            store.begin_task('fixture', 'chat')
            time.sleep(30)
        append_message(store, 'assistant', 'synthetic test response')
        print(json.dumps({'tag':'assistant','text':'synthetic test response'}), flush=True)
    elif mode == 'run':
        store.set_many({'status':'awaiting_direction_discussion', 'question_cycle':{'stage':'direction'},
                        'problem_checkpoint':{'kind':'direction','state':'discussing'}})
        print(json.dumps({'tag':'direction','text':'synthetic directions'}), flush=True)
    else:
        store.set_many({'status':'completed', 'problem_checkpoint':{'kind':'problem','state':'confirmed'}})
        print(json.dumps({'tag':'idea','text':'synthetic conclusion'}), flush=True)
    store.close()
'''


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.worker = self.root / 'worker.py'
        self.worker.write_text(WORKER, encoding='utf-8')
        self.start_server()

    def start_server(self):
        self.server = make_server(0, projects=self.root / 'projects', output=self.root / 'results')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.token = self.request('GET', '/api/session')[1]['token']

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        merged = {'Content-Type':'application/json', 'X-Research-Token':getattr(self, 'token', '')}
        merged.update(headers or {})
        try:
            connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=merged)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def create(self, **kwargs):
        status, project = self.request('POST', '/api/projects', kwargs)
        self.assertEqual(status, 201, project)
        return project

    def get(self, ident):
        status, data = self.request('GET', '/api/projects/' + ident)
        self.assertEqual(status, 200)
        return data

    def action(self, ident, action, **kwargs):
        return self.request('POST', '/api/projects/'+ident+'/actions', {'action':action, **kwargs})

    def wait(self, ident, predicate=lambda p: not p['busy']):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result = self.get(ident)
            if predicate(result):
                return result
            time.sleep(.05)
        self.fail('worker did not reach expected state')

    def fake_processes(self):
        original = subprocess.Popen
        def launch(args, **kwargs):
            if args[:4] == [sys.executable, '-u', '-m', 'research_idea.chat_worker']:
                args = [sys.executable, '-u', str(self.worker)]
            return original(args, **kwargs)
        return patch('research_idea.web_runtime.subprocess.Popen', side_effect=launch)

    def test_create_persist_and_settings_do_not_expose_credentials(self):
        p = self.create(title='自演化智能体')
        self.assertEqual(p['model'], 'gpt-6-astra')
        self.assertEqual(p['stage'], 0)
        self.assertNotIn('api_key_env', p['config'])
        status, changed = self.request('POST', '/api/projects/'+p['id']+'/settings', {'reasoning_effort':'high', 'max_calls':90})
        self.assertEqual(status, 200)
        self.assertEqual(changed['config']['reasoning_effort'], 'high')
        self.assertEqual(load_config(Path(p['path']))['max_calls'], 90)
        self.assertEqual(self.request('POST', '/api/projects/'+p['id']+'/settings', {'output_dir':'/escape'})[0], 400)
        self.assertEqual(self.request('POST', '/api/projects/'+p['id']+'/settings', {'max_calls':-1})[0], 400)
        self.assertEqual(load_config(Path(p['path']))['max_calls'], 90)
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.start_server()
        self.assertEqual(self.get(p['id'])['title'], '自演化智能体')
        self.assertEqual(self.get(p['id'])['config']['reasoning_effort'], 'high')

    def test_write_requires_same_origin_and_session_token(self):
        self.assertEqual(self.request('POST', '/api/projects', {}, {'X-Research-Token':''})[0], 403)
        self.assertEqual(self.request('POST', '/api/projects', {}, {'Origin':'https://evil.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/projects', {}, {'Host':'evil.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/projects', {}, {'Content-Type':'text/plain'})[0], 415)
        self.assertEqual(self.request('GET', '/api/projects/..')[0], 404)
        self.assertEqual(self.request('POST', '/api/projects', {'model':[]})[0], 400)
        self.assertEqual(self.request('POST', '/api/projects', {'effort':'invented'})[0], 400)

    def test_web_exposes_skimmed_papers_without_claiming_body_reading(self):
        p = self.create(title='A focused research question')
        store = Store(Path(p['path']))
        try:
            store.set('literature_landscape', {'key': 'skim-v1', 'sources': [
                {'id': 'skim-only', 'title': 'An adjacent approach', 'abstract': 'A source abstract.',
                 'content_kind': 'abstract', 'url': 'https://example.org/paper'}],
                'notes': [{'paper_id': 'skim-only', 'claimed_progress': 'An author claim.'}], 'overview': {}})
        finally:
            store.close()
        snapshot = self.get(p['id'])
        self.assertEqual(snapshot['paper_count'], 1)
        self.assertEqual(snapshot['papers'][0]['content_kind'], 'abstract')
        self.assertEqual(snapshot['papers'][0]['url'], 'https://example.org/paper')
        self.assertEqual(snapshot['evidence'], [])
        self.assertEqual(snapshot['literature_landscape']['notes'][0]['claimed_progress'], 'An author claim.')

    def test_discussion_run_continue_and_reload_use_real_project_state(self):
        p = self.create()
        ident = p['id']
        self.assertEqual(self.action(ident, 'run')[0], 400)
        self.assertEqual(self.action(ident, 'continue')[0], 400)
        with self.fake_processes():
            self.assertEqual(self.action(ident, 'chat', message='self evolving agents')[0], 202)
            p = self.wait(ident)
            self.assertEqual(p['title'], 'self evolving agents')
            self.assertEqual([m['role'] for m in p['messages']], ['user','assistant'])
            self.assertEqual(self.action(ident, 'run')[0], 202)
            p = self.wait(ident)
            self.assertEqual(p['stage'], 2)
            self.assertTrue(p['can_continue'])
            self.assertEqual(p['steps'][1]['state'], 'complete')
            self.assertEqual(self.action(ident, 'run')[0], 400)
            self.assertEqual(self.action(ident, 'continue')[0], 202)
            p = self.wait(ident)
            self.assertEqual(p['status'], 'completed')
            self.assertTrue(all(s['state']=='complete' for s in p['steps']))
            self.assertTrue(any(e['tag']=='idea' for e in p['events']))

    def test_stop_rejects_duplicate_run_and_preserves_messages_and_time(self):
        ident = self.create()['id']
        with self.fake_processes():
            self.assertEqual(self.action(ident, 'chat', message='slow')[0], 202)
            self.wait(ident, lambda p: any(e['tag']=='thinking' for e in p['events']))
            self.assertEqual(self.action(ident, 'chat', message='duplicate')[0], 409)
            self.assertEqual(self.request('POST', '/api/projects/'+ident+'/settings', {'model':'gpt-6-astra'})[0], 409)
            self.assertEqual(self.action(ident, 'stop')[0], 200)
            p = self.wait(ident)
            self.assertEqual(p['last_job']['state'], 'stopped')
            self.assertEqual(p['messages'][0]['content'], 'slow')
            self.assertGreater(p['elapsed'], 0)
            self.assertTrue(any(e['tag']=='stopped' for e in p['events']))
            with project_lock(Path(p['path'])):
                pass

    def test_existing_cli_checkpoint_is_read_without_advancing(self):
        p = self.create(title='existing CLI research')
        store = Store(Path(p['path']))
        store.set_many({'status':'awaiting_problem_discussion', 'calls_used':12,
                        'problem_checkpoint':{'kind':'problem','state':'discussing','created_at':'2026-11-02T00:00:00Z'}})
        store.close()
        p = self.get(p['id'])
        self.assertEqual(p['stage'], 4)
        self.assertEqual(p['calls'], 12)
        self.assertEqual(p['checkpoint_time'], '2026-11-02T00:00:00Z')
        self.assertTrue(p['can_continue'])
        with project_lock(Path(p['path'])):
            p = self.get(p['id'])
            self.assertTrue(p['external'])
            self.assertEqual(self.action(p['id'], 'chat', message='busy')[0], 409)

    def test_workspace_root_is_owned_by_only_one_server(self):
        with self.assertRaises(RuntimeError):
            make_server(0, projects=self.root / 'projects')

    def test_concurrent_readers_do_not_report_each_other_as_external_workers(self):
        p = self.create()
        with ThreadPoolExecutor(max_workers=6) as pool:
            snapshots = list(pool.map(lambda _: self.server.workspace.snapshot(p['id']), range(36)))
        self.assertFalse(any(p['busy'] for p in snapshots))

    def test_pin_trash_restore_keep_original_records_and_order(self):
        first = self.create(title='keep my research')
        second = self.create(title='newer research')
        self.assertEqual(self.request('POST', '/api/projects/'+first['id']+'/actions', {'action':'pin','pinned':True})[0], 200)
        projects = self.request('GET', '/api/projects')[1]['projects']
        self.assertEqual(projects[0]['id'], first['id'])
        self.assertTrue(projects[0]['pinned'])
        self.assertEqual(self.action(first['id'], 'archive')[0], 200)
        self.assertFalse(Path(first['path']).exists())
        self.assertEqual(self.request('GET', '/api/trash')[1]['projects'][0]['title'], 'keep my research')
        self.assertEqual(self.request('GET', '/api/projects/'+first['id'])[0], 404)
        status, restored = self.request('POST', '/api/trash/'+first['id']+'/restore', {})
        self.assertEqual(status, 200)
        self.assertEqual(restored['title'], 'keep my research')
        self.assertTrue(restored['pinned'])
        self.assertEqual(self.request('GET', '/api/trash')[1]['projects'], [])
        self.assertTrue(Path(second['path']).is_dir())
        with project_lock(Path(first['path'])):
            self.assertEqual(self.action(first['id'], 'archive')[0], 409)


if __name__ == '__main__':
    unittest.main()
