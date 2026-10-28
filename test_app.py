import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import app


class AppTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_home_and_assets(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.headers['content-type'])
        self.assertIn('PA Caddie', response.text)
        for asset in ('app.js', 'styles.css', 'loader.js'):
            self.assertEqual(self.client.get(f'/static/{asset}').status_code, 200)

    def test_sample_case(self):
        response = self.client.get('/api/case')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['schemaVersion'], 2)
        self.assertEqual(data['cases'][0]['id'], '26-900000001')
        self.assertEqual(len(data['questionMetadata']), 57)

    def test_json_edits_are_read_on_next_request(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'case.json'
            with patch('app.DATA_FILE', path):
                for number in ('first', 'updated'):
                    path.write_text(json.dumps({'paNumber': number}), encoding='utf-8')
                    self.assertEqual(self.client.get('/api/case').json()['paNumber'], number)

    def test_unreadable_or_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'case.json'
            with patch('app.DATA_FILE', path):
                self.assertEqual(self.client.get('/api/case').status_code, 500)
                for invalid in ('not json', '[]'):
                    path.write_text(invalid, encoding='utf-8')
                    response = self.client.get('/api/case')
                    self.assertEqual(response.status_code, 500)
                    self.assertIn('detail', response.json())


if __name__ == '__main__':
    unittest.main()
