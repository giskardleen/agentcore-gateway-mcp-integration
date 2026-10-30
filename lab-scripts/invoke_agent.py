import requests
import urllib.parse
import json
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import secrets
import sys
import os

# Configuration
REGION_NAME = os.getenv("AWS_REGION", "us-west-2")

# Retrieve test user credentials from Secrets Manager (created by the lab stack)
_secrets_client = boto3.client('secretsmanager', region_name=REGION_NAME)
_creds = json.loads(_secrets_client.get_secret_value(
    SecretId='/personal-agent/cognito/test-user-credentials'
)['SecretString'])
username = _creds['username']
password = _creds['password']

# Initialize clients
ssm_client = boto3.client('ssm', region_name=REGION_NAME)
cognito_client = boto3.client('cognito-idp', region_name=REGION_NAME)

# Module-level variables (initialized when imported)
agent_arn = None
client_id = None

def init_config(verbose=True):
    """Initialize configuration from SSM Parameter Store."""
    global agent_arn, client_id
    
    # Get agent ARN from SSM Parameter Store
    try:
        response = ssm_client.get_parameter(Name='/personal-agent/agent-arn')
        agent_arn = response['Parameter']['Value'].strip().strip('()')
        if verbose:
            print(f"✅ Retrieved agent ARN from SSM: {repr(agent_arn)}")
        # Validate it looks like a proper ARN
        if not agent_arn.startswith('arn:aws:bedrock-agentcore:') or '/' not in agent_arn:
            if verbose:
                print(f"⚠️  SSM value doesn't look like a valid ARN, attempting CLI fallback...")
            raise ValueError(f"Invalid ARN format: {agent_arn}")
    except Exception as e:
        if verbose:
            print(f"⚠️  SSM lookup issue: {e}")
        agent_arn = _discover_agent_arn(verbose)
    
    # Get Cognito client ID from SSM Parameter Store
    try:
        response = ssm_client.get_parameter(Name='/personal-agent/cognito/client-id')
        client_id = response['Parameter']['Value']
        if verbose:
            print(f"✅ Retrieved Cognito client ID from SSM: {client_id}")
    except Exception as e:
        if verbose:
            print(f"❌ Failed to get Cognito client ID from SSM: {e}")
        raise

def _discover_agent_arn(verbose=True):
    """Discover agent ARN from agentcore CLI and update SSM."""
    if verbose:
        print(f"🔄 Trying 'agentcore status' CLI to discover agent ARN...")
    import subprocess
    import re
    try:
        result = subprocess.run(['agentcore', 'status'], capture_output=True, text=True, timeout=30)
        match = re.search(r'arn:aws:bedrock-agentcore:[^\s\)\"]+', result.stdout)
        if match:
            arn = match.group(0)
            if verbose:
                print(f"✅ Got agent ARN from CLI: {arn}")
            # Update SSM with correct value
            ssm_client.put_parameter(Name='/personal-agent/agent-arn', Value=arn, Type='String', Overwrite=True)
            if verbose:
                print(f"✅ Updated SSM with correct ARN")
            return arn
        else:
            raise RuntimeError("Could not extract ARN from agentcore status output")
    except Exception as e2:
        if verbose:
            print(f"❌ CLI fallback also failed: {e2}")
        raise

def refresh_agent_arn_on_404(verbose=True):
    """Called when invocation gets 404 — agent ARN in SSM is stale."""
    global agent_arn
    if verbose:
        print("⚠️  Agent not found (404). ARN in SSM may be stale after redeployment.")
        print("    Attempting to discover current agent ARN...")
    try:
        new_arn = _discover_agent_arn(verbose)
        agent_arn = new_arn
        return True
    except Exception:
        if verbose:
            print("❌ Could not discover new agent ARN. Has the agent been deployed?")
            print("   Run: agentcore deploy -y")
        return False

def _get_user_pool_id():
    """Derive the user pool ID from the Cognito discovery URL in SSM."""
    response = ssm_client.get_parameter(Name='/personal-agent/cognito/discovery-url')
    # e.g. https://cognito-idp.us-west-2.amazonaws.com/us-west-2_AbCdEfGhI/.well-known/openid-configuration
    return response['Parameter']['Value'].split('/')[3]

def _sync_test_user_password(verbose=True):
    """Re-sync the Cognito test user's password from Secrets Manager.

    The lab stack sets the user's password via a CloudFormation custom
    resource, but secretsmanager dynamic references are not resolved in
    custom resource properties, so the password in Cognito can drift from
    the secret. The secret is the source of truth — re-apply it here.
    """
    if verbose:
        print("⚠️  Password out of sync, re-syncing Cognito user from Secrets Manager...")
    cognito_client.admin_set_user_password(
        UserPoolId=_get_user_pool_id(),
        Username=username,
        Password=password,
        Permanent=True
    )
    if verbose:
        print("✅ Password re-synced")

def get_cognito_token():
    """Get Cognito bearer token, self-healing if the password is out of sync."""
    auth_params = {'USERNAME': username, 'PASSWORD': password}
    try:
        response = cognito_client.initiate_auth(
            ClientId=client_id,
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters=auth_params
        )
    except cognito_client.exceptions.NotAuthorizedException:
        # Cognito user password drifted from the secret — re-sync and retry once
        _sync_test_user_password()
        response = cognito_client.initiate_auth(
            ClientId=client_id,
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters=auth_params
        )
    return response['AuthenticationResult']['AccessToken']

def invoke_agent(prompt, session_id, auth_token, verbose=False):
    """
    Invoke the agent with a prompt and return the response.
    Attempts Bearer token auth first (for JWT-configured agents).
    Falls back to SigV4 auth if the agent is still using IAM default.
    """
    # Build the invocation URL using URL-encoded full ARN (per AWS docs)
    if agent_arn.startswith('arn:'):
        escaped_arn = urllib.parse.quote(agent_arn, safe='')
        url = f"https://bedrock-agentcore.{REGION_NAME}.amazonaws.com/runtimes/{escaped_arn}/invocations?qualifier=DEFAULT"
    else:
        # If we only have an ID, build the ARN first
        sts_client = boto3.client('sts', region_name=REGION_NAME)
        account_id = sts_client.get_caller_identity()['Account']
        full_arn = f"arn:aws:bedrock-agentcore:{REGION_NAME}:{account_id}:agent-runtime/{agent_arn.strip()}"
        escaped_arn = urllib.parse.quote(full_arn, safe='')
        url = f"https://bedrock-agentcore.{REGION_NAME}.amazonaws.com/runtimes/{escaped_arn}/invocations?qualifier=DEFAULT"
    
    if verbose:
        print(f"🔗 Invoking agent: {agent_arn}")
    
    payload = json.dumps({"prompt": prompt})
    
    # First attempt: Bearer token (for JWT/OAuth-configured agents)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
        "X-Amzn-Trace-Id": secrets.token_hex(17)
    }
    
    response = requests.post(url, headers=headers, data=payload, stream=True)
    
    # Handle 403 auth mismatch — agent likely expects SigV4 (default IAM auth)
    if response.status_code == 403 and "Authorization method mismatch" in response.text:
        session = boto3.Session(region_name=REGION_NAME)
        credentials = session.get_credentials().get_frozen_credentials()
        
        sigv4_headers = {
            "Content-Type": "application/json",
            "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
            "X-Amzn-Trace-Id": secrets.token_hex(17)
        }
        
        aws_request = AWSRequest(method='POST', url=url, data=payload, headers=sigv4_headers)
        SigV4Auth(credentials, 'bedrock-agentcore', REGION_NAME).add_auth(aws_request)
        
        response = requests.post(url, headers=dict(aws_request.headers), data=payload, stream=True)
    
    # Handle 401 - token expired, retry with fresh token
    if response.status_code == 401:
        if verbose:
            print("⚠️  Token expired (401), refreshing authentication...")
        auth_token = get_cognito_token()
        headers["Authorization"] = f"Bearer {auth_token}"
        response = requests.post(url, headers=headers, data=payload, stream=True)
        if verbose:
            print("✅ Retried with fresh token")
    
    # Handle 404 - agent not found (stale ARN after redeployment)
    if response.status_code == 404:
        if refresh_agent_arn_on_404(verbose):
            # Rebuild URL with new ARN and retry
            if agent_arn.startswith('arn:'):
                escaped_arn = urllib.parse.quote(agent_arn, safe='')
                url = f"https://bedrock-agentcore.{REGION_NAME}.amazonaws.com/runtimes/{escaped_arn}/invocations?qualifier=DEFAULT"
            else:
                sts_client = boto3.client('sts', region_name=REGION_NAME)
                account_id = sts_client.get_caller_identity()['Account']
                full_arn = f"arn:aws:bedrock-agentcore:{REGION_NAME}:{account_id}:agent-runtime/{agent_arn.strip()}"
                escaped_arn = urllib.parse.quote(full_arn, safe='')
                url = f"https://bedrock-agentcore.{REGION_NAME}.amazonaws.com/runtimes/{escaped_arn}/invocations?qualifier=DEFAULT"
            
            if verbose:
                print(f"🔄 Retrying with updated ARN: {agent_arn}")
            # Retry with Bearer first
            headers["X-Amzn-Trace-Id"] = secrets.token_hex(17)
            response = requests.post(url, headers=headers, data=payload, stream=True)
            
            # If still auth mismatch, try SigV4
            if response.status_code == 403 and "Authorization method mismatch" in response.text:
                session = boto3.Session(region_name=REGION_NAME)
                credentials = session.get_credentials().get_frozen_credentials()
                sigv4_headers = {
                    "Content-Type": "application/json",
                    "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
                    "X-Amzn-Trace-Id": secrets.token_hex(17)
                }
                aws_request = AWSRequest(method='POST', url=url, data=payload, headers=sigv4_headers)
                SigV4Auth(credentials, 'bedrock-agentcore', REGION_NAME).add_auth(aws_request)
                response = requests.post(url, headers=dict(aws_request.headers), data=payload, stream=True)
    
    if response.status_code != 200:
        raise Exception(f"Agent invocation failed with status {response.status_code}: {response.text}")
    
    # Collect streaming response
    content = []
    for line in response.iter_lines():
        if line:
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                data_str = line_str[6:]
                try:
                    event_data = json.loads(data_str)
                    if isinstance(event_data, str):
                        if verbose:
                            print(event_data, end='', flush=True)
                        content.append(event_data)
                    elif isinstance(event_data, dict) and 'data' in event_data:
                        chunk = event_data['data']
                        if verbose:
                            print(chunk, end='', flush=True)
                        content.append(chunk)
                except json.JSONDecodeError:
                    if verbose:
                        print(data_str, end='', flush=True)
                    content.append(data_str)
    
    return "".join(content)

def main():
    """Main function for CLI usage."""
    # Initialize configuration
    try:
        init_config(verbose=True)
    except Exception:
        exit(1)
    
    # Get Cognito token
    try:
        auth_token = get_cognito_token()
        print("✅ Successfully obtained Cognito token")
    except Exception as e:
        print(f"❌ Failed to get Cognito token: {e}")
        exit(1)
    
    # Parse arguments for session ID and prompt
    session_id = None
    prompt = None
    
    args = sys.argv[1:]
    if "--session-id" in args:
        idx = args.index("--session-id")
        if idx + 1 < len(args):
            session_id = args[idx + 1]
            args = args[:idx] + args[idx+2:]
            print(f"Using provided session ID: {session_id}")
        else:
            print("⚠️  --session-id requires a value")
            exit(1)
    
    # Remaining args are the prompt
    if args:
        prompt = " ".join(args)
    else:
        prompt = "I had oatmeal with berries for breakfast at 8am"
    
    # Generate session ID if not provided
    if not session_id:
        session_id = secrets.token_hex(20)
        print(f"Generated new session ID: {session_id}")
    
    print(f"\n💬 Prompt: {prompt}\n")
    
    # Invoke agent
    try:
        print("=== Agent Response ===\n")
        response = invoke_agent(prompt, session_id, auth_token, verbose=True)
        print("\n\n=== End of Response ===")
        
        if response:
            print(f"\n✅ Received {len(response)} characters")
            print(f"💾 Session ID: {session_id}")
            print(f"\n💡 To continue this conversation, use:")
            print(f"   python invoke_agent.py --session-id {session_id} \"your next message\"")
        else:
            print("\n⚠️  No content received from stream")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
