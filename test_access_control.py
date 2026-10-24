import importlib
import logging
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
from authlib.integrations.httpx_client.oauth2_client import Response as OAuthResponse
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from access_control import AuthSettings, CallbackLogFilter, DEFAULT_GROUPS, group_name, install_access_control

oauth_http = importlib.import_module(OAuthResponse.__module__.split(".")[0])


class AccessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.settings = AuthSettings(
            enabled=True, client_id="test-client", client_secret="test-only-client-secret",
            authorize_url="https://sso.example/authorize", token_url="https://sso.example/token",
            userinfo_url="https://sso.example/userinfo", issuer="https://sso.example",
            jwks_url="https://sso.example/jwks", audience="test-api",
            redirect_uri="https://app.example/auth/callback", session_secret="test-only-session-secret-32-characters-long",
        )
        self.app = FastAPI()
        install_access_control(self.app, self.settings)
        self.access = self.app.state.access_control

        @self.app.get("/health")
        def health():
            return {"status": "ok"}

        @self.app.get("/")
        def home():
            return {"page": "review"}

        @self.app.get("/api/case")
        def case():
            return {"data": "protected"}

        self.app.mount("/static", StaticFiles(directory="static"))
        self.client = TestClient(self.app, base_url="https://app.example", follow_redirects=False)
        self.claims = {
            "sub": "employee-1", "mail": "USER@example.com", "groups": ["app-paops-eng"],
            "iss": self.settings.issuer, "aud": self.settings.audience, "exp": int(time.time()) + 600,
        }

    def provider(self, request):
        self.assertEqual(request.url.path, "/token")
        body = parse_qs(request.content.decode())
        self.assertIn("code_verifier", body)
        return oauth_http.Response(200, json={
            "access_token": jwt.encode(self.claims, self.key, algorithm="RS256", headers={"kid": "test-key"}),
            "token_type": "Bearer", "expires_in": 600,
        })

    def login(self):
        self.access.client.client_kwargs["transport"] = oauth_http.MockTransport(self.provider)
        redirect = self.client.get("/auth/login")
        self.assertEqual(redirect.status_code, 302)
        query = parse_qs(urlsplit(redirect.headers["location"]).query)
        self.assertEqual(query["code_challenge_method"], ["S256"])
        with patch.object(self.access.keys, "get_signing_key_from_jwt", return_value=SimpleNamespace(key=self.key.public_key())):
            return self.client.get("/auth/callback", params={"code": "test-code", "state": query["state"][0]})

    def test_allowed_login_and_protected_resources(self):
        with self.assertLogs("uvicorn.error", level="INFO") as logs:
            response = self.login()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/")
        cookie = response.headers.get_list("set-cookie")[0]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn('"email": "user@example.com"', "\n".join(logs.output))
        self.assertNotIn("test-code", "\n".join(logs.output))
        for path in ["/", "/api/case", "/static/app.js"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")

    def test_each_screenshot_group_and_ldap_name_is_allowed(self):
        for name in DEFAULT_GROUPS:
            self.assertEqual(self.access.match([group_name(f"CN={name.upper()},OU=Groups,DC=example")]), [name])
        self.assertEqual(self.access.match(["app-paops-eng-extra"]), [])
        self.assertEqual(len(DEFAULT_GROUPS), 11)

    def test_nonmember_is_403_and_email_is_logged(self):
        self.claims["groups"] = ["some-other-group"]
        with self.assertLogs("uvicorn.error", level="INFO") as logs:
            response = self.login()
        self.assertEqual(response.status_code, 403)
        self.assertIn('"email": "user@example.com"', "\n".join(logs.output))
        self.assertNotIn(self.access.cookie_name, self.client.cookies)
        self.assertEqual(self.client.get("/api/case").status_code, 401)

    def test_anonymous_and_spoofed_email_cannot_read_application(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        response = self.client.get("/", headers={"X-Email": "user@example.com", "X-Groups": "app-paops-eng"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/auth/login")
        for path in ["/api/case", "/static/app.js", "/docs", "/openapi.json"]:
            self.assertEqual(self.client.get(path).status_code, 401)

    def test_missing_state_cannot_authenticate(self):
        self.assertEqual(self.client.get("/auth/callback", params={"code": "fake"}).status_code, 401)

    def test_expired_and_wrong_audience_access_tokens_fail(self):
        for claim, value in [("exp", int(time.time())-60), ("aud", "another-app"), ("iss", "https://other.example")]:
            original = self.claims[claim]
            self.claims[claim] = value
            self.assertEqual(self.login().status_code, 401)
            self.claims[claim] = original

    def test_tampered_session_is_rejected(self):
        self.login()
        self.client.cookies.clear()
        self.client.cookies.set(self.access.cookie_name, "forged.cookie.value")
        self.assertEqual(self.client.get("/api/case").status_code, 401)

    def test_userinfo_fallback_supplies_email_and_groups(self):
        self.claims.pop("mail")
        self.claims.pop("groups")
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
            "sub": "employee-1", "email": "fallback@example.com", "Groups": ["CN=app-paops-eng,OU=Groups"],
        }))
        with patch("access_control.httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
            self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.client.get("/api/case").status_code, 200)

    def test_userinfo_from_another_subject_is_rejected(self):
        self.claims.pop("mail")
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"sub": "someone-else", "email": "other@example.com"}))
        with patch("access_control.httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
            self.assertEqual(self.login().status_code, 401)

    def test_access_token_with_wrong_signature_is_rejected(self):
        wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = jwt.encode(self.claims, wrong_key, algorithm="RS256")
        with patch.object(self.access.keys, "get_signing_key_from_jwt", return_value=SimpleNamespace(key=self.key.public_key())):
            with self.assertRaises(jwt.InvalidSignatureError):
                self.access.decode_access_token(token)

    def test_access_logs_redact_callback_query(self):
        record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s %s %s %s %s',
                                   ("client", "GET", "/auth/callback?code=do-not-log&state=test", "1.1", 302), None)
        CallbackLogFilter().filter(record)
        self.assertNotIn("do-not-log", record.getMessage())

    def test_expired_or_wrong_group_session_is_rejected(self):
        for expired, groups, status in [(True, ["app-paops-eng"], 401), (False, ["unrelated"], 403)]:
            now = int(time.time())
            value = jwt.encode({
                "sub": "employee-1", "email": "user@example.com", "groups": groups,
                "iss": self.access.cookie_issuer, "aud": self.access.cookie_audience,
                "iat": now-100, "exp": now-10 if expired else now+100,
            }, self.settings.session_secret, algorithm="HS256")
            self.client.cookies.set(self.access.cookie_name, value)
            self.assertEqual(self.client.get("/api/case").status_code, status)

    def test_missing_configuration_and_empty_allowlist_fail_closed(self):
        with patch.dict("os.environ", {"AUTH_ENABLED": "true"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "Missing authentication configuration"):
                AuthSettings.from_env()
        self.settings.allowed_groups = frozenset()
        with self.assertRaisesRegex(RuntimeError, "must not be empty"):
            self.settings.validate()


if __name__ == "__main__":
    unittest.main()
