import base64
import hashlib
import logging
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from ping_auth import ALLOWED_GROUPS, CallbackLogFilter, PingSettings, extract_groups, install_ping_auth


class PingAuthTest(unittest.TestCase):
    def make_app(self, settings):
        app = FastAPI()
        install_ping_auth(app, settings)

        @app.get("/health")
        def health():
            return {"status": "ok"}

        @app.get("/")
        def home():
            return {"page": "review"}

        @app.get("/api/case")
        def case():
            return {"data": "protected"}

        app.mount("/static", StaticFiles(directory="static"))
        return app

    def setUp(self):
        self.settings = PingSettings(
            enabled=True, client_id="test-client", client_secret="test-only-secret",
            redirect_uri="https://app.example/token", session_secret="test-only-session-secret-longer-than-32-characters",
            auth_url="https://sso.example/authorize", token_endpoint="https://sso.example/token",
            userinfo_endpoint="https://sso.example/userinfo",
        )
        self.app = self.make_app(self.settings)
        self.auth = self.app.state.ping_auth
        self.client = TestClient(self.app, base_url="https://app.example", follow_redirects=False)
        self.info = {"sub": "employee-1", "email": "USER@example.com", "groups_cn": ["app-paops-eng"]}
        self.provider_calls = []

    def provider(self, request):
        self.provider_calls.append(request)
        if request.method == "POST":
            self.assertEqual(str(request.url), self.settings.token_endpoint)
            expected = base64.b64encode(b"test-client:test-only-secret").decode()
            self.assertEqual(request.headers["authorization"], f"Basic {expected}")
            data = parse_qs(request.content.decode())
            self.assertEqual(data["grant_type"], ["authorization_code"])
            self.assertEqual(data["redirect_uri"], [self.settings.redirect_uri])
            self.assertEqual(data["code"], ["test-code"])
            verifier = data["code_verifier"][0]
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
            self.assertEqual(challenge, self.challenge)
            # Explicitly opaque, not a JWT: identity comes from userinfo.
            return httpx.Response(200, json={"access_token": "opaque-ping-token", "expires_in": 3600})
        self.assertEqual(str(request.url), self.settings.userinfo_endpoint)
        self.assertEqual(request.headers["authorization"], "Bearer opaque-ping-token")
        return httpx.Response(200, json=self.info)

    def start_login(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 302)
        params = parse_qs(urlsplit(response.headers["location"]).query)
        self.assertEqual(params["scope"], ["openid profile email PHGroup"])
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.challenge = params["code_challenge"][0]
        return params["state"][0]

    def callback(self, state):
        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(self.provider))
        with patch("ping_auth.httpx.AsyncClient", return_value=mock_client):
            return self.client.get("/token", params={"state": state, "code": "test-code"})

    def login(self):
        return self.callback(self.start_login())

    def set_session(self, groups=None, expired=False):
        now = int(time.time())
        token = jwt.encode({"sub": "employee-1", "email": "user@example.com", "groups": groups or ["app-paops-eng"],
                            "iss": self.auth.issuer, "aud": self.auth.audience, "iat": now-100,
                            "exp": now-10 if expired else now+100}, self.settings.session_secret, algorithm="HS256")
        self.client.cookies.clear()
        self.client.cookies.set(self.auth.cookie_name, token)

    def test_userinfo_groups_cn_allows_page_and_logs_email(self):
        with self.assertLogs("uvicorn.error", level="INFO") as logs:
            response = self.login()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/")
        output = "\n".join(logs.output)
        self.assertIn('"email": "user@example.com"', output)
        self.assertNotIn("opaque-ping-token", output)
        self.assertNotIn("test-only-secret", output)
        cookie = response.headers.get_list("set-cookie")[0]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertNotIn("opaque-ping-token", cookie)
        for path in ("/", "/api/case", "/static/app.js"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")

    def test_groups_dn_and_groups_cn_are_combined(self):
        self.assertEqual(extract_groups({"groups_cn": ["A", "B"], "groups": ["CN=B,OU=Groups", "CN=C,OU=Groups"]}), ["a", "b", "c"])
        self.info.pop("groups_cn")
        self.info["groups"] = "CN=APP-PAOPS-ENG,OU=Groups,DC=example"
        self.assertEqual(self.login().status_code, 302)

    def test_all_eleven_screenshot_groups_allow_access(self):
        self.assertEqual(len(ALLOWED_GROUPS), 11)
        for name in ALLOWED_GROUPS:
            self.info["groups_cn"] = [name.upper()]
            self.assertEqual(self.login().status_code, 302, name)

    def test_nonmember_or_missing_groups_returns_403(self):
        for groups in (["unrelated"], ["app-paops-eng-extra"], []):
            self.info["groups_cn"] = groups
            with self.assertLogs("uvicorn.error", level="INFO") as logs:
                response = self.login()
            self.assertEqual(response.status_code, 403)
            self.assertIn("user@example.com", "\n".join(logs.output))
            self.assertEqual(self.client.get("/api/case").status_code, 401)

    def test_malformed_or_missing_identity_fails_closed(self):
        for value in (None, "", 123):
            self.info["email"] = value
            self.assertEqual(self.login().status_code, 401)
        self.info["email"] = "user@example.com"
        self.info["groups_cn"] = {"admin": True}
        self.assertEqual(self.login().status_code, 401)

    def test_anonymous_cannot_read_page_api_or_assets(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        response = self.client.get("/")
        self.assertEqual(response.headers["location"], "/login")
        for path in ("/api/case", "/static/app.js", "/docs", "/openapi.json"):
            response = self.client.get(path, headers={"X-Email": "user@example.com", "X-Groups": "app-paops-eng"})
            self.assertEqual(response.status_code, 401)

    def test_missing_wrong_and_replayed_state_are_rejected(self):
        self.assertEqual(self.client.get("/token", params={"code": "test-code"}).status_code, 401)
        self.start_login()
        self.assertEqual(self.callback("wrong-state").status_code, 401)
        self.assertEqual(self.provider_calls, [])
        state = self.start_login()
        self.assertEqual(self.callback(state).status_code, 302)
        count = len(self.provider_calls)
        self.assertEqual(self.callback(state).status_code, 401)
        self.assertEqual(len(self.provider_calls), count)

    def test_tampered_expired_and_disallowed_sessions_are_rejected(self):
        self.client.cookies.set(self.auth.cookie_name, "forged.cookie.value")
        self.assertEqual(self.client.get("/api/case").status_code, 401)
        self.set_session(expired=True)
        self.assertEqual(self.client.get("/api/case").status_code, 401)
        self.set_session(groups=["unrelated"])
        self.assertEqual(self.client.get("/api/case").status_code, 403)

    def test_ping_failure_does_not_create_session(self):
        state = self.start_login()
        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(500)))
        with patch("ping_auth.httpx.AsyncClient", return_value=mock_client):
            response = self.client.get("/token", params={"state": state, "code": "test-code"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.get("/api/case").status_code, 401)

    def test_invalid_token_lifetime_is_rejected(self):
        for lifetime in (0, -1, 0.5, "Infinity", "not-a-number"):
            state = self.start_login()

            def provider(request):
                if request.method == "POST":
                    return httpx.Response(200, json={"access_token": "opaque", "expires_in": lifetime})
                return httpx.Response(200, json=self.info)

            mock_client = httpx.AsyncClient(transport=httpx.MockTransport(provider))
            with patch("ping_auth.httpx.AsyncClient", return_value=mock_client):
                response = self.client.get("/token", params={"state": state, "code": "test-code"})
            self.assertEqual(response.status_code, 401)

    def test_logout_clears_local_session(self):
        self.login()
        self.assertEqual(self.client.get("/logout").headers["location"], "/login")
        self.assertEqual(self.client.get("/api/case").status_code, 401)

    def test_missing_config_keeps_health_but_blocks_application(self):
        app = self.make_app(PingSettings(enabled=True))
        client = TestClient(app)
        self.assertEqual(client.get("/health").status_code, 200)
        for path in ("/", "/login", "/api/case", "/static/app.js"):
            self.assertEqual(client.get(path).status_code, 503)

    def test_non_https_callback_and_weak_session_key_are_rejected(self):
        self.settings.redirect_uri = "http://app.example/token"
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            self.settings.validate()
        self.settings.redirect_uri = "https://app.example/token"
        self.settings.session_secret = "short"
        with self.assertRaisesRegex(ValueError, "32"):
            self.settings.validate()

    def test_callback_logs_do_not_expose_code(self):
        record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "%s %s %s %s %s",
                                   ("client", "GET", "/token?code=do-not-log&state=test", "1.1", 302), None)
        CallbackLogFilter().filter(record)
        self.assertNotIn("do-not-log", record.getMessage())


if __name__ == "__main__":
    unittest.main()
