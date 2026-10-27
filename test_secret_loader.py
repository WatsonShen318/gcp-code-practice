import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ping_auth import PingSettings
from secret_loader import load_client_secret, read_client_secret


class SecretLoaderTest(unittest.TestCase):
    def mock_manager(self, payload):
        manager = MagicMock()
        manager.__enter__.return_value = manager
        manager.access_secret_version.return_value = SimpleNamespace(
            payload=SimpleNamespace(data=json.dumps(payload).encode()))
        return manager

    def test_reference_secret_and_client_are_loaded_without_manual_secrets(self):
        manager = self.mock_manager({"sso_client_secret": " mock-only-secret-value "})
        credentials = object()
        with patch.dict("os.environ", {"AUTH_ENABLED": "true", "REDIRECT_URI": "https://app.example/token"}, clear=True), \
                patch("google.auth.default", return_value=(credentials, "another-compute-project")), \
                patch("google.cloud.secretmanager.SecretManagerServiceClient", return_value=manager) as constructor:
            with self.assertLogs("uvicorn.error", level="INFO") as logs:
                settings = PingSettings.from_env()
            settings.validate()
        self.assertEqual(settings.client_id, "APM0015442")
        self.assertEqual(settings.client_secret, "mock-only-secret-value")
        self.assertEqual(len(settings.session_secret), 64)
        constructor.assert_called_once_with(credentials=credentials)
        manager.access_secret_version.assert_called_once_with(
            request={"name": "projects/edp-pdev-restrict-paops/secrets/paops-streamlit-pdev/versions/latest"},
            timeout=10, retry=None)
        self.assertNotIn("mock-only-secret-value", "\n".join(logs.output))

    def test_secret_resource_can_be_overridden(self):
        manager = self.mock_manager({"sso_client_secret": "mock-only-secret"})
        with patch.dict("os.environ", {"GCP_PROJECT_ID": "example-project", "SECRET_ID": "example-secret", "SECRET_VERSION": "2"}, clear=True), \
                patch("google.auth.default", return_value=(object(), None)), \
                patch("google.cloud.secretmanager.SecretManagerServiceClient", return_value=manager):
            self.assertEqual(read_client_secret(), "mock-only-secret")
        self.assertEqual(manager.access_secret_version.call_args.kwargs["request"]["name"],
                         "projects/example-project/secrets/example-secret/versions/2")

    def test_local_auth_disabled_never_fetches_secret(self):
        with patch.dict("os.environ", {}, clear=True), patch("ping_auth.load_client_secret") as loader:
            settings = PingSettings.from_env()
        self.assertFalse(settings.enabled)
        loader.assert_not_called()

    def test_skip_secret_manager_uses_injected_secret(self):
        with patch.dict("os.environ", {"USE_SECRET_MANAGER": "0"}, clear=True), patch("secret_loader.read_client_secret") as reader:
            self.assertEqual(load_client_secret("mock-only-env-secret"), "mock-only-env-secret")
        reader.assert_not_called()

    def test_manager_failure_can_fall_back_to_existing_environment(self):
        with patch.dict("os.environ", {}, clear=True), patch("secret_loader.read_client_secret", side_effect=RuntimeError("do-not-log-response")):
            with self.assertLogs("uvicorn.error", level="WARNING") as logs:
                self.assertEqual(load_client_secret("mock-only-fallback"), "mock-only-fallback")
            self.assertNotIn("do-not-log-response", "\n".join(logs.output))
            self.assertNotIn("mock-only-fallback", "\n".join(logs.output))
            with self.assertRaisesRegex(ValueError, "Cannot load Ping credential"):
                load_client_secret()

    def test_missing_or_invalid_secret_json_is_not_accepted(self):
        for payload in ({}, {"sso_client_secret": ""}, {"sso_client_secret": 123}, []):
            manager = self.mock_manager(payload)
            with patch.dict("os.environ", {}, clear=True), \
                    patch("google.auth.default", return_value=(object(), None)), \
                    patch("google.cloud.secretmanager.SecretManagerServiceClient", return_value=manager):
                with self.assertRaisesRegex(ValueError, "nonempty sso_client_secret"):
                    read_client_secret()

    def test_session_key_is_stable_per_app_and_overrideable(self):
        environment = {"AUTH_ENABLED": "true", "USE_SECRET_MANAGER": "0", "SSO_CLIENT_SECRET": "mock-only-secret",
                       "REDIRECT_URI": "https://app.example/token"}
        with patch.dict("os.environ", environment, clear=True):
            first, second = PingSettings.from_env(), PingSettings.from_env()
            self.assertEqual(first.session_secret, second.session_secret)
            with patch.dict("os.environ", {"REDIRECT_URI": "https://another-app.example/token"}):
                self.assertNotEqual(first.session_secret, PingSettings.from_env().session_secret)
            with patch.dict("os.environ", {"SHARED_SECRET_KEY": "mock-only-explicit-key-at-least-32-characters"}):
                self.assertEqual(PingSettings.from_env().session_secret, "mock-only-explicit-key-at-least-32-characters")
