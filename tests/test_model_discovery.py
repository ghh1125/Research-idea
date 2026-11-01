import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research_idea.model_discovery import cached_catalog, discover_models, normalize_models, read_codex_models


class ModelDiscoveryTests(unittest.TestCase):
    def test_normalize_public_fields_and_supported_efforts(self):
        result = normalize_models([
            {'model': 'one', 'displayName': 'One', 'secret': 'do-not-copy',
             'supportedReasoningEfforts': [{'reasoningEffort': 'high'}, {'reasoningEffort': 'ultra'}]},
            {'slug': 'two', 'supported_reasoning_levels': [{'effort': 'low'}]},
            {'slug': 'hidden', 'visibility': 'hide'}, {'model': 'hidden2', 'hidden': True},
            {'slug': 'one'}, {'slug': 'three', 'supported_reasoning_levels': None}, None])
        self.assertEqual([m['id'] for m in result], ['one', 'two', 'three'])
        self.assertEqual(result[0]['levels'], ['high', 'ultra'])
        self.assertNotIn('do-not-copy', str(result))

    def test_cache_is_multi_model_and_never_copies_identity(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, CODEX_HOME=tmp):
            Path(tmp, 'models_cache.json').write_text(json.dumps({'identity': 'private', 'fetched_at': 'today',
                'models': [{'slug': f'model-{i}'} for i in range(8)]}), encoding='utf-8')
            with patch('research_idea.model_discovery.read_codex_models') as rpc:
                result = discover_models()
            rpc.assert_not_called()
            self.assertEqual(len(result['models']), 8)
            self.assertEqual(result['source'], 'cache')
            self.assertNotIn('private', str(result))
            with patch('research_idea.model_discovery.read_codex_models', side_effect=TimeoutError):
                result = discover_models(refresh=True)
                profiled = discover_models(profile='different-account')
            self.assertEqual(len(result['models']), 8)
            self.assertTrue(result['error'])
            self.assertEqual(profiled['models'], [])

    def test_bad_cache_is_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, CODEX_HOME=tmp):
            for payload in ['not json', 'null', '[]', '{"models":null}']:
                Path(tmp, 'models_cache.json').write_text(payload, encoding='utf-8')
                self.assertEqual(cached_catalog()['models'], [])

    def test_rpc_handshake_pagination_and_cleanup(self):
        program = '''import json,sys
initialized=False
for line in sys.stdin:
    m=json.loads(line)
    if m['method']=='initialize':
        print(json.dumps({'id':m['id'],'result':{}}),flush=True)
    elif m['method']=='initialized': initialized=True
    elif m['method']=='model/list':
        assert initialized
        page=m['params'].get('cursor')
        print(json.dumps({'method':'notice','params':{'private':'ignore'}}),flush=True)
        print(json.dumps({'id':m['id'],'result':{'data':[{'model':'second' if page else 'first'}],
              'nextCursor':None if page else 'next'}}),flush=True)
'''
        popen = subprocess.Popen
        children = []
        def fake(command, **kwargs):
            self.assertEqual(command, ['custom-codex', '--profile', 'research', 'app-server', '--listen', 'stdio://'])
            child = popen([sys.executable, '-c', program], **kwargs)
            children.append(child)
            return child
        with patch('research_idea.model_discovery.subprocess.Popen', side_effect=fake):
            models = read_codex_models('custom-codex', 'research', timeout=5)
        self.assertEqual([m['id'] for m in models], ['first', 'second'])
        self.assertIsNotNone(children[0].poll())
        self.assertTrue(children[0].stdout.closed)

    def test_rpc_timeout_terminates_child(self):
        popen = subprocess.Popen
        children = []
        def fake(command, **kwargs):
            child = popen([sys.executable, '-c', 'import time; time.sleep(10)'], **kwargs)
            children.append(child)
            return child
        with patch('research_idea.model_discovery.subprocess.Popen', side_effect=fake):
            with self.assertRaises(TimeoutError):
                read_codex_models(timeout=.1)
        self.assertIsNotNone(children[0].poll())
