"""Ping userinfo-based identity and AD group authorization for PA Caddie."""

import base64
import hashlib
import hmac
import json
import logging
import math
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit

import httpx
import jwt
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from secret_loader import load_client_secret

logger = logging.getLogger("uvicorn.error")
ALLOWED_GROUPS = frozenset({
    "app-paops-eng", "app-paops-pnp-eng", "app-paops-prod-eng",
    "app-paops-restrict-admin", "app-paops-restrict-eng",
    "app-paops-rnp-admin", "app-paops-rnp-eng",
    "clb-paops-rnp-editor", "clb-paops-rnp-read",
    "csm-paops-pnp-read", "csm-paops-rnp-read",
})


def normalize_group(value):
    if not isinstance(value, str):
        raise ValueError("Group names must be strings")
    value = value.strip()
    if value.upper().startswith("CN="):
        value = value.split(",", 1)[0][3:]
    return value.strip().casefold()


def extract_groups(userinfo):
    """Combine Ping's groups_cn and groups, including string or list claims."""
    groups = set()
    for claim in ("groups_cn", "groups"):
        values = userinfo.get(claim) or []
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            raise ValueError("Invalid group claim")
        for value in values:
            name = normalize_group(value)
            if name:
                groups.add(name)
    return sorted(groups)


@dataclass
class PingSettings:
    enabled: bool = False
    client_id: str = "APM0015442"
    client_secret: str = field(default="", repr=False)
    redirect_uri: str = ""
    session_secret: str = field(default="", repr=False)
    auth_url: str = "https://authsvc.cvshealth.com/as/authorization.oauth2"
    token_endpoint: str = "https://authsvc.cvshealth.com/as/token.oauth2"
    userinfo_endpoint: str = "https://authsvc.cvshealth.com/idp/userinfo.openid"
    session_seconds: int = 7200

    @classmethod
    def from_env(cls):
        enabled = os.getenv("AUTH_ENABLED", "false").strip().lower()
        if enabled not in {"true", "false"}:
            raise ValueError("AUTH_ENABLED must be true or false")
        settings = cls(
            enabled=enabled == "true", client_id=os.getenv("SSO_CLIENT_ID") or cls.client_id,
            client_secret=os.getenv("SSO_CLIENT_SECRET") or os.getenv("sso_client_secret", ""),
            redirect_uri=os.getenv("REDIRECT_URI", ""), session_secret=os.getenv("SHARED_SECRET_KEY", ""),
            auth_url=os.getenv("AUTH_URL", cls.auth_url),
            token_endpoint=os.getenv("TOKEN_ENDPOINT", cls.token_endpoint),
            userinfo_endpoint=os.getenv("USERINFO_ENDPOINT", cls.userinfo_endpoint),
            session_seconds=int(os.getenv("TOKEN_EXPIRATION_TIME", "7200")),
        )
        if settings.enabled:
            settings.client_secret = load_client_secret(settings.client_secret)
            if settings.client_secret and not settings.session_secret:
                # A stable, application-specific key shared by all replicas. Do not
                # reuse the public placeholder session key from the reference ZIP.
                context = "pa-caddie/session/v1\0" + settings.client_id + "\0" + settings.redirect_uri
                settings.session_secret = hmac.new(settings.client_secret.encode(), context.encode(), hashlib.sha256).hexdigest()
        return settings

    def validate(self):
        required = {"SSO_CLIENT_ID": self.client_id, "SSO_CLIENT_SECRET": self.client_secret,
                    "REDIRECT_URI": self.redirect_uri, "SHARED_SECRET_KEY": self.session_secret}
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError("Missing authentication configuration: " + ", ".join(missing))
        if len(self.session_secret) < 32:
            raise ValueError("SHARED_SECRET_KEY must contain at least 32 random characters")
        if not 60 <= self.session_seconds <= 86400:
            raise ValueError("TOKEN_EXPIRATION_TIME must be between 60 and 86400 seconds")
        for name, value in {"AUTH_URL": self.auth_url, "TOKEN_ENDPOINT": self.token_endpoint,
                            "USERINFO_ENDPOINT": self.userinfo_endpoint, "REDIRECT_URI": self.redirect_uri}.items():
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError(f"{name} must be an HTTPS URL without credentials, query, or fragment")
        if urlsplit(self.redirect_uri).path != "/token":
            raise ValueError("REDIRECT_URI must use this application's /token callback")


class CallbackLogFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            path = record.args[2]
            if isinstance(path, str) and path.split("?", 1)[0] == "/token":
                record.args = (*record.args[:2], "/token", *record.args[3:])
        return True


def audit(request, email, decision, reason, groups=()):
    logger.info(json.dumps({
        "event": "access_check", "time": datetime.now(timezone.utc).isoformat(),
        "email": email, "decision": decision, "reason": reason,
        "matched_groups": list(groups), "path": request.url.path,
    }))


def failure(status, detail):
    return JSONResponse({"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"})


class PingAuth:
    cookie_name = "pa_caddie_ping"
    issuer = "pa-caddie-ping"
    audience = "pa-caddie-web"

    def __init__(self, settings):
        self.settings = settings

    def read_session(self, request):
        token = request.cookies.get(self.cookie_name)
        if not token:
            return None
        try:
            claims = jwt.decode(token, self.settings.session_secret, algorithms=["HS256"],
                                issuer=self.issuer, audience=self.audience,
                                options={"require": ["iss", "aud", "sub", "email", "groups", "iat", "exp"]})
            if not isinstance(claims["email"], str) or not claims["email"].strip() or not isinstance(claims["sub"], str) or not claims["sub"]:
                return None
            claims["groups"] = extract_groups({"groups": claims["groups"]})
            return claims
        except (jwt.InvalidTokenError, ValueError, TypeError):
            return None

    async def guard(self, request, call_next):
        if request.url.path in {"/health", "/login", "/token", "/logout"}:
            return await call_next(request)
        identity = self.read_session(request)
        if identity is None:
            audit(request, None, "deny", "unauthenticated")
            if request.method in {"GET", "HEAD"} and request.url.path == "/":
                return RedirectResponse("/login", status_code=302, headers={"Cache-Control": "no-store"})
            return failure(401, "Authentication required")
        matched = sorted(set(identity["groups"]) & ALLOWED_GROUPS)
        if not matched:
            audit(request, identity["email"], "deny", "group_not_allowed")
            return failure(403, "Access denied: required AD group membership is missing")
        request.state.user = identity
        audit(request, identity["email"], "allow", "group_allowed", matched)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    async def login(self, request: Request):
        # Bind the callback to this browser, with short-lived random state and PKCE.
        request.session.clear()
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        request.session["ping_login"] = {"state": state, "verifier": verifier, "created": time.time()}
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        params = urlencode({"response_type": "code", "client_id": self.settings.client_id,
                            "redirect_uri": self.settings.redirect_uri, "scope": "openid groups profile email",
                            "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})
        response = RedirectResponse(self.settings.auth_url + "?" + params, status_code=302)
        response.headers["Cache-Control"] = "no-store"
        response.delete_cookie(self.cookie_name, path="/", secure=True, httponly=True, samesite="lax")
        return response

    async def fetch_userinfo(self, code, verifier):
        # Treat access_token as opaque. Ping's HTTPS userinfo endpoint verifies it.
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            token_response = await client.post(
                self.settings.token_endpoint,
                auth=httpx.BasicAuth(self.settings.client_id, self.settings.client_secret),
                data={"grant_type": "authorization_code", "redirect_uri": self.settings.redirect_uri,
                      "code": code, "code_verifier": verifier},
            )
            token_response.raise_for_status()
            token_data = token_response.json()
            access_token = token_data.get("access_token")
            if not isinstance(access_token, str) or not access_token:
                raise ValueError("Missing access token")
            info_response = await client.get(self.settings.userinfo_endpoint,
                                            headers={"Authorization": f"Bearer {access_token}"})
            info_response.raise_for_status()
            info = info_response.json()
        email, subject = info.get("email") or info.get("mail"), info.get("sub")
        if not isinstance(email, str) or not email.strip() or not isinstance(subject, str) or not subject:
            raise ValueError("Userinfo must contain email and subject")
        lifetime = float(token_data.get("expires_in", self.settings.session_seconds))
        if not math.isfinite(lifetime) or lifetime < 1:
            raise ValueError("Invalid token lifetime")
        return {"sub": subject, "email": email.strip().lower(), "groups": extract_groups(info),
                "lifetime": min(self.settings.session_seconds, int(lifetime))}

    async def callback(self, request: Request):
        pending = request.session.pop("ping_login", None)
        identity = None
        try:
            state, code = request.query_params.get("state", ""), request.query_params.get("code", "")
            if not pending or not state or not code or request.query_params.get("error"):
                raise ValueError("Missing login state or code")
            if not hmac.compare_digest(state, pending["state"]) or not 0 <= time.time()-pending["created"] < 600:
                raise ValueError("Invalid or expired login state")
            identity = await self.fetch_userinfo(code, pending["verifier"])
        except Exception as error:
            audit(request, None, "deny", "authentication_failed:" + type(error).__name__)
            response = failure(401, "Company login failed; start again at /login")
        else:
            matched = sorted(set(identity["groups"]) & ALLOWED_GROUPS)
            if not matched:
                audit(request, identity["email"], "deny", "group_not_allowed")
                response = failure(403, "Access denied: required AD group membership is missing")
            else:
                now = int(time.time())
                lifetime = identity["lifetime"]
                token = jwt.encode({"sub": identity["sub"], "email": identity["email"], "groups": matched,
                                    "iss": self.issuer, "aud": self.audience, "iat": now, "exp": now+lifetime},
                                   self.settings.session_secret, algorithm="HS256")
                response = RedirectResponse("/", status_code=302)
                response.set_cookie(self.cookie_name, token, max_age=lifetime, path="/", secure=True,
                                    httponly=True, samesite="lax")
                response.headers["Cache-Control"] = "no-store"
                audit(request, identity["email"], "allow", "login_allowed", matched)
        request.session.clear()
        if response.status_code != 302:
            response.delete_cookie(self.cookie_name, path="/", secure=True, httponly=True, samesite="lax")
        return response

    async def logout(self, request: Request):
        request.session.clear()
        response = RedirectResponse("/login", status_code=302, headers={"Cache-Control": "no-store"})
        response.delete_cookie(self.cookie_name, path="/", secure=True, httponly=True, samesite="lax")
        return response


def install_ping_auth(app, settings=None):
    """Missing configuration blocks the app, but leaves /health available."""
    try:
        settings = settings or PingSettings.from_env()
        app.state.ping_settings = settings
        if not settings.enabled:
            return
        settings.validate()
    except ValueError as error:
        app.state.auth_configuration_error = str(error)
        logger.error("Ping configuration unavailable: %s", error)

        @app.middleware("http")
        async def unavailable(request, call_next):
            if request.url.path == "/health":
                return await call_next(request)
            return failure(503, "Company login is not configured; contact the application administrator")

        return
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, CallbackLogFilter) for item in access_logger.filters):
        access_logger.addFilter(CallbackLogFilter())
    auth = PingAuth(settings)
    app.state.ping_auth = auth
    app.middleware("http")(auth.guard)
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, session_cookie="pa_caddie_login_state",
                       max_age=600, same_site="lax", https_only=True)
    app.add_api_route("/login", auth.login, methods=["GET"], include_in_schema=False)
    app.add_api_route("/token", auth.callback, methods=["GET"], include_in_schema=False)
    app.add_api_route("/logout", auth.logout, methods=["GET"], include_in_schema=False)
