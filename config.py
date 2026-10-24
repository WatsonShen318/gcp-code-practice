import os
import logging
from google.cloud import secretmanager as _sm
from google.api_core.exceptions import NotFound

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger(__name__)


def _fetch_secret(project_id: str, secret_name: str) -> str:
    _log.info("[SecretManager] Fetching secret '%s' from project '%s'", secret_name, project_id)
    try:
        client = _sm.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        resp = client.access_secret_version(request={"name": name})
        value = resp.payload.data.decode("utf-8")
        _log.info("[SecretManager] Successfully fetched secret '%s'", secret_name)
        return value
    except NotFound:
        _log.warning("[SecretManager] Secret '%s' not found or has no versions, using empty string", secret_name)
        return ""
    except Exception as e:
        _log.error("[SecretManager] Failed to fetch secret '%s': %s", secret_name, e)
        raise


# SSO-related configurations (constants that don't change per environment)
SSO_CONFIG = {
    "auth_url": "https://authsvc-dev.cvshealth.com/as/authorization.oauth2",
    "token_endpoint": "https://authsvc-dev.cvshealth.com/as/token.oauth2",
    "userinfo_endpoint": "https://authsvc-dev.cvshealth.com/idp/userinfo.openid",
    # client credentials are set per-environment below
    "sso_client_id": None,
    "sso_client_secret": None,
    "scope": "openid profile email",
    "grant_type": "authorization_code",
    "sso_cookie_key": "sage-cookie",
    "shared_secret_key": "sage-cookie",
    "token_expiration_time": 86400#, #set to 24 hours as the expiration timestamp
    #"PERMITTED_GROUPS": {"dialsmart-genai-users"} # Groups allowed to access the service
}

# Per-environment SSO endpoints. prod uses the production authsvc; all others use UAT.
SSO_ENDPOINTS_BY_ENV = {
    "prod": {
        "auth_url": "https://authsvc.cvshealth.com/as/authorization.oauth2",
        "token_endpoint": "https://authsvc.cvshealth.com/as/token.oauth2",
        "userinfo_endpoint": "https://authsvc.cvshealth.com/idp/userinfo.openid",
    },
}

# Per-environment SSO client IDs (not secret — safe to keep here).
SSO_CLIENT_IDS_BY_ENV = {
    "pdev": "sso-sage-dev",
    "pss-test": "Sageuinp",
    "prod": "sso-sage-prod",
    "local": "sso-sage-dev",
}

# Secret Manager secret name per environment.
SSO_SECRET_NAME_BY_ENV = {
    "pdev": "spcltyeng-generic-sso-prod",
    "pss-test": "spcltyeng-sso-generic-pss-test",
    "prod": "spcltyeng-generic-sso-prod",
}

# Determine active environment name (uses ENV_NAME which is used throughout the app).
# Default to `prod` to match app defaults when not set.
ENV_NAME = os.environ.get("ENV_NAME", "prod")

SSO_CONFIG["sso_client_id"] = SSO_CLIENT_IDS_BY_ENV.get(ENV_NAME, SSO_CLIENT_IDS_BY_ENV["prod"])

# GCP project where SSO secrets live per environment.
_SM_PROJECT_BY_ENV = {
    "pdev": "edp-prod-restrict-spcltyeng",
    "pss-test": "anbc-test-spcltopz",   # update if different
    "prod": "edp-prod-restrict-spcltyeng",   # update if different
}
#test
if ENV_NAME == "local":
    # For local dev: set SSO_CLIENT_SECRET env var to avoid needing Secret Manager access.
    SSO_CONFIG["sso_client_secret"] = os.environ.get("SSO_CLIENT_SECRET", "")
elif ENV_NAME == "prod":
#     # TODO: Temporary hardcoded SSO client secret for prod. Move back to Secret Manager ASAP.
#     SSO_CONFIG["sso_client_secret"] = "MMmI9l5b4kS3JjAGZGZ40QKgGDfohsTA"
# else:
    _project_id = _SM_PROJECT_BY_ENV.get(ENV_NAME, _SM_PROJECT_BY_ENV["prod"])
    _secret_name = SSO_SECRET_NAME_BY_ENV.get(ENV_NAME, SSO_SECRET_NAME_BY_ENV["prod"])
    SSO_CONFIG["sso_client_secret"] = _fetch_secret(_project_id, _secret_name)

endpoints = SSO_ENDPOINTS_BY_ENV.get(ENV_NAME)
if endpoints:
    SSO_CONFIG.update(endpoints)

# Environment-specific configurations
ENV_CONFIG = {
    "pdev": {
        "redirect_token": "https://spcltyeng-sso-generic.prod.cvshealth.com/token",
        "domain": ".prod.cvshealth.com",
        "PROJECT_ID": "edp-prod-restrict-spcltyeng"
    },
    "prod": {
        "redirect_token": "https://spcltyeng-sso-generic.prod.cvshealth.com/token",
        "domain": ".prod.cvshealth.com",
        "PROJECT_ID": "edp-prod-restrict-spcltyeng"
    },
    "pss-test": {
        "redirect_token": "https://spcltyeng-sso-generic.pss-test.cvshealth.com/token",
        "domain": ".pss-test.cvshealth.com",
        "PROJECT_ID": "anbc-pss-test"
    },
    "local": {
        "redirect_token": "http://localhost:8080/token",
        "domain": "localhost",
        "PROJECT_ID": "edp-prod-restrict-spcltyeng"
    }
}

# Spanner configurations (shared across environments)
SPANNER_CONFIG = {
    "SPANNER_INSTANCE_ID": "spclt-anthm-prod",
    "SPANNER_DATABASE_ID": "dialsmart"
}

# Cloud SQL (PostgreSQL) configurations (shared across environments).
# Credentials are pulled from environment variables where possible; the DB
# password is stored in Secret Manager under the secret name below.
POSTGRES_CONFIG = {
    "POSTGRES_INSTANCE": "spclteng-db-prod",
    "POSTGRES_HOST": os.environ.get("POSTGRES_HOST", "10.157.181.99"),
    "POSTGRES_PORT": os.environ.get("POSTGRES_PORT", "5432"),
    "POSTGRES_USER": os.environ.get("POSTGRES_USER", "postgres"),
    "POSTGRES_DB": os.environ.get("POSTGRES_DB", "spclteng_db_prod"),
    "POSTGRES_PASSWORD_SECRET": "spclteng-db-prod",
}

# Active Directory groups used by this service. Keep as canonical names used in SSO/group claims.
AD_GROUPS = {
    "SAGE-Agent-Users",
    "QBR-Agent-Users",
    "SAGE-Admin-Users",
    "QBR-Agnt-Users",
    "genai-trend-analytics-restricted-rebates-access",
    "genai-trend-analytics-unrestricted-nonrebate-access",
    "genai-trend-analytics-nonrebate-access",
    "cust-form-genai-access", #CFC AD Group
    "genai-pa-analytics-access",
    "spclt-temp",
    "sage-patient",
    "sage-clinical",
    "sage-ops",
    "sage-patient-claude",
    "sage-patient-cache",
    "MIAH_corp_users",
    "MIAH_cvs_users",
    "MIAH_cmk_users",
    "MIAH_aet_users",
    "iss-prescriberlink-admin",
    "spclteng-crr-dashboard-access",
    "presc-sales-agnt-sandbox",
    "sage-pbm-agent",
    "umca-nrbts-access",
}

# Map AD group -> logical use-case/type. This makes group-based routing/authorization clearer.
AD_GROUP_TO_USECASE = {
    "SAGE-Agent-Users": "SAGE-Common",
    "SAGE-Admin-Users": "SAGE-Admin",
    "QBR-Agent-Users": "QBR",
    "QBR-Agnt-Users": "QBR",
    "genai-trend-analytics-restricted-rebates-access": "Trend",
    "genai-trend-analytics-unrestricted-nonrebate-access": "Trend",
    "genai-trend-analytics-nonrebate-access": "Trend",
    "cust-form-genai-access": "CFC", #CFC AD Group
    "genai-pa-analytics-access": "UM-PA",
    "spclt-temp": "CVS-Template",
    "sage-patient": "SAGE-Common",
    "sage-clinical": "SAGE-Common",
    "sage-ops": "SAGE-Common",
    "sage-patient-claude": "SAGE-Common",
    "sage-patient-cache": "SAGE-Common",
    "MIAH_corp_users": "MIAH",
    "MIAH_cvs_users": "MIAH",
    "MIAH_cmk_users": "MIAH",
    "MIAH_aet_users": "MIAH",
    "iss-prescriberlink-admin": "prescriberlink",
    "spclteng-crr-dashboard-access": "crr-dashboard",
    "presc-sales-agnt-sandbox": "presc-sales-agent",
    "sage-pbm-agent": "pbm-mail-analyzer",
    "umca-nrbts-access": "um-criteria-analyzer",
}

# Derived convenience sets for use-case membership checks
AD_GROUPS_BY_USECASE = {}
for grp, usecase in AD_GROUP_TO_USECASE.items():
    AD_GROUPS_BY_USECASE.setdefault(usecase, set()).add(grp)

# Prefix-based (wildcard) group matching -> logical use-case/type.
# Mirrors the SSO server group filter which releases wildcards like SAGE*, sage*, MIAH*, miah*.
# Any group whose name STARTS WITH one of these prefixes (case-insensitive) maps to the
# given use-case, so new groups don't need to be added explicitly above.
AD_GROUP_PREFIX_TO_USECASE = {
    "sage": "SAGE-Common",   # covers SAGE* and sage*
    "miah": "MIAH",          # covers MIAH* and miah*
    "umca": "um-criteria-analyzer",  # covers umca* (e.g. umca-nrbts-access)
}


def get_usecases_for_group(group_name):
    """Return the set of use-cases a single group grants, via exact match then prefix match.

    Exact matches in AD_GROUP_TO_USECASE take precedence. If no exact match, the group
    name is checked (case-insensitively) against AD_GROUP_PREFIX_TO_USECASE prefixes.
    """
    usecases = set()
    if not group_name:
        return usecases
    # Exact match first
    exact = AD_GROUP_TO_USECASE.get(group_name)
    if exact:
        usecases.add(exact)
    # Prefix (wildcard) match
    lowered = group_name.lower()
    for prefix, usecase in AD_GROUP_PREFIX_TO_USECASE.items():
        if lowered.startswith(prefix):
            usecases.add(usecase)
    return usecases


def user_has_usecase_access(user_groups, use_case):
    """True if any of the user's groups grants access to use_case (exact or prefix match)."""
    for grp in user_groups:
        if use_case in get_usecases_for_group(grp):
            return True
    return False

# Use cases that require EXPLICIT access (no SAGE-Common fallback)
# Add any new use cases here that should have strict access control
STRICT_ACCESS_USECASES = {
    "QBR",
    "Trend",
    "CFC", #CFC Use Case
    "MIAH",  # Require explicit AD-group membership for MIAH use case
    "UM-PA",  # Require explicit AD-group membership for UM-PA use case
    "prescriberlink",  # Require explicit AD-group membership for prescriberlink use case
    "crr-dashboard",  # Require explicit AD-group membership for CRR dashboard use case
    "presc-sales-agent",  # Require explicit AD-group membership (presc-sales-agnt-sandbox)
    "pbm-mail-analyzer",  # Require explicit AD-group membership (sage-pbm-agent)
    "um-criteria-analyzer",  # Require explicit AD-group membership (umca-nrbts-access)
    # Add future strict-access use cases here
    # "NewUseCase",
}

# Use case to cookie domain mapping (for cross-domain use cases)
# Use cases not listed here will use the default domain from ENV_CONFIG
USE_CASE_COOKIE_DOMAINS = {
    "Trend": {
        "pdev": ".cvshealth.com",
        "pss-test": ".cvshealth.com",
        "prod": ".cvshealth.com",
        "local": "localhost"
    },
    "CFC": { #CFC Use Case
        "pdev": ".cvshealth.com",
        "pss-test": ".cvshealth.com",
        "prod": ".cvshealth.com",
        "local": "localhost"
    },
    "MIAH": {
        "pdev": ".cvshealth.com",
        "pss-test": ".cvshealth.com",
        "prod": ".cvshealth.com",
        "local": "localhost"
    },
    "UM-PA": {
        "pdev": ".cvshealth.com",
        "pss-test": ".cvshealth.com",
        "prod": ".cvshealth.com",
        "local": "localhost"
    },
    "prescriberlink": {
        "pdev": ".cvshealth.com",
        "pss-test": ".cvshealth.com",
        "prod": ".cvshealth.com",
        "local": "localhost"
    },
    "um-criteria-analyzer": {
        "pdev": ".cvshealth.com",
        "pss-test": ".cvshealth.com",
        "prod": ".cvshealth.com",
        "local": "localhost"
    },
    # "FutureUseCase": {
    #     "prod": ".custom-domain.cvshealth.com",
    #     ...
    # }
}

# Use case URL mappings (per use case and environment)
USE_CASE_URLS = {
    "digital": {
        "pdev": "https://spcltyeng-digital-analyzer-agent-fe.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-digital-analyzer-agent-fe.pss-test.cvshealth.com/",
        "prod": "https://spcltyeng-digital-analyzer-agent-fe.prod.cvshealth.com/",
        "local": "http://localhost:3001/"
    },
    "vol-trend": {
        "pdev": "https://spcltyeng-vol-trend-analyzer-fe.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-vol-trend-analyzer-fe.pss-test.cvshealth.com/",
        "prod": "https://spcltyeng-vol-trend-analyzer-fe.prod.cvshealth.com/",
        "local": "http://localhost:3002/"
    },
    "QBR": {
        "pdev": "https://spcltyeng-qbr-adk-comp-agent-fe.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-qbr-adk-comp-agent-fe.pss-test.cvshealth.com/",
        "prod": "https://spcltyeng-qbr-adk-comp-agent-fe.prod.cvshealth.com/",
        "local": "http://localhost:3003/"
    },

    #Future use case can be added here
    #Make changes and perform Pull request for review and merging.
     #"Future": {
       # "prod": "https://spcltyeng-qbr-comp-agent-fe-test.prod.cvshealth.com/",
       # "pss-test": "https://spcltyeng-qbr-adk-comp-agent-fe.pss-test.cvshealth.com/",
        #"prod": "https://spcltyeng-qbr-adk-comp-agent-fe.prod.cvshealth.com/",
        #"local": "http://localhost:3003/"
    #},
    "SAGE-Common": {
        "pdev": "https://spcltyeng-sage-fe.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-sage-fe.pss-test.cvshealth.com/",
        "prod": "https://spcltyeng-sage-fe.prod.cvshealth.com/",
        "local": "http://localhost:3004/"
    },
    "Trend": {
        "pdev": "https://um-trend-agent-fe.prod.cvshealth.com/",
        "pss-test": "https://um-trend-agent-fe.prod.cvshealth.com/",
        "prod": "https://um-trend-agent-fe.pprod.cvshealth.com/",
        "local": "http://localhost:3005/"
    },
    "CFC": {
        "pdev": "https://cust-form-cfc-agentic-ui-repo.dev.cvshealth.com/",
        "pss-test": "https://cust-form-cfc-agentic-ui-repo.test.cvshealth.com/",
        "prod": "https://cust-form-cfc-agentic-ui-repo.prod.cvshealth.com/",
        "local": "http://localhost:3006/"
    },
    "MIAH": {
        "pdev": "https://hea-miah-app-ui.prod.cvshealth.com/",
        "pss-test": "https://hea-miah-app-ui.prod.cvshealth.com/",
        "prod": "https://hea-miah-app-ui.pprod.cvshealth.com/",
        "local": "http://localhost:3007/"
    },
    "UM-PA": {
        "pdev": "https://dpes-de-um-pa-agent-ui.dev.cvshealth.com/",
        "pss-test": "https://dpes-de-um-pa-agent-ui.test.cvshealth.com/",
        "prod": "https://dpes-de-um-pa-agent-ui.prod.cvshealth.com/",
        "local": "http://localhost:3008/"
    },
    "spclt-tmplt": {
        "pdev": "https://spcltyeng-cvs-spclt-ui-template.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-cvs-spclt-ui-template.pss-test.cvshealth.com/",
        "prod": "https://spcltyeng-cvs-spclt-ui-template.prod.cvshealth.com/",
        "local": "http://localhost:3009/"
    },
    "gnrcs-ops": {
        "pdev": "https://spcltyeng-sage-gnrcs-ops-fe.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-sage-gnrcs-ops-fe.pss-test.cvshealth.com/",
        "prod": "https://spcltyeng-sage-gnrcs-ops-fe.prod.cvshealth.com/",
        "local": "http://localhost:3010/"
    },
    "sage-patient": {
        "pdev": "https://spcltyeng-sage-patient-agent-ui.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-sage-patient-agent-ui.pss-test.cvshealth.com/",
        "prod": "https://spcltyeng-sage-patient-agent-ui.prod.cvshealth.com/",
        "local": "http://localhost:3011/"
    },
    "sage-clinical": {
        "pdev": "https://spcltyeng-sage-clinical-agent-fe.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-sage-clinical-agent-fe.pss-test.cvshealth.com/",
        "prod": "https://spcltyeng-sage-clinical-agent-fe.prod.cvshealth.com/",
        "local": "http://localhost:3003/"
    },
    "sage-ops": {
        "pdev": "https://spcltyeng-sage-ops-agent-fe.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-sage-ops-agent-fe.pss-test.cvshealth.com/",
        "prod": "https://spcltyeng-sage-ops-agent-fe.prod.cvshealth.com/",
        "local": "http://localhost:3003/"
    },
    "sage-patient-cache": {
        "pdev": "https://spcltyeng-sage-patient-agent-ui-cache.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-sage-patient-agent-ui-cache.prod.cvshealth.com/",
        "prod": "https://spcltyeng-sage-patient-agent-ui-cache.prod.cvshealth.com/",
        "local": "http://localhost:3012/"
    },
    "adk-agents-monitoring-tool": {
        "pdev": "https://spcltyeng-adk-agents-monitoring-tool.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-adk-agents-monitoring-tool.pss-test.cvshealth.com/",
        "prod": "https://spcltyeng-adk-agents-monitoring-tool.prod.cvshealth.com/",
        "local": "http://localhost:3000/"
    },
    "gke-cost-advisor": {
        "pdev": "https://spcltyeng-gke-cost-advisor.prod.cvshealth.com/ui",
        "pss-test": "https://spcltyeng-gke-cost-advisor.pss-test.cvshealth.com/ui",
        "prod": "https://spcltyeng-gke-cost-advisor.prod.cvshealth.com/ui",
        "local": "http://localhost:8000/ui"
    },
    "sage-patient-claude": {
        "pdev": "https://spcltyeng-sage-patient-claude-agent-ui.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-sage-patient-claude-agent-ui.pss-test.cvshealth.com/",
        "prod": "https://spcltyeng-sage-patient-claude-agent-ui.prod.cvshealth.com/",
        "local": "http://localhost:3005/"
    },
    "claude-evalsuite-generic": {
        "pdev": "https://spcltyeng-claude-evalsuite-generic.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-claude-evalsuite-generic.pss-test.cvshealth.com/",
        "prod": "https://spcltyeng-claude-evalsuite-generic.prod.cvshealth.com/",
        "local": "http://localhost:8501/"
    },
    "adk-evalsuite": {
        "pdev": "https://spcltyeng-adk-evalsuite.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-adk-evalsuite.pss-test.cvshealth.com/",
        "prod": "https://spcltyeng-adk-evalsuite.prod.cvshealth.com/",
        "local": "http://localhost:8080/"
    },
    "omnigence": {
        "pdev": "https://spcltyeng-omnigence.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-omnigence.pss-test.cvshealth.com/",
        "prod": "https://spcltyeng-omnigence.prod.cvshealth.com/",
        "local": "http://localhost:8080/"
    },
    "prescriberlink": {
        "pdev": "https://pa-stars-plss-iss-prescriberlink.dev.cvshealth.com/",
        "pss-test": "https://pa-stars-plss-iss-prescriberlink.test.cvshealth.com/",
        "prod": "https://pa-stars-plss-iss-prescriberlink.prod.cvshealth.com/",
        "local": "http://localhost:3013/"
    },
    "crr-dashboard": {
        "pdev": "https://spcltyeng-crr-enhanced-services-dashboard.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-crr-enhanced-services-dashboard.pss-test.cvshealth.com/",
        "prod": "https://spcltyeng-crr-enhanced-services-dashboard.prod.cvshealth.com/",
        "local": "http://localhost:3014/"
    },
    "pulse-agent": {
        "pdev": "https://spcltyeng-sage-pulse-agent-fe.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-sage-pulse-agent-fe.pss-test.cvshealth.com/",
        "prod": "https://spcltyeng-sage-pulse-agent-fe.prod.cvshealth.com/",
        "local": "http://localhost:3015/"
    },
    "pbm-mail-analyzer": {
        "pdev": "https://spcltyeng-pbm-mail-analyzer-fe.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-pbm-mail-analyzer-fe.pss-test.cvshealth.com/",
        "prod": "https://spcltyeng-pbm-mail-analyzer-fe.prod.cvshealth.com/",
        "local": "http://localhost:3016/"
    },
    "presc-sales-agent": {
        "pdev": "https://spcltyeng-presc-sales-agent-fe.prod.cvshealth.com/",
        "pss-test": "https://spcltyeng-presc-sales-agent-fe.pss-test.cvshealth.com/",
        "prod": "https://spcltyeng-presc-sales-agent-fe.prod.cvshealth.com/",
        "local": "http://localhost:3017/"
    },
    "um-criteria-analyzer": {
        "pdev": "https://um-criteria-analyzer.prod.cvshealth.com/",
        "pss-test": "https://um-criteria-analyzer.pss-test.cvshealth.com/",
        "prod": "https://um-criteria-analyzer.pprod.cvshealth.com/",
        "local": "http://localhost:3018/"
    }
}

#dummy commit 

# CORS origins # To resolve CORS issues during  development and testing
ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://localhost:3003",
    "http://localhost:3004",
    "https://spcltyeng-digital-analyzer-agent-fe.prod.cvshealth.com",
    "https://spcltyeng-vol-trend-analyzer-fe.prod.cvshealth.com",
    "https://spcltyeng-qbr-adk-comp-agent-fe.prod.cvshealth.com",
    "https://spcltyeng-sage-fe.prod.cvshealth.com",
    "https://cust-form-cfc-agentic-ui-repo.dev.cvshealth.com",
    "https://cust-form-cfc-agentic-ui-repo.test.cvshealth.com",
    "https://cust-form-cfc-agentic-ui-repo.prod.cvshealth.com",
    "https://spcltyeng-sage-patient-agent-ui.prod.cvshealth.com",
    "https://spcltyeng-sage-patient-agent-ui.pss-test.cvshealth.com",
    "https://spcltyeng-sage-patient-agent-ui.prod.cvshealth.com",
    "https://spcltyeng-sage-patient-agent-ui-cache.prod.cvshealth.com",
    "https://spcltyeng-sage-patient-agent-ui-cache.pss-test.cvshealth.com",
    "https://spcltyeng-sage-patient-agent-ui-cache.prod.cvshealth.com",
    "https://spcltyeng-sage-clinical-agent-fe.prod.cvshealth.com",
    "https://spcltyeng-sage-clinical-agent-fe.pss-test.cvshealth.com",
    "https://spcltyeng-sage-clinical-agent-fe.prod.cvshealth.com",
    "https://spcltyeng-adk-agents-monitoring-tool.prod.cvshealth.com",
    "https://spcltyeng-adk-agents-monitoring-tool.pss-test.cvshealth.com",
    "https://spcltyeng-adk-agents-monitoring-tool.prod.cvshealth.com",
    "https://spcltyeng-gke-cost-advisor.prod.cvshealth.com",
    "https://spcltyeng-gke-cost-advisor.pss-test.cvshealth.com",
    "https://spcltyeng-gke-cost-advisor.prod.cvshealth.com",
    "https://spcltyeng-sage-patient-claude-agent-ui.prod.cvshealth.com",
    "https://spcltyeng-sage-patient-claude-agent-ui.pss-test.cvshealth.com",
    "https://spcltyeng-sage-patient-claude-agent-ui.prod.cvshealth.com",
    "https://spcltyeng-claude-evalsuite-generic.prod.cvshealth.com",
    "https://spcltyeng-claude-evalsuite-generic.pss-test.cvshealth.com",
    "https://spcltyeng-claude-evalsuite-generic.prod.cvshealth.com",
    "https://spcltyeng-adk-evalsuite.prod.cvshealth.com",
    "https://spcltyeng-adk-evalsuite.pss-test.cvshealth.com",
    "https://spcltyeng-adk-evalsuite.prod.cvshealth.com",
    "https://spcltyeng-omnigence.prod.cvshealth.com",
    "https://spcltyeng-omnigence.pss-test.cvshealth.com",
    "https://spcltyeng-omnigence.prod.cvshealth.com",
    "https://spcltyeng-sage-ops-agent-fe.prod.cvshealth.com",
    "https://spcltyeng-sage-ops-agent-fe.pss-test.cvshealth.com",
    "https://spcltyeng-sage-ops-agent-fe.prod.cvshealth.com",
]

# MIAH CORS origins
ORIGINS.extend([
    "https://hea-miah-app-ui.prod.cvshealth.com",
    "https://hea-miah-app-ui.pprod.cvshealth.com",
])

# Trend CORS origins
ORIGINS.extend([
    "https://um-trend-agent-fe.prod.cvshealth.com",
    "https://um-trend-agent-fe.pprod.cvshealth.com",
])

# prescriberlink CORS origins
ORIGINS.extend([
    "https://pa-stars-plss-iss-prescriberlink.dev.cvshealth.com",
    "https://pa-stars-plss-iss-prescriberlink.test.cvshealth.com",
    "https://pa-stars-plss-iss-prescriberlink.prod.cvshealth.com",
])

# CRR dashboard CORS origins
ORIGINS.extend([
    "https://spcltyeng-crr-enhanced-services-dashboard.prod.cvshealth.com",
    "https://spcltyeng-crr-enhanced-services-dashboard.pss-test.cvshealth.com",
    "https://spcltyeng-crr-enhanced-services-dashboard.prod.cvshealth.com",
])

# Pulse Agent CORS origins
ORIGINS.extend([
    "https://spcltyeng-sage-pulse-agent-fe.prod.cvshealth.com",
    "https://spcltyeng-sage-pulse-agent-fe.pss-test.cvshealth.com",
    "https://spcltyeng-sage-pulse-agent-fe.prod.cvshealth.com",
])

# PBM Mail Analyzer CORS origins
ORIGINS.extend([
    "https://spcltyeng-pbm-mail-analyzer-fe.prod.cvshealth.com",
    "https://spcltyeng-pbm-mail-analyzer-fe.pss-test.cvshealth.com",
    "https://spcltyeng-pbm-mail-analyzer-fe.prod.cvshealth.com",
])

# Presc Sales Agent CORS origins
ORIGINS.extend([
    "https://spcltyeng-presc-sales-agent-fe.prod.cvshealth.com",
    "https://spcltyeng-presc-sales-agent-fe.pss-test.cvshealth.com",
    "https://spcltyeng-presc-sales-agent-fe.prod.cvshealth.com",
])

# UM Criteria Analyzer CORS origins
ORIGINS.extend([
    "https://um-criteria-analyzer.prod.cvshealth.com",
    "https://um-criteria-analyzer.pss-test.cvshealth.com",
    "https://um-criteria-analyzer.pprod.cvshealth.com",
])

# Default support/contact information used in error messages.
# Update these values or map per-use-case in `USE_CASE_CONTACTS`.
DEFAULT_SUPPORT_CONTACT = "kathiresanm@aetna.com,Vignesh.Shankar@CVSHealth.com"
CFC_SUPPORT_CONTACT = "NagaLakshmiSharma.Vaddi@CVSHealth.com,gmcooper@aetna.com"
TREND_SUPPORT_CONTACT = "NagaLakshmiSharma.Vaddi@CVSHealth.com,FarazmandF@aetna.com"
MIAH_SUPPORT_CONTACT = "GuntupalliA@aetna.com,MohammedHannan.Desai@CVSHealth.com"
PRESCRIBERLINK_SUPPORT_CONTACT = "GuntupalliA@aetna.com,Karveandhan.Palanisamy@CVSHealth.com"
UMCA_SUPPORT_CONTACT = "nagalakshmisharma.vaddi@cvshealth.com,LathikaShukaram.Amin@CVSHealth.com"


USE_CASE_CONTACTS = {
    "digital": DEFAULT_SUPPORT_CONTACT,
    "vol-trend": DEFAULT_SUPPORT_CONTACT,
    "QBR": DEFAULT_SUPPORT_CONTACT,
    "SAGE-Common": DEFAULT_SUPPORT_CONTACT,
    "Trend": TREND_SUPPORT_CONTACT,
    "CFC": CFC_SUPPORT_CONTACT,
    "MIAH": MIAH_SUPPORT_CONTACT,
    "UM-PA": TREND_SUPPORT_CONTACT,
    "prescriberlink": PRESCRIBERLINK_SUPPORT_CONTACT,
    "crr-dashboard": DEFAULT_SUPPORT_CONTACT,
    "pulse-agent": DEFAULT_SUPPORT_CONTACT,
    "pbm-mail-analyzer": DEFAULT_SUPPORT_CONTACT,
    "presc-sales-agent": DEFAULT_SUPPORT_CONTACT,
    "adk-agents-monitoring-tool": DEFAULT_SUPPORT_CONTACT,
    "gke-cost-advisor": DEFAULT_SUPPORT_CONTACT,
    "claude-evalsuite-generic": DEFAULT_SUPPORT_CONTACT,
    "adk-evalsuite": DEFAULT_SUPPORT_CONTACT,
    "omnigence": DEFAULT_SUPPORT_CONTACT,
    "um-criteria-analyzer": UMCA_SUPPORT_CONTACT,
}
