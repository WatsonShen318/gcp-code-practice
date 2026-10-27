"""Load the same Ping credential JSON as the supplied PA Pulse repository."""

import json
import logging
import os
import re

logger = logging.getLogger("uvicorn.error")
DEFAULT_PROJECT = "edp-pdev-restrict-paops"
DEFAULT_SECRET = "paops-streamlit-pdev"


def read_client_secret():
    # Lazy imports keep local page development and image import checks offline.
    import google.auth
    from google.cloud import secretmanager

    project = os.getenv("GCP_PROJECT_ID") or DEFAULT_PROJECT
    secret_id = os.getenv("SECRET_ID") or DEFAULT_SECRET
    version = os.getenv("SECRET_VERSION") or "latest"
    if not all(re.fullmatch(r"[A-Za-z0-9_-]+", value) for value in (project, secret_id, version)):
        raise ValueError("Invalid Secret Manager resource configuration")
    resource = f"projects/{project}/secrets/{secret_id}/versions/{version}"
    credentials, _ = google.auth.default()
    with secretmanager.SecretManagerServiceClient(credentials=credentials) as client:
        response = client.access_secret_version(request={"name": resource}, timeout=10, retry=None)
    payload = json.loads(response.payload.data.decode("utf-8"))
    value = payload.get("sso_client_secret") if isinstance(payload, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Secret JSON must contain a nonempty sso_client_secret string")
    logger.info("Ping credential loaded from Secret Manager: %s", resource)
    return value.strip()


def load_client_secret(fallback=""):
    enabled = os.getenv("USE_SECRET_MANAGER", "1")
    if enabled not in {"0", "1"}:
        raise ValueError("USE_SECRET_MANAGER must be 0 or 1")
    if enabled == "0":
        return fallback
    try:
        return read_client_secret()
    except Exception as error:
        # As in the reference: an explicitly injected credential can be a fallback.
        # Never include SDK response bodies or secret contents in logs/errors.
        if fallback:
            logger.warning("Secret Manager unavailable (%s); using injected Ping credential", type(error).__name__)
            return fallback
        raise ValueError("Cannot load Ping credential from Secret Manager (" + type(error).__name__ +
                         "); verify GCP_PROJECT_ID, SECRET_ID and the Pod's existing secret access") from None
