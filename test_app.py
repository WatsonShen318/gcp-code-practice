import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from app import Handler


class AppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path):
        connection = HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request("GET", path)
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def test_home(self):
        status, payload = self.request("/")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"message": "Hello World from Cloud Run!"})

    def test_health(self):
        status, payload = self.request("/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "ok"})

    def test_not_found(self):
        status, payload = self.request("/missing")
        self.assertEqual(status, 404)
        self.assertEqual(payload, {"error": "not found"})


if __name__ == "__main__":
    unittest.main()
