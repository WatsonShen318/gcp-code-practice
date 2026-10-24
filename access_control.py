"""Corporate identity and group access, independent of the SAGE application."""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
import jwt
from authlib.integrations.starlette_client import OAuth
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

logger = logging.getLogger("uvicorn.error")


class CallbackLogFilter(logging.Filter):
    """Uvicorn must not put the callback authorization code in access logs."""

    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            path = record.args[2]
            if isinstance(path, str) and path.split("?", 1)[0] == "/auth/callback":
                record.args = (*record.args[:2], "/auth/callback", *record.args[3:])
        return True

# Exact names transcribed from the supplied Azure group screenshot.
DEFAULT_GROUPS = frozenset({
    "app-paops-eng", "app-paops-pnp-eng", "app-paops-prod-eng",
    "app-paops-restrict-admin", "app-paops-restrict-eng",
    "app-paops-rnp-admin", "app-paops-rnp-eng",
    "clb-paops-rnp-editor", "clb-paops-rnp-read",
    "csm-paops-pnp-read", "csm-paops-rnp-read",
})


def group_name(value):
    """Accept the reference service's plain names or LDAP CN values."""
    if not isinstance(value, str):
        return None
    for part in value.split(","):
        if part.strip().upper().startswith("CN="):
            return part.strip()[3:].strip().casefold()
    return value.strip().casefold() or None


def read_groups(claims):
    raw = claims.get("groups") or claims.get("Groups") or claims.get("GROUPS") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("Invalid group claim")
    return sorted({name for value in raw if (name := group_name(value))})


@dataclass
class AuthSettings:
    enabled: bool = False
    client_id: str = ""
    client_secret: str = field(default="", repr=False)
    authorize_url: str = ""
    token_url: str = ""
    userinfo_url: str = ""
    issuer: str = ""
    jwks_url: str = ""
    audience: str = ""
    redirect_uri: str = ""
    session_secret: str = field(default="", repr=False)
    allowed_groups: frozenset = DEFAULT_GROUPS
    session_seconds: int = 900

    @classmethod
    def from_env(cls):
        enabled = os.getenv("AUTH_ENABLED", "false").lower()
        if enabled not in {"true", "false"}:
            raise RuntimeError("AUTH_ENABLED must be true or false")
        supplied = os.getenv("AUTH_ALLOWED_GROUPS")
        settings = cls(
            enabled=enabled == "true",
            client_id=os.getenv("SSO_CLIENT_ID", ""),
            client_secret=os.getenv("SSO_CLIENT_SECRET", ""),
            authorize_url=os.getenv("SSO_AUTHORIZE_URL", ""),
            token_url=os.getenv("SSO_TOKEN_URL", ""),
            userinfo_url=os.getenv("SSO_USERINFO_URL", ""),
            issuer=os.getenv("SSO_ISSUER", ""),
            jwks_url=os.getenv("SSO_JWKS_URL", ""),
            audience=os.getenv("SSO_AUDIENCE", ""),
            redirect_uri=os.getenv("SSO_REDIRECT_URI", ""),
            session_secret=os.getenv("AUTH_SESSION_SECRET", ""),
            allowed_groups=frozenset(name for item in supplied.split(",") if (name := group_name(item))) if supplied is not None else DEFAULT_GROUPS,
        )
        if settings.enabled:
            settings.validate()
        return settings

    def validate(self):
        required = {
            "SSO_CLIENT_ID": self.client_id, "SSO_CLIENT_SECRET": self.client_secret,
            "SSO_AUTHORIZE_URL": self.authorize_url, "SSO_TOKEN_URL": self.token_url,
            "SSO_USERINFO_URL": self.userinfo_url, "SSO_ISSUER": self.issuer,
            "SSO_JWKS_URL": self.jwks_url, "SSO_AUDIENCE": self.audience,
            "SSO_REDIRECT_URI": self.redirect_uri, "AUTH_SESSION_SECRET": self.session_secret,
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise RuntimeError("Missing authentication configuration: " + ", ".join(missing))
        if len(self.session_secret) < 32:
            raise RuntimeError("AUTH_SESSION_SECRET must contain at least 32 random characters")
        if not self.allowed_groups:
            raise RuntimeError("AUTH_ALLOWED_GROUPS must not be empty")
        for name, value in required.items():
            if name.endswith("_URL") or name in {"SSO_ISSUER", "SSO_REDIRECT_URI"}:
                parsed = urlsplit(value)
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
                    raise RuntimeError(f"{name} must be an HTTPS URL without credentials or fragment")


class AccessControl:
    cookie_name = "pa_caddie_session"
    cookie_issuer = "pa-caddie"
    cookie_audience = "pa-caddie-web"

    def __init__(self, settings):
        self.settings = settings
        self.oauth = OAuth()
        self.client = self.oauth.register(
            "corporate", client_id=settings.client_id, client_secret=settings.client_secret,
            authorize_url=settings.authorize_url, access_token_url=settings.token_url,
            userinfo_endpoint=settings.userinfo_url, issuer=settings.issuer, jwks_uri=settings.jwks_url,
            client_kwargs={"scope": "openid profile email", "code_challenge_method": "S256", "token_endpoint_auth_method": "client_secret_post", "timeout": 10},
        )
        self.keys = jwt.PyJWKClient(settings.jwks_url, timeout=10)

    def audit(self, request, email, decision, reason, groups=()):
        logger.info(json.dumps({
            "event": "access_check", "email": email, "decision": decision,
            "time": datetime.now(timezone.utc).isoformat(),
            "reason": reason, "matched_groups": list(groups), "path": request.url.path,
        }))

    def match(self, groups):
        return sorted(set(groups) & self.settings.allowed_groups)

    def decode_access_token(self, token):
        key = self.keys.get_signing_key_from_jwt(token).key
        return jwt.decode(token, key, algorithms=["RS256"], issuer=self.settings.issuer,
                          audience=self.settings.audience, options={"require": ["exp", "iss", "aud", "sub"]})

    async def identity(self, token):
        # Same source as the reference, but validate the JWT before trusting claims.
        claims = await run_in_threadpool(self.decode_access_token, token["access_token"])
        email = claims.get("mail") or claims.get("email")
        groups = read_groups(claims)
        if not email or not groups:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                response = await client.get(self.settings.userinfo_url, headers={"Authorization": f"Bearer {token['access_token']}"})
                response.raise_for_status()
                info = response.json()
            # Do not combine identities from different subjects.
            if info.get("sub") != claims["sub"]:
                raise ValueError("Userinfo subject mismatch")
            email = email or info.get("email") or info.get("mail")
            groups = groups or read_groups(info)
        if not isinstance(email, str) or not email.strip() or not isinstance(claims["sub"], str) or not claims["sub"]:
            raise ValueError("Missing identity")
        return {"email": email.strip().lower(), "sub": claims["sub"], "groups": groups, "exp": claims["exp"]}

    def session(self, request):
        token = request.cookies.get(self.cookie_name)
        if not token:
            return None
        try:
            claims = jwt.decode(token, self.settings.session_secret, algorithms=["HS256"],
                                issuer=self.cookie_issuer, audience=self.cookie_audience,
                                options={"require": ["exp", "iat", "iss", "aud", "sub", "email", "groups"]})
            if not isinstance(claims["email"], str) or not claims["email"] or not isinstance(claims["groups"], list):
                return None
            return claims
        except jwt.InvalidTokenError:
            return None

    async def guard(self, request, call_next):
        if request.url.path in {"/health", "/auth/login", "/auth/callback"}:
            return await call_next(request)
        identity = self.session(request)
        if identity is None:
            self.audit(request, None, "deny", "unauthenticated")
            if request.method in {"GET", "HEAD"} and request.url.path == "/":
                return RedirectResponse("/auth/login", status_code=302)
            return JSONResponse({"detail": "Authentication required"}, status_code=401, headers={"Cache-Control": "no-store"})
        matched = self.match(read_groups(identity))
        if not matched:
            self.audit(request, identity["email"], "deny", "group_not_allowed")
            return JSONResponse({"detail": "Access denied: AD group membership required"}, status_code=403, headers={"Cache-Control": "no-store"})
        request.state.user = identity
        self.audit(request, identity["email"], "allow", "group_allowed", matched)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    async def login(self, request: Request):
        request.session.clear()
        response = await self.client.authorize_redirect(request, self.settings.redirect_uri)
        response.headers["Cache-Control"] = "no-store"
        return response

    async def callback(self, request: Request):
        try:
            token = await self.client.authorize_access_token(request)
            identity = await self.identity(token)
        except Exception:
            # Never log authorization codes, credentials, or complete tokens.
            self.audit(request, None, "deny", "authentication_failed")
            response = JSONResponse({"detail": "Authentication failed"}, status_code=401)
        else:
            matched = self.match(identity["groups"])
            if not matched:
                self.audit(request, identity["email"], "deny", "group_not_allowed")
                response = JSONResponse({"detail": "Access denied: AD group membership required"}, status_code=403)
            else:
                now = int(time.time())
                exp = min(now + self.settings.session_seconds, int(identity["exp"]))
                if exp <= now:
                    raise HTTPException(401, "Authentication expired")
                session = jwt.encode({
                    "sub": identity["sub"], "email": identity["email"], "groups": matched,
                    "iss": self.cookie_issuer, "aud": self.cookie_audience, "iat": now, "exp": exp,
                }, self.settings.session_secret, algorithm="HS256")
                response = RedirectResponse("/", status_code=302)
                response.set_cookie(self.cookie_name, session, max_age=exp-now, secure=True, httponly=True, samesite="lax", path="/")
                self.audit(request, identity["email"], "allow", "login_allowed", matched)
        request.session.clear()
        if response.status_code != 302:
            response.delete_cookie(self.cookie_name, path="/", secure=True, httponly=True, samesite="lax")
        response.headers["Cache-Control"] = "no-store"
        return response


def install_access_control(app, settings=None):
    settings = settings or AuthSettings.from_env()
    app.state.auth_settings = settings
    if not settings.enabled:
        return
    settings.validate()
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, CallbackLogFilter) for item in access_logger.filters):
        access_logger.addFilter(CallbackLogFilter())
    access = AccessControl(settings)
    app.state.access_control = access
    app.middleware("http")(access.guard)
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, session_cookie="pa_caddie_oauth",
                       max_age=600, same_site="lax", https_only=True)
    app.add_api_route("/auth/login", access.login, methods=["GET"], include_in_schema=False)
    app.add_api_route("/auth/callback", access.callback, methods=["GET"], include_in_schema=False)
