'''
Generic SSO Version - FastAPI application that implements a Single Sign-On (SSO) authentication flow using OAuth 2.0
Author: Mareeswaran Kathiresan
Updated: Dec-23-2025

Endpoints Summary:
#1. /health - Health check endpoint
#2.1. /sso-authenticate - SAGE Specific Entry point for any application wanting SSO authentication
#2.2 /sso-service - SSO  Generic service endpoint for any team to use SSO as Service - (NON SAGE End point)
#3. /login - Redirects users to SSO authentication URL
#4. /token - Exchanges authorization code for user metadata, validates use case, and redirects
#5. /user_info - Returns logged-in user's information from JWT cookie
#6. /refresh_cookie - Refreshes the JWT cookie expiration
#7. /add-active-user - Adds an active user entry into the sage_users table in Spanner
#8. /deactivate-user - Deactivates a user entry in the sage_users table in Spanner
#9. /create-sage-users-table - Creates the sage_users table in Spanner (setup endpoint)

'''



import base64
import html
import json
import os
import secrets
import requests
import jwt
import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Response, Request, Query
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, BaseLoader
from pathlib import Path
from datetime import datetime, timezone, timedelta
from google.cloud import spanner
import time
from .config import (
    SSO_CONFIG,
    ENV_CONFIG,
    SPANNER_CONFIG,
    USE_CASE_URLS,
    ORIGINS,
    STRICT_ACCESS_USECASES,
    USE_CASE_COOKIE_DOMAINS,
    USE_CASE_CONTACTS,
    DEFAULT_SUPPORT_CONTACT,
    AD_GROUPS,
    user_has_usecase_access,
)

GCP_ENV = os.environ.get("ENV_NAME")
print(f"GCP_ENV is : {GCP_ENV}")

# Load environment-specific config (default to prod if not set)
env_config = ENV_CONFIG.get(GCP_ENV, ENV_CONFIG["prod"])

# Set variables from configs
auth_url = SSO_CONFIG["auth_url"]
token_endpoint = SSO_CONFIG["token_endpoint"]
userinfo_endpoint = SSO_CONFIG["userinfo_endpoint"]
sso_client_id = SSO_CONFIG["sso_client_id"]
sso_client_secret = SSO_CONFIG["sso_client_secret"]
redirect_token = env_config["redirect_token"]
domain = env_config["domain"]
scope = SSO_CONFIG["scope"]
grant_type = SSO_CONFIG["grant_type"]
sso_cookie_key = SSO_CONFIG["sso_cookie_key"]
shared_secret_key = SSO_CONFIG["shared_secret_key"]
token_expiration_time = SSO_CONFIG["token_expiration_time"]
#PERMITTED_GROUPS = SSO_CONFIG["PERMITTED_GROUPS"] #Not used currently

# Spanner configuration
PROJECT_ID = env_config["PROJECT_ID"]
SPANNER_INSTANCE_ID = SPANNER_CONFIG["SPANNER_INSTANCE_ID"]
SPANNER_DATABASE_ID = SPANNER_CONFIG["SPANNER_DATABASE_ID"]

print(f"Configuration loaded. Project: {PROJECT_ID}, Spanner Instance: {SPANNER_INSTANCE_ID}, Database: {SPANNER_DATABASE_ID}")
print(f"SSO auth_url: {auth_url}")
print(f"SSO token_endpoint: {token_endpoint}")
print(f"SSO userinfo_endpoint: {userinfo_endpoint}")
print(f"SSO client_id: {sso_client_id}")
print(f"SSO redirect_token: {redirect_token}")
print(f"SSO scope: {scope}")
print(f"SSO grant_type: {grant_type}")
print(f"SSO cookie key: {sso_cookie_key}")
print(f"Shared secret key: {'*' * len(shared_secret_key)}")  # Do not print the actual secret, just indicate it's set
print(f"Token expiration time (seconds): {token_expiration_time}")
print(f"SSO Client secrent: {sso_client_secret[:4]}... (hidden for security)")
# Spanner client initialization
def get_spanner_client():
    """Initialize Spanner client"""
    try:
        print(f"Initializing Spanner client for project: {PROJECT_ID}")
        spanner_client = spanner.Client(project=PROJECT_ID)
        instance = spanner_client.instance(SPANNER_INSTANCE_ID)
        database = instance.database(SPANNER_DATABASE_ID)
        print("Spanner client initialized successfully")
        return database
    except Exception as e:
        print(f"Error initializing Spanner client: {e}")
        raise
    




# Fetch user authorized use cases from Spanner
#used for Alntenative email based access validation (if any of the requestor manager is OOO)
def get_user_authorized_usecases(email: str, max_retries: int = 3) -> list:
    """
    Fetch all authorized use cases for a user from sage_users table
    
    Args:
        email: User's email address (will be converted to lowercase for matching)
        max_retries: Number of retry attempts for Spanner connection
        
    Returns:
        List of use case names the user has access to (empty list if user not found)
        
    Raises:
        HTTPException(500): If Spanner query fails after retries
        
    Note:
        Returns empty list [] if user not found - this is intentional to allow
        AD group-based access as a fallback mechanism.
    """
    retry_count = 0
    last_error = None
    
    # Convert email to lowercase for case-insensitive matching
    email_lower = email.lower()
    print(f"Email converted to lowercase: {email_lower}")
    
    while retry_count < max_retries:
        try:
            print(f"Fetching authorized use cases for email: {email_lower} (Attempt {retry_count + 1}/{max_retries})")
            
            database = get_spanner_client()
            
            # Query to get all active use cases for the user (case-insensitive email match)
            query = """
                SELECT usecase_name
                FROM sage_users
                WHERE LOWER(user_email_id) = @email
                AND Active_ind = TRUE
            """
            
            params = {"email": email_lower}
            param_types = {"email": spanner.param_types.STRING}
            
            with database.snapshot() as snapshot:
                results = snapshot.execute_sql(
                    query,
                    params=params,
                    param_types=param_types
                )
                
                # Extract use case names
                use_cases = [row[0] for row in results]
                
                # ✅ CHANGED: Return empty list instead of raising 404
                if not use_cases:
                    print(f"User {email_lower} not found in sage_users table - will check AD groups")
                else:
                    print(f"Found {len(use_cases)} authorized use cases for {email_lower}: {use_cases}")
                
                return use_cases
                
        except Exception as e:
            last_error = e
            retry_count += 1
            print(f"Error fetching use cases (attempt {retry_count}): {e}")
            
            if retry_count < max_retries:
                wait_time = 2 ** retry_count  # Exponential backoff: 2s, 4s, 8s
                print(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"Failed to fetch use cases after {max_retries} attempts")
                contact = DEFAULT_SUPPORT_CONTACT
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to validate user access after {max_retries} attempts. Please contact {contact}. Error: {str(last_error)}"
                )
    
    # Should never reach here due to raise in loop, but return empty list as fallback
    return []

# Helper functions
def make_token():
    """Generates a cryptographically secure, URL-safe string."""
    print("make_token fn is called")
    return secrets.token_urlsafe(16)

def sso_encoded_credentials():
    """Encodes client credentials for authorization."""
    print("sso_encoded_credentials is called")
    client_credentials = f"{sso_client_id}:{sso_client_secret}"
    encoded_secret = base64.b64encode(client_credentials.encode()).decode()
    print(f"encoded_secret is:{encoded_secret}")
    return encoded_secret

# Extract CN from LDAP DN string
def extract_group_name(dn_string):
    """Extract CN value from an LDAP Distinguished Name.

    Some SSO tokens deliver groups as full DNs (e.g. 'CN=SAGE-Agent-Users,OU=...'),
    while others deliver plain group names (e.g. 'SAGE-Agent-Users'). Handle both:
    return the CN component when present, otherwise return the plain value.
    """
    if not dn_string:
        return None
    parts = dn_string.split(',')
    for part in parts:
        part = part.strip()
        if part.upper().startswith('CN='):
            return part[3:]
    # Not a DN — it's already a plain group name
    return dn_string.strip()

# Initialize FastAPI app
app = FastAPI()

# Templates directory for HTML files (use project-relative absolute path)
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR_PATH = BASE_DIR / "templates"
TEMPLATES_DIR = str(TEMPLATES_DIR_PATH)
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Verify that required templates exist at startup so container/runtime issues are
# discovered early instead of at request time.
required_templates = ["disclaimer.html"]
missing = [t for t in required_templates if not (TEMPLATES_DIR_PATH / t).exists()]
if missing:
    missing_list = ", ".join(missing)
    raise RuntimeError(f"Missing required template(s) in {TEMPLATES_DIR}: {missing_list}")

# Serve static assets (logo, etc.) from the templates directory
app.mount("/static", StaticFiles(directory=TEMPLATES_DIR), name="static")

# Jinja2 environment with autoescape for rendering inline HTML safely
_jinja_env = Environment(loader=BaseLoader(), autoescape=True)

AUTH_SUCCESS_TEMPLATE = _jinja_env.from_string("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Authentication Successful</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: #f8f9fa;
            margin: 0;
            padding: 20px;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            color: #212529;
        }
        .container {
            background: #ffffff;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            padding: 40px;
            max-width: 700px;
            width: 100%;
            text-align: center;
        }
        h1 {
            color: #007bff;
            margin-bottom: 10px;
            font-size: 28px;
        }
        .subtitle {
            color: #6c757d;
            margin-bottom: 30px;
            font-size: 16px;
        }
        .section {
            margin-bottom: 30px;
            text-align: left;
        }
        .section h2 {
            border-bottom: 1px solid #dee2e6;
            padding-bottom: 8px;
            color: #495057;
            font-size: 20px;
        }
        .detail {
            margin: 12px 0;
            padding: 12px;
            background: #f8f9fa;
            border-radius: 4px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .detail strong {
            color: #343a40;
        }
        .groups {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .group-badge {
            background: #868d93;
            color: white;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 500;
        }
        .json-section {
            margin-top: 40px;
        }
        .textarea-container {
            position: relative;
        }
        textarea {
            width: 100%;
            height: 200px;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            padding: 12px;
            border: 1px solid #ced4da;
            border-radius: 4px;
            resize: vertical;
            background: #f8f9fa;
        }
        .tooltip {
            position: absolute;
            top: 12px;
            right: 12px;
            display: inline-block;
            z-index: 10;
        }
        .copy-icon {
            cursor: pointer;
            background: #007bff;
            border-radius: 4px;
            padding: 8px;
            transition: background-color 0.2s;
        }
        .copy-icon:hover {
            background: #0056b3;
        }
        .copy-icon svg {
            width: 16px;
            height: 16px;
            fill: white;
        }
        .tooltip .tooltiptext {
            visibility: hidden;
            width: 60px;
            background-color: #555;
            color: #fff;
            text-align: center;
            border-radius: 4px;
            padding: 5px;
            position: absolute;
            z-index: 1;
            bottom: 125%;
            left: 50%;
            margin-left: -30px;
            opacity: 0;
            transition: opacity 0.3s;
            font-size: 12px;
        }
        .tooltip:hover .tooltiptext {
            visibility: visible;
            opacity: 1;
        }
    </style>
    <script>
        function copyJson() {
            const textarea = document.getElementById('jsonTextarea');
            const tooltip = document.getElementById('tooltipText');
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(textarea.value).then(() => {
                    tooltip.innerText = 'Copied!';
                    setTimeout(() => {
                        tooltip.innerText = 'Copy';
                    }, 2000);
                }).catch(err => {
                    console.error('Clipboard API failed:', err);
                    fallbackCopy(textarea, tooltip);
                });
            } else {
                fallbackCopy(textarea, tooltip);
            }
        }
        function fallbackCopy(textarea, tooltip) {
            textarea.select();
            textarea.setSelectionRange(0, 99999);
            try {
                document.execCommand('copy');
                tooltip.innerText = 'Copied!';
                setTimeout(() => {
                    tooltip.innerText = 'Copy';
                }, 2000);
            } catch (err) {
                console.error('Fallback copy failed:', err);
                alert('Copy failed. Please select and copy manually.');
            }
        }
    </script>
</head>
<body>
    <div class="container">
        <h1>Authentication Successful</h1>
        <p class="subtitle">Your login was successful. Here are your details.</p>

        <div class="section">
            <h2>User Information</h2>
            <div class="detail"><strong>Full Name:</strong> <span>{{ first_name }} {{ last_name }}</span></div>
            <div class="detail"><strong>Email:</strong> <span>{{ email }}</span></div>
            <div class="detail"><strong>Username:</strong> <span>{{ sam_account_name }}</span></div>
        </div>

        <div class="section">
            <h2>Groups</h2>
            <div class="groups">
                {% if groups %}
                    {% for group in groups %}
                        <span class="group-badge">{{ group }}</span>
                    {% endfor %}
                {% else %}
                    <span>No groups</span>
                {% endif %}
            </div>
        </div>

        <div class="section">
            <h2>Session Information</h2>
            <div class="detail"><strong>Session ID:</strong> <span>{{ session_id }}</span></div>
            <div class="detail"><strong>Auth Time:</strong> <span>{{ auth_time }}</span></div>
            <div class="detail"><strong>Expiration Time:</strong> <span>{{ exp_time }}</span></div>
        </div>

        <div class="json-section">
            <h2>Raw JSON Response</h2>
            <div class="textarea-container">
                <textarea id="jsonTextarea" readonly>{{ json_raw }}</textarea>
                <div class="tooltip">
                    <div class="copy-icon" onclick="copyJson()">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
                            <path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/>
                        </svg>
                    </div>
                    <span class="tooltiptext" id="tooltipText">Copy</span>
                </div>
            </div>
        </div>
    </div>
</body>
</html>""")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Health check endpoint
@app.get('/health')
def health():
    """Health check endpoint"""
    try:
        return {'health': 'ok'}
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


#SSO as service to other applications
@app.get("/sso-service")
def sso_auth():
    """
    SSO Generic Service Entry point for any team wanting SSO authentication (Non SAGE Specific)
    
    """
    try:
        return RedirectResponse(f"/login")
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"SSO auth error: {error}")
    
# SAGE Specific SSO entry point
@app.get("/sso-auth")
def sso_auth(use_case: str = Query(...)):
    """
    Redirects to the /login endpoint with use_case parameter for SSO authentication.
    
    Args:
        use_case: The use case identifier (digital, vol-trend, QBR, SAGE-Common)
    """
    try:
        # Validate use_case exists
        if use_case not in USE_CASE_URLS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid use_case: {use_case}. Valid options: {list(USE_CASE_URLS.keys())}"
            )

        return RedirectResponse(f"/login?use_case={use_case}")
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"SSO auth error: {error}")

#Needs to be tested later-after SSO team fix the issue
@app.get("/sso-authenticate")
def sso_authenticate(use_case: str = Query(...)):
    """
    Redirects to the /login endpoint with use_case parameter for SSO authentication.
    
    Args:
        use_case: The use case identifier (digital, vol-trend, QBR, SAGE-Common)
    """
    try:
        # Validate use_case exists
        if use_case not in USE_CASE_URLS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid use_case: {use_case}. Valid options: {list(USE_CASE_URLS.keys())}"
            )
        
        # Redirect to /login with use_case
        return RedirectResponse(f"/login")
        
    except HTTPException as he:
        raise he
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"SSO auth error: {error}")


#SAGE specific login endpoint
@app.get("/login")
def login(use_case: str = Query(default=None)):
    """
    Redirects the user to SSO authentication URL.
    Encodes use_case in the state parameter to preserve it through OAuth flow.
    If no use_case is provided, sets state to indicate no-use-case mode.
    """
    try:
        print(f"login endpoint is called with use_case: {use_case}")
        
        # Build state parameter
        if use_case:
            state_value = f"usecase:{use_case}"
        else:
            # No use_case provided - set special state for no-usecase mode
            state_value = "no-usecase"
        
        # Build SSO authorization URL
        reauth_url = (
            f"{auth_url}?response_type=code"
            f"&client_id={sso_client_id}"
            f"&redirect_uri={redirect_token}"
            f"&scope={scope}"
            f"&state={state_value}"
        )
        
        print(f"Redirecting to SSO with state: {state_value}")
        print(f"auth_url : {reauth_url}")
        
        return RedirectResponse(reauth_url)
        
    except HTTPException as he:
        raise he
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"user is unable to login due to the error message: {error}")

# Token exchange and user validation endpoint
@app.get("/token")
def token_receive_from_sso(code: str = Query(...), state: str = Query(default=None)):
    """
    Handles the token exchange process after user authentication.
    Validates user access via email OR AD group membership and either redirects to use case URL or returns JSON based on state.
    """
    try:
        print("/token endpoint is called")
        print(f"Received authorization code: {code}")
        print(f"Received state: {state}")
       
        if not code:
            raise HTTPException(status_code=400, detail="Error: No code returned from SSO Server.")
        
        # Determine mode from state
        use_case = None
        is_no_usecase_mode = False
        
        if state == "no-usecase":
            is_no_usecase_mode = True
            print("No-use-case mode: will return JSON response")
        elif state and state.startswith("usecase:"):
            use_case = state.split(":", 1)[1]
            print(f"Extracted use_case from state: {use_case}")
        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid or missing state parameter. Please start authentication from /sso-auth or /sso-service endpoint."
            )

        # If use-case mode, validate use_case exists
        if not is_no_usecase_mode and use_case not in USE_CASE_URLS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid use_case: {use_case}. Valid options: {list(USE_CASE_URLS.keys())}"
            )
        print("Use_case validation passed.")
        
        # Prepare token request parameters (state is NOT part of OAuth2 token exchange)
        token_params = {
            "grant_type": grant_type,
            "client_id": sso_client_id,
            "client_secret": sso_client_secret,
            "redirect_uri": redirect_token,
            "code": code
        }
        
        print(f"Using redirect_uri: {redirect_token}")
 
        token_headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        print(f"POST request to {token_endpoint}")

        # Request access token from SSO with retry for transient errors
        max_retries = 3
        token_response = None
        for attempt in range(1, max_retries + 1):
            print(f"Making POST request to token endpoint (attempt {attempt}/{max_retries}).")
            try:
                token_response = requests.post(
                    token_endpoint, headers=token_headers, data=token_params, timeout=15
                )
                print(f"Token response status: {token_response.status_code}")
                if token_response.status_code == 200:
                    break
                # Retry only on 500/502/503/504 (server-side transient errors)
                if token_response.status_code in (500, 502, 503, 504) and attempt < max_retries:
                    wait_time = 2 ** attempt
                    print(f"Token endpoint returned {token_response.status_code}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                # Non-retryable error or last attempt
                break
            except requests.exceptions.Timeout:
                print(f"Token request timed out (attempt {attempt}/{max_retries})")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise HTTPException(status_code=504, detail="Token request to SSO server timed out.")
            except requests.exceptions.RequestException as req_err:
                print(f"Token request failed (attempt {attempt}/{max_retries}): {req_err}")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise HTTPException(status_code=502, detail=f"Failed to connect to SSO server: {req_err}")

        if token_response is None or token_response.status_code != 200:
            error_text = token_response.text if token_response else "No response"
            status = token_response.status_code if token_response else 502
            print(f"Token response error after {max_retries} attempts: {error_text}")
            raise HTTPException(
                status_code=status, 
                detail=f"Not able to fetch the token - {error_text}"
            )

        # Extract access and refresh tokens
        token_response_data = token_response.json()
        print(f"token_response_data received")
        access_token = token_response_data.get("access_token")
        refresh_token_value = token_response_data.get("refresh_token")
        print(f"Tokens extracted successfully")
        
        try:
            decoded_access_token = jwt.decode(access_token, options={"verify_signature": False})
            print(f"Decoded access token successfully")
            print(f"Access token contents: {decoded_access_token}")
        except Exception as e:
            print(f"Could not decode access token: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to decode access token: {str(e)}"
            )
        
        print("Extracting user information from access token.")
        
        # Extract email — try 'mail' first, fall back to 'email' in the access token
        user_email = decoded_access_token.get("mail") or decoded_access_token.get("email")
        if not user_email:
            print("WARNING: 'mail'/'email' not in access token — calling userinfo endpoint as fallback")
            try:
                userinfo_resp = requests.get(
                    userinfo_endpoint,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10
                )
                print(f"Userinfo endpoint status: {userinfo_resp.status_code}")
                if userinfo_resp.status_code == 200:
                    userinfo_data = userinfo_resp.json()
                    print(f"Userinfo response: {userinfo_data}")
                    user_email = userinfo_data.get("email") or userinfo_data.get("mail")
                else:
                    print(f"Userinfo endpoint returned non-200: {userinfo_resp.text}")
            except Exception as ui_err:
                print(f"Userinfo endpoint call failed: {ui_err}")

        if not user_email:
            print("WARNING: User email not found in access token or userinfo endpoint. AD group check will still proceed.")
        else:
            print(f"User email: {user_email}")
        
        # Extract groups and clean group names
        print("Extracting groups from access token.")
        # Token may deliver the groups claim under different casings:
        # 'groups', 'Groups', or 'GROUPS'. Check all to avoid dropping memberships.
        raw_groups = (
            decoded_access_token.get("groups")
            or decoded_access_token.get("Groups")
            or decoded_access_token.get("GROUPS")
            or []
        )
        if isinstance(raw_groups, str):
            raw_groups = [raw_groups]
        groups = [extract_group_name(g) for g in raw_groups if extract_group_name(g)]
        print(f"Extracted group names: {groups}")
        
        # Extract other user attributes
        first_name = decoded_access_token.get("firstName") or decoded_access_token.get("firstname")
        last_name = decoded_access_token.get("lastName") or decoded_access_token.get("lastname")
        sam_account_name = decoded_access_token.get("sAMAccountName")
        employee_id = decoded_access_token.get("employeeID")
        
        print(f"User: {first_name} {last_name} ({sam_account_name})")
        
        # Check AD group membership - TREAT LIKE EMAIL-BASED ACCESS
        has_ad_group_access = False
        has_sage_common_group = False
        has_specific_usecase_group = False
        
        if not is_no_usecase_mode and use_case:
            # Convert user groups to set for efficient lookup
            user_groups_set = set(groups)
            print(f"User groups: {user_groups_set}")
            
            # Check if user has SAGE-Common group (SAGE All access, except strict-access use cases)
            from .config import AD_GROUPS_BY_USECASE
            sage_common_groups = AD_GROUPS_BY_USECASE.get("SAGE-Common", set())
            has_sage_common_group = bool(user_groups_set & sage_common_groups)
            print(f"Has SAGE-Common group: {has_sage_common_group}")
            
            # Check if user has specific use case group
            authorized_ad_groups = AD_GROUPS_BY_USECASE.get(use_case, set())
            has_specific_usecase_group = bool(user_groups_set & authorized_ad_groups)
            print(f"Has {use_case} specific group: {has_specific_usecase_group}")
            
            # Apply access rules based on use case strictness
            if use_case in STRICT_ACCESS_USECASES:
                # Strict access use cases require EXPLICIT group membership (SAGE-Common doesn't grant access)
                has_ad_group_access = has_specific_usecase_group
                print(f"Strict access use case '{use_case}' - AD group access: {has_ad_group_access}")
            else:
                # For other use cases: SAGE-Common OR specific use case group grants access
                has_ad_group_access = has_sage_common_group or has_specific_usecase_group
                print(f"Standard access use case '{use_case}' - AD group access: {has_ad_group_access} (SAGE-Common: {has_sage_common_group}, Specific: {has_specific_usecase_group})")
        
        # Fetch user's authorized use cases from Spanner (email-based check)
        has_email_access = False
        authorized_use_cases = []

        if user_email:
            print("Fetching authorized use cases from Spanner.")
            try:
                authorized_use_cases = get_user_authorized_usecases(user_email)
                print(f"Authorized use cases from Spanner: {authorized_use_cases}")
            except HTTPException as he:
                print(f"Spanner error: {he.detail}")
                print("Continuing with AD group check despite Spanner error")
                authorized_use_cases = []
            except Exception as e:
                print(f"Unexpected error in get_user_authorized_usecases: {e}")
                print("Continuing with AD group check despite error")
                authorized_use_cases = []
        else:
            print("Skipping Spanner email check — no email in token. AD group check only.")
        
        # If use-case mode, validate access via EMAIL OR AD GROUP
        if not is_no_usecase_mode:
            # Check email-based access (existing logic)
            has_sage_common = "SAGE-Common" in authorized_use_cases
            has_specific_usecase = use_case in authorized_use_cases
            
            if use_case in STRICT_ACCESS_USECASES:
                # Strict access use cases require explicit access (either via email or AD group)
                has_email_access = has_specific_usecase
                print(f"Strict access use case '{use_case}' - Email access: {has_email_access}")
            else:
                # For non-strict use cases, allow if SAGE-Common or specific use case is assigned
                has_email_access = has_sage_common or has_specific_usecase
                print(f"Standard access use case '{use_case}' - Email access: {has_email_access} (SAGE-Common: {has_sage_common}, Specific: {has_specific_usecase})")
            
            print(f"Email-based access: {has_email_access} (SAGE-Common: {has_sage_common}, Specific: {has_specific_usecase})")
            
            # OR condition: user needs EITHER email access OR AD group access
            if not has_email_access and not has_ad_group_access:
                access_type = "strict" if use_case in STRICT_ACCESS_USECASES else "standard"
                print(f"Access denied for {access_type} use case '{use_case}'. Email access: {has_email_access}, AD group access: {has_ad_group_access}")
                print(f"User has Spanner access to: {authorized_use_cases}, User AD groups: {groups}")
                contact = USE_CASE_CONTACTS.get(use_case, DEFAULT_SUPPORT_CONTACT)
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied. You do not have permission to access {use_case} via email or AD group membership. Contact {contact}"
                )
            
            # Determine access method(s) for logging
            access_method = []
            if has_email_access:
                access_method.append("email")
            if has_ad_group_access:
                access_method.append("AD group")
            access_type = "strict" if use_case in STRICT_ACCESS_USECASES else "standard"
            print(f"Access granted for {user_email} to {use_case} ({access_type} access) via {' and '.join(access_method)}")
            
            # Filter to only known SAGE/use-case groups — users with 200+ AD groups
            # produce a JWT that exceeds the 4KB browser cookie limit otherwise.
            relevant_groups = [g for g in groups if g in AD_GROUPS]

            user_metadata = {
                "firstName": first_name,
                "lastName": last_name,
                "email": user_email,
                "sAMAccountName": sam_account_name,
                "employeeID": employee_id,
                "groups": relevant_groups,
                "session_id": make_token(),
                "auth_time": datetime.now(timezone.utc).isoformat(),
                "exp_time": (datetime.now(timezone.utc) + timedelta(seconds=token_expiration_time)).isoformat()
            }
            
            # Create JWT token
            jwt_token = jwt.encode(user_metadata, shared_secret_key, algorithm="HS256")

            cookie_domain = domain  # Default domain from ENV_CONFIG
        
            if use_case and use_case in USE_CASE_COOKIE_DOMAINS:
                cookie_domain = USE_CASE_COOKIE_DOMAINS[use_case].get(GCP_ENV, domain)
                print(f"Using custom cookie domain for {use_case}: {cookie_domain}")
            else:
                print(f"Using default cookie domain: {cookie_domain}")
            
            # Redirect to /disclaimer with cookie set
            disclaimer_url = f"/disclaimer?use_case={use_case}"
            print(f"Redirecting user to disclaimer: {disclaimer_url}")
            
            redirect_response = RedirectResponse(disclaimer_url)
            redirect_response.set_cookie(
                key=sso_cookie_key,
                value=jwt_token,
                domain=cookie_domain,
                httponly=False,
                samesite="None",
                secure=True,
                max_age=token_expiration_time
            )
            return redirect_response
        
        print(f"Returning HTML page for {user_email} (no-use-case mode)")
        user_metadata = {
            "firstName": first_name,
            "lastName": last_name,
            "email": user_email,
            "sAMAccountName": sam_account_name,
            "employeeID": employee_id,
            "groups": groups,
            "session_id": make_token(),
            "auth_time": datetime.now(timezone.utc).isoformat(),
            "exp_time": (datetime.now(timezone.utc) + timedelta(seconds=token_expiration_time)).isoformat()
        }
        # Build the JSON response as a dict (for embedding in HTML)
        json_response = {
            "success": True,
            "user": {
                "firstName": user_metadata["firstName"],
                "lastName": user_metadata["lastName"],
                "email": user_metadata["email"],
                "sAMAccountName": user_metadata["sAMAccountName"],
                "groups": user_metadata["groups"]
            },
            "session": {
                "session_id": user_metadata["session_id"],
                "auth_time": user_metadata["auth_time"],
                "exp_time": user_metadata["exp_time"]
            }
        }
        
        # Render HTML using Jinja2 autoescape template for XSS protection
        html_content = AUTH_SUCCESS_TEMPLATE.render(
            first_name=user_metadata["firstName"],
            last_name=user_metadata["lastName"],
            email=user_metadata["email"],
            sam_account_name=user_metadata["sAMAccountName"],
            groups=user_metadata["groups"],
            session_id=user_metadata["session_id"],
            auth_time=user_metadata["auth_time"],
            exp_time=user_metadata["exp_time"],
            json_raw=json.dumps(json_response, indent=2),
        )

        return HTMLResponse(content=html_content)
    
    except HTTPException as http_error:
        print(f"HTTPException raised: {http_error.detail}")
        raise http_error
    except Exception as error:
        print(f"Unexpected error in /token: {error}")
        contact = DEFAULT_SUPPORT_CONTACT
        try:
            # prefer use-case specific contact if available
            if 'use_case' in locals() and use_case:
                contact = USE_CASE_CONTACTS.get(use_case, DEFAULT_SUPPORT_CONTACT)
        except Exception:
            contact = DEFAULT_SUPPORT_CONTACT

        raise HTTPException(
            status_code=500,
            detail=f"Error occurred: {error}. Please contact {contact}"
        )

# User info endpoint
@app.get("/user_info")
def user_info(request: Request):
    """Retrieves and returns the information of the logged-in user."""
    print("user_info is called")
    print(f"Request is:{Request}")
    try:
        user_metadata_token = request.cookies.get(sso_cookie_key)
        print("user_metadata_token is done")
        print(f"user_metadata_token is: {user_metadata_token}")
        if not user_metadata_token:
            raise HTTPException(status_code=401, detail="Unauthorized: No token provided.")

        user_metadata = jwt.decode(user_metadata_token, shared_secret_key, algorithms=["HS256"])
        print("user_metadata is done")
        print(user_metadata)
       
        return {
            "firstName": user_metadata.get("firstName") or user_metadata.get("firstname"),
            "lastName": user_metadata.get("lastName") or user_metadata.get("lastname"),
            "email": user_metadata.get("email"),
            "auth_time": user_metadata.get("auth_time"),
            "exp_time": user_metadata.get("exp_time"),
            "groups": user_metadata.get("groups", []),
        }
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Error occurred: {error}")
    
# Refresh JWT cookie endpoint
# will be called from frontend to refresh the cookie expiration time
@app.post("/refresh_cookie")
def refresh_cookie(request: Request, response: Response):
    """Refresh the JWT cookie expiration."""
    user_metadata_token = request.cookies.get(sso_cookie_key)
    if not user_metadata_token:
        raise HTTPException(status_code=401, detail="Unauthorized: No token provided.")

    try:
        user_metadata = jwt.decode(user_metadata_token, shared_secret_key, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")

    # Update exp_time
    user_metadata["exp_time"] = (datetime.now(timezone.utc) + timedelta(seconds=token_expiration_time)).isoformat()

    # Re-encode JWT
    jwt_token = jwt.encode(user_metadata, shared_secret_key, algorithm="HS256")

    # Determine cookie domain based on use case (from the existing token)
    use_case = user_metadata.get("use_case")
    cookie_domain = domain  # Default domain
    
    if use_case and use_case in USE_CASE_COOKIE_DOMAINS:
        cookie_domain = USE_CASE_COOKIE_DOMAINS[use_case].get(GCP_ENV, domain)
        print(f"Refreshing cookie with custom domain for {use_case}: {cookie_domain}")
    else:
        print(f"Refreshing cookie with default domain: {cookie_domain}")

    # Set refreshed cookie on the response parameter
    response.set_cookie(
        key=sso_cookie_key,
        value=jwt_token,
        domain=cookie_domain, 
        httponly=False,
        samesite="None",
        secure=True,
        max_age=token_expiration_time
    )
    
    return {"message": "Cookie refreshed"}


@app.get("/logout")
def logout(request: Request, use_case: str = Query(default=None)):
    """Clear the sage-cookie and redirect to the login page."""
    if use_case and use_case not in USE_CASE_URLS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid use_case: {use_case}. Valid options: {list(USE_CASE_URLS.keys())}"
        )

    cookie_domain = domain
    if use_case and use_case in USE_CASE_COOKIE_DOMAINS:
        cookie_domain = USE_CASE_COOKIE_DOMAINS[use_case].get(GCP_ENV, domain)

    login_page_url = "/login-page"
    if use_case:
        login_page_url += f"?use_case={use_case}"

    response = RedirectResponse(url=login_page_url)
    response.delete_cookie(
        key=sso_cookie_key,
        domain=cookie_domain,
        samesite="None",
        secure=True,
    )
    return response


@app.get("/login-page")
def login_page(request: Request, use_case: str = Query(default=None)):
    """Displays a login page after successful logout."""
    login_url = f"/sso-auth?use_case={html.escape(use_case, quote=True)}" if use_case else "/sso-service"
    use_case_label = html.escape(use_case.upper()) if use_case else "SSO SERVICE"

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Sign In - {use_case_label}</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                background: linear-gradient(135deg, #eef0f8 0%, #dce1ed 100%);
                color: #212529;
            }}
            .main-content {{
                flex: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 40px 20px;
            }}
            .card {{
                background: #ffffff;
                border-radius: 12px;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.12);
                overflow: hidden;
                width: 100%;
                max-width: 420px;
            }}
            .card-accent {{
                height: 4px;
                background: linear-gradient(90deg, #cc0000 0%, #475f7b 100%);
            }}
            .card-body {{
                padding: 40px 32px 48px;
                text-align: center;
            }}
            .logo {{
                height: 28px;
                margin-bottom: 24px;
            }}
            .app-name {{
                font-weight: 700;
                font-size: 24px;
                color: #475f7b;
                letter-spacing: 2px;
                margin-bottom: 4px;
            }}
            .app-subtitle {{
                font-size: 0.78rem;
                color: #6c757d;
                letter-spacing: 0.5px;
                margin-bottom: 24px;
            }}
            .divider {{
                border: none;
                border-top: 1px solid #dee2e6;
                margin: 16px 0;
            }}
            .sign-in-text {{
                font-size: 0.85rem;
                color: #3a4a5c;
                margin-bottom: 24px;
            }}
            .btn-sso {{
                display: block;
                width: 100%;
                padding: 12px 24px;
                background-color: #cc0000;
                color: #ffffff;
                text-decoration: none;
                border-radius: 6px;
                font-size: 15px;
                font-weight: 600;
                border: none;
                cursor: pointer;
                transition: background-color 0.2s;
            }}
            .btn-sso:hover {{
                background-color: #a30000;
            }}
            .policy-text {{
                font-size: 0.75rem;
                color: #6c757d;
                margin-top: 16px;
            }}
            .footer {{
                background: #ffffff;
                border-top: 1px solid #e9ecef;
                padding: 12px 24px;
            }}
            .footer-inner {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                max-width: 1200px;
                margin: 0 auto;
            }}
            .footer-left {{
                display: flex;
                align-items: center;
                gap: 12px;
            }}
            .footer-logo {{
                height: 18px;
            }}
            .footer-divider {{
                width: 1px;
                height: 16px;
                background: #dee2e6;
            }}
            .footer-copyright {{
                font-size: 0.72rem;
                color: #6c757d;
            }}
            .footer-accent {{
                height: 3px;
                background: linear-gradient(90deg, #cc0000 0%, #475f7b 100%);
            }}
        </style>
    </head>
    <body>
        <div class="main-content">
            <div class="card">
                <div class="card-accent"></div>
                <div class="card-body">
                    <img alt="CVS Health" class="logo" src="/static/cvs-health-logo.png">
                    <div class="app-name">{use_case_label}</div>
                    <p class="app-subtitle">CVS Health Enterprise Application</p>
                    <hr class="divider">
                    <p class="sign-in-text">Sign in with your CVS Health corporate credentials via Single Sign-On (SSO).</p>
                    <a href="{login_url}" class="btn-sso">Sign in with SSO</a>
                    <p class="policy-text">By signing in, you agree to CVS Health's security policies.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# Add User entry into SAGE Users table
@app.post("/add-active-user")
def add_active_user(email: str, usecase_name: str, user_name: str):
    """
    Adds an active user entry into the sage_users table in Spanner.
    
    Args:
        email: User's email address
        usecase_name: Name of the use case to assign to the user
        user_name: User's name (required for primary key)
    """
    try:
        print(f"Adding active user: {email} for usecase: {usecase_name}, user_name: {user_name}")
        
        # Validate required fields
        if not email or not usecase_name or not user_name:
            raise HTTPException(status_code=400, detail="email, usecase_name, and user_name are required.")
        
        # Get current timestamp
        current_ts = datetime.now(timezone.utc)
        
        database = get_spanner_client()
        
        with database.batch() as batch:
            batch.insert(
                table="sage_users",
                columns=("user_name", "user_email_id", "usecase_name", "data_create_ts", "data_update_ts", "Active_ind"),
                values=[(user_name, email.lower(), usecase_name, current_ts, current_ts, True)]
            )
        
        print(f"Active user {email} added successfully.")
        return {"message": f"Active user {email} added successfully."}
    
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error adding active user: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error adding active user: {str(e)}"
        )
        
        
# Deactivate User entry in SAGE Users table
@app.post("/deactivate-user")
def deactivate_user(email: str, usecase_name: str, user_name: str):
    """
    Deactivates a user entry in the sage_users table in Spanner.
    
    Args:
        email: User's email address
        usecase_name: Name of the use case to deactivate for the user
        user_name: User's name (required for primary key)
    """
    try:
        print(f"Deactivating user: {email} for usecase: {usecase_name}, user_name: {user_name}")
        
        # Validate required fields
        if not email or not usecase_name or not user_name:
            raise HTTPException(status_code=400, detail="email, usecase_name, and user_name are required.")
        
        # Get current timestamp for update
        current_ts = datetime.now(timezone.utc)
        
        database = get_spanner_client()
        
        with database.batch() as batch:
            batch.update(
                table="sage_users",
                columns=("user_name", "user_email_id", "usecase_name", "data_update_ts", "Active_ind"),
                values=[(user_name, email.lower(), usecase_name, current_ts, False)]
            )
        
        print(f"User {email} deactivated successfully for usecase {usecase_name}.")
        return {"message": f"User {email} deactivated successfully for usecase {usecase_name}."}
    
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error deactivating user: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error deactivating user: {str(e)}"
        )

# Create sage_users table in Spanner
@app.post("/create-sage-users-table")
def create_sage_users_table():
    """
    Creates the sage_users table in Spanner with the specified DDL schema.
    """
    try:
        print("Creating sage_users table in Spanner.")
        
        database = get_spanner_client()
        
        ddl_statements = [
            """
            CREATE TABLE sage_users (
                user_name STRING(MAX) NOT NULL,
                user_email_id STRING(MAX) NOT NULL,
                usecase_name STRING(MAX) NOT NULL,
                data_create_ts TIMESTAMP NOT NULL,
                data_update_ts TIMESTAMP NOT NULL,
                Active_ind BOOL NOT NULL
            ) PRIMARY KEY (user_name, user_email_id, usecase_name)
            """
        ]
        
        operation = database.update_ddl(ddl_statements)
        operation.result()  # Wait for the operation to complete
        
        print("sage_users table created successfully.")
        return {"message": "sage_users table created successfully."}
    
    except Exception as e:
        print(f"Error creating sage_users table: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating sage_users table: {str(e)}"
        )

#Disaclaimer endpoint
@app.get("/disclaimer")
def disclaimer(request: Request, use_case: str = Query(...)):
    """
    Displays a disclaimer page for the user to acknowledge before proceeding to the use case URL.
    For cross-domain use cases (like Trend), accepts token via URL parameter and sets cookie
    on the target domain using JavaScript.
    
    Args:
        use_case: The use case identifier (digital, vol-trend, QBR, SAGE-Common, Trend)
        token: Optional JWT token for cross-domain use cases
    """
    try:
        print(f"/disclaimer endpoint called with use_case: {use_case}")
        
        # Validate use_case exists
        if use_case not in USE_CASE_URLS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid use_case: {use_case}. Valid options: {list(USE_CASE_URLS.keys())}"
            )
        
        # Get environment (default to prod if not set)
        current_env = GCP_ENV or "prod"
        
        # Get the redirect URL for the use case
        redirect_url = USE_CASE_URLS[use_case].get(current_env)
        if not redirect_url:
            raise HTTPException(
                status_code=500,
                detail=f"No URL configured for use_case '{use_case}' in environment '{current_env}'"
            )
        
        
        # Render disclaimer template with redirect_url.
        # Prefer project 'src/templates' folder; if missing in the container image, fall back to 'src' folder.
        template_path = TEMPLATES_DIR_PATH / "disclaimer.html"
        if template_path.exists():
            print(f"Serving disclaimer page from {TEMPLATES_DIR} for use_case: {use_case}, redirecting to: {redirect_url}")
            return templates.TemplateResponse(request, "disclaimer.html", {"redirect_url": redirect_url})
        else:
            # Fallback: render template from src folder using a minimal TemplateResponse
            src_template_dir = str(BASE_DIR)
            print(f"Template not found in {TEMPLATES_DIR}; falling back to {src_template_dir}")
            fallback_templates = Jinja2Templates(directory=src_template_dir)
            return fallback_templates.TemplateResponse(request, "disclaimer.html", {"redirect_url": redirect_url})
        
    except HTTPException as he:
        raise he
    except Exception as error:
        print(f"Disclaimer page error: {error}")
        raise HTTPException(status_code=500, detail=f"Disclaimer page error: {error}")


# Authentication success display endpoint
@app.get("/show-auth-success")
def show_auth_success(data: str = Query(...)):
    """
    Displays the authentication success HTML page with decoded JSON data.
    Receives Base64-encoded JSON from dialsmart-login.
    
    Args:
        data: Base64-encoded JSON string containing user/session data.
    """
    try:
        # Decode the Base64 data
        import base64
        decoded_data = base64.b64decode(data).decode()
        json_response = json.loads(decoded_data)
        
        # Extract user_metadata from json_response (assuming structure matches dialsmart-login)
        user_metadata = {
            "firstName": json_response["user"]["firstName"],
            "lastName": json_response["user"]["lastName"],
            "email": json_response["user"]["email"],
            "sAMAccountName": json_response["user"]["sAMAccountName"],
            "groups": json_response["user"]["groups"],
            "session_id": json_response["session"]["session_id"],
            "auth_time": json_response["session"]["auth_time"],
            "exp_time": json_response["session"]["exp_time"]
        }
        
        # Render HTML using Jinja2 autoescape template for XSS protection
        html_content = AUTH_SUCCESS_TEMPLATE.render(
            first_name=user_metadata["firstName"],
            last_name=user_metadata["lastName"],
            email=user_metadata["email"],
            sam_account_name=user_metadata["sAMAccountName"],
            groups=user_metadata["groups"],
            session_id=user_metadata["session_id"],
            auth_time=user_metadata["auth_time"],
            exp_time=user_metadata["exp_time"],
            json_raw=json.dumps(json_response, indent=2),
        )

        return HTMLResponse(content=html_content)
        
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"Invalid data or error displaying page: {error}")

    
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
