import http.client
import json
import threading
import unittest
from unittest.mock import patch

from research_idea.cli import build_parser
from research_idea.web import make_server


class WebTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def get(self, path, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            conn.request('GET', path, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_html_and_parser(self):
        status, body = self.get('/')
        self.assertEqual(status, 200)
        self.assertIn(b'/api/models?', body)
        args = build_parser().parse_args(['web', '--no-browser', '--port', '0'])
        self.assertTrue(args.no_browser)
        self.assertEqual(args.port, 0)

    def test_model_refresh_returns_all_choices(self):
        with patch('research_idea.web.discover_models', return_value={'models': [{'id':'a'}, {'id':'b'}]}) as discover:
            status, body = self.get('/api/models?refresh=1')
            self.assertEqual(status, 200)
            self.assertEqual(len(json.loads(body)['models']), 2)
            discover.assert_called_once_with(refresh=True, codex_bin='codex', profile=None)

    def test_other_backend_does_not_receive_codex_choices(self):
        with patch('research_idea.web.discover_models') as discover:
            status, body = self.get('/api/models?backend=claude')
            self.assertEqual(json.loads(body)['models'], [])
            discover.assert_not_called()

    def test_builtin_skill_source_is_readable_without_arbitrary_file_access(self):
        status, body = self.get('/api/skills/research-idea-motivation')
        self.assertEqual(status, 200)
        self.assertIn('content', json.loads(body))
        self.assertEqual(self.get('/api/skills/../../pyproject.toml')[0], 404)

    def test_local_catalog_cannot_be_requested_from_foreign_origin(self):
        with patch('research_idea.web.discover_models') as discover:
            self.assertEqual(self.get('/api/models', {'Origin': 'https://other.example'})[0], 403)
            self.assertEqual(self.get('/api/models', {'Host': 'other.example'})[0], 403)
            discover.assert_not_called()
        self.assertEqual(self.get('/../../pyproject.toml')[0], 404)
