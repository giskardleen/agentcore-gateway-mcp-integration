#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Simple agent that connects to AgentCore Gateway and uses Lambda tools.

This script:
1. Retrieves gateway configuration from SSM and Secrets Manager
2. Authenticates with Cognito to get access token
3. Connects to gateway via MCP client
4. Lists available tools and invokes them

Usage: python test_gateway.py
"""
import boto3
import json
import os
import logging
import requests
from strands.models import BedrockModel
from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp.mcp_client import MCPClient
from strands import Agent

REGION = os.getenv("AWS_REGION", "us-east-1")

# Configure logging
logging.getLogger("strands").setLevel(logging.INFO)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()]
)


def get_ssm_parameter(parameter_name):
    """Retrieve parameter from SSM Parameter Store."""
    ssm = boto3.client('ssm', region_name=REGION)
    try:
        response = ssm.get_parameter(Name=parameter_name)
        return response['Parameter']['Value']
    except Exception as e:
        print(f"❌ Error retrieving {parameter_name}: {e}")
        raise


def get_secret(secret_name):
    """Retrieve secret from Secrets Manager."""
    secrets = boto3.client('secretsmanager', region_name=REGION)
    try:
        response = secrets.get_secret_value(SecretId=secret_name)
        return json.loads(response['SecretString'])
    except Exception as e:
        print(f"❌ Error retrieving {secret_name}: {e}")
        raise


def get_cognito_token(user_pool_id, client_id, client_secret):
    """Get access token from Cognito using client credentials flow."""
    # Get Cognito domain
    cognito = boto3.client('cognito-idp', region_name=REGION)
    try:
        response = cognito.describe_user_pool(UserPoolId=user_pool_id)
        domain = response['UserPool'].get('Domain')

        if not domain:
            print("❌ User pool does not have a domain configured")
            print("💡 Create a domain in Cognito console: User Pools > Your Pool > App Integration > Domain")
            raise ValueError("Cognito domain not configured")

        # Request token
        token_url = f"https://{domain}.auth.{REGION}.amazoncognito.com/oauth2/token"

        response = requests.post(
            token_url,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'grant_type': 'client_credentials',
                'client_id': client_id,
                'client_secret': client_secret,
                'scope': 'personal-agent-gateway-id/gateway:read personal-agent-gateway-id/gateway:write'
            }
        )

        if response.status_code != 200:
            print(f"❌ Token request failed: {response.text}")
            raise ValueError(f"Failed to get token: {response.status_code}")

        token_data = response.json()
        return token_data['access_token']

    except Exception as e:
        print(f"❌ Error getting Cognito token: {e}")
        raise


def create_streamable_http_transport(gateway_url, token):
    """Create HTTP transport for MCP client."""
    return streamablehttp_client(
        gateway_url,
        headers={"Authorization": f"Bearer {token}"}
    )


def main():
    """Main function to run the agent."""
    print("=" * 80)
    print("PERSONAL AGENT - GATEWAY CLIENT")
    print("=" * 80)

    # Step 1: Retrieve configuration
    print("\n📋 Retrieving configuration from AWS...")
    gateway_id = get_ssm_parameter('/personal-agent/gateway/id')
    gateway_url = get_ssm_parameter('/personal-agent/gateway/url')
    user_pool_id = get_ssm_parameter('/personal-agent/cognito/user-pool-id')
    credentials = get_secret('/personal-agent/cognito/client-credentials')

    client_id = credentials['client_id']
    client_secret = credentials['client_secret']

    print(f"   ✅ Gateway URL: {gateway_url}")
    print(f"   ✅ User Pool ID: {user_pool_id}")

    # Step 2: Get Cognito token
    print("\n🔐 Authenticating with Cognito...")
    token = get_cognito_token(user_pool_id, client_id, client_secret)
    print("   ✅ Access token obtained")

    # Step 3: Create MCP client
    print("\n🔌 Connecting to gateway...")
    client = MCPClient(lambda: create_streamable_http_transport(gateway_url, token))

    # Step 4: Create Bedrock model
    model = BedrockModel(
        model_id="us.amazon.nova-pro-v1:0",
        temperature=0.7
    )

    # Step 5: List tools and create agent
    print("\n🛠️  Loading tools from gateway...")
    with client:
        tools = client.list_tools_sync()
        agent = Agent(model=model, tools=tools)

        print(f"   ✅ Tools loaded: {agent.tool_names}")

        # Discover actual tool names from the gateway
        tool_names = agent.tool_names
        print(f"   📋 Available tool names: {tool_names}")

        # Find the calorie and recipe tools by partial match
        calorie_tool = next((t for t in tool_names if 'calori' in t.lower()), None)
        recipe_tool = next((t for t in tool_names if 'recipe' in t.lower()), None)

        print(f"   🔍 Calorie tool: {calorie_tool}")
        print(f"   🔍 Recipe tool: {recipe_tool}")

        # Example interactions
        print("\n" + "=" * 80)
        print("AGENT INTERACTIONS")
        print("=" * 80)

        # List available tools
        print("\n1️⃣  Listing available tools...")
        try:
            response = agent("Hi, can you list all tools available to you?")
            print(f"   Response: {response}")
        except Exception as e:
            print(f"   ⚠️  Error: {e}")

        # Direct tool call - calculate calories
        print("\n2️⃣  Direct tool call - Calculate calories...")
        if calorie_tool:
            try:
                result = client.call_tool_sync(
                    tool_use_id="calculate-calories-call-1",
                    name=calorie_tool,
                    arguments={"meal_description": "oatmeal with berries, honey, and almond milk"}
                )
                raw = result['content'][0]['text']
                try:
                    parsed = json.loads(raw)
                    body = json.loads(parsed['body']) if isinstance(parsed.get('body'), str) else parsed.get('body', parsed)
                    print(f"   ✅ Status: {parsed.get('statusCode', 'N/A')}")
                    print(f"   Foods: {body.get('foods', 'N/A')}")
                    print(f"\n{body.get('estimate', raw)}")
                except (json.JSONDecodeError, KeyError):
                    print(f"   Tool result: {raw[:300]}...")
            except Exception as e:
                print(f"   ⚠️  Error: {e}")
        else:
            print("   ⚠️  Calorie tool not found in gateway tools")

        # Direct tool call - suggest recipes
        print("\n3️⃣  Direct tool call - Suggest recipes...")
        if recipe_tool:
            try:
                result = client.call_tool_sync(
                    tool_use_id="suggest-recipes-call-1",
                    name=recipe_tool,
                    arguments={"dietary_preferences": "vegetarian, high protein, quick meals under 30 minutes"}
                )
                raw = result['content'][0]['text']
                try:
                    parsed = json.loads(raw)
                    body = json.loads(parsed['body']) if isinstance(parsed.get('body'), str) else parsed.get('body', parsed)
                    print(f"   ✅ Status: {parsed.get('statusCode', 'N/A')}")
                    print(f"   Preferences: {body.get('preferences', 'N/A')}")
                    print(f"\n{body.get('recipes', raw)}")
                except (json.JSONDecodeError, KeyError):
                    print(f"   Tool result: {raw[:300]}...")
            except Exception as e:
                print(f"   ⚠️  Error: {e}")
        else:
            print("   ⚠️  Recipe tool not found in gateway tools")

        print("\n✅ All interactions complete!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
