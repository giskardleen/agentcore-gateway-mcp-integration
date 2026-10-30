from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp.mcp_client import MCPClient
import os
import boto3
import json
import requests

def get_gateway_config():
    """Retrieve gateway configuration from SSM and Secrets Manager."""
    region = os.getenv("AWS_REGION", "us-west-2")
    ssm = boto3.client('ssm', region_name=region)
    secrets = boto3.client('secretsmanager', region_name=region)

    try:
        gateway_url = ssm.get_parameter(
            Name='/personal-agent/gateway/url'
        )['Parameter']['Value']

        credentials = json.loads(secrets.get_secret_value(
            SecretId='/personal-agent/cognito/client-credentials'
        )['SecretString'])

        user_pool_id = ssm.get_parameter(
            Name='/personal-agent/cognito/user-pool-id'
        )['Parameter']['Value']

        return {
            'gateway_url': gateway_url,
            'client_id': credentials['client_id'],
            'client_secret': credentials['client_secret'],
            'user_pool_id': user_pool_id
        }
    except Exception as e:
        print(f"Failed to get gateway config: {e}")
        return None

def get_gateway_token(config):
    """Get access token for gateway using client credentials flow."""
    region = os.getenv("AWS_REGION", "us-west-2")
    cognito = boto3.client('cognito-idp', region_name=region)

    try:
        response = cognito.describe_user_pool(UserPoolId=config['user_pool_id'])
        domain = response['UserPool'].get('Domain')

        if not domain:
            print("Cognito domain not configured")
            return None

        token_url = f"https://{domain}.auth.{region}.amazoncognito.com/oauth2/token"

        response = requests.post(
            token_url,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'grant_type': 'client_credentials',
                'client_id': config['client_id'],
                'client_secret': config['client_secret'],
                'scope': 'personal-agent-gateway-id/gateway:read personal-agent-gateway-id/gateway:write'
            }
        )

        if response.status_code == 200:
            return response.json()['access_token']
        else:
            print(f"Failed to get token: {response.text}")
            return None
    except Exception as e:
        print(f"Error getting gateway token: {e}")
        return None

def get_streamable_http_mcp_client() -> MCPClient:
    """
    Returns an MCP Client compatible with Strands.

    Tries to connect to AgentCore Gateway first, falls back to example endpoint.
    """
    EXAMPLE_MCP_ENDPOINT = "https://mcp.exa.ai/mcp"

    config = get_gateway_config()

    if config:
        token = get_gateway_token(config)
        if token:
            print(f"Using AgentCore Gateway: {config['gateway_url']}")
            return MCPClient(lambda: streamablehttp_client(
                config['gateway_url'],
                headers={"Authorization": f"Bearer {token}"}
            ))

    print(f"Gateway not configured, using example endpoint: {EXAMPLE_MCP_ENDPOINT}")
    return MCPClient(lambda: streamablehttp_client(EXAMPLE_MCP_ENDPOINT))
