#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Create Amazon Bedrock AgentCore Gateway with Cognito authorization.

This script:
1. Retrieves existing Cognito User Pool for authorization
2. Creates resource server and M2M client
3. Creates AgentCore Gateway with Cognito authorizer (using pre-created IAM role)
4. Creates Lambda targets for nutrition tools

Usage: python scripts/create-gateway.py
"""

import boto3
import os
import json
import time
from botocore.exceptions import ClientError

REGION = os.getenv("AWS_REGION", "us-east-1")
USER_POOL_NAME = "PersonalAgentUserPool"
RESOURCE_SERVER_ID = "personal-agent-gateway-id"
RESOURCE_SERVER_NAME = "personal-agent-gateway-name"
CLIENT_NAME = "personal-agent-gateway-client"
GATEWAY_NAME = "PersonalAgentGateway"
GATEWAY_ROLE_NAME = "PersonalAgentGatewayRole"

SCOPES = [
    {"ScopeName": "gateway:read", "ScopeDescription": "Read access"},
    {"ScopeName": "gateway:write", "ScopeDescription": "Write access"}
]

# Lambda functions to expose via gateway
LAMBDA_TOOLS = [
    {
        "name": "calculatecalories",
        "function_name": "calculate-calories",
        "arn_env": "CALCULATE_CALORIES_LAMBDA_ARN",
        "tools": [
            {
                "name": "calculate_calories",
                "description": "Estimate calorie content of foods",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "meal_description": {
                            "type": "string",
                            "description": "Description of the meal to analyze"
                        }
                    },
                    "required": ["meal_description"]
                }
            }
        ]
    },
    {
        "name": "suggestrecipes",
        "function_name": "suggest-recipes",
        "arn_env": "SUGGEST_RECIPES_LAMBDA_ARN",
        "tools": [
            {
                "name": "suggest_recipes",
                "description": "Suggest recipes based on dietary preferences",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "dietary_preferences": {
                            "type": "string",
                            "description": "Dietary preferences and requirements"
                        }
                    },
                    "required": ["dietary_preferences"]
                }
            }
        ]
    }
]


def get_or_create_user_pool(cognito, pool_name):
    """Get existing user pool or create new one."""
    try:
        response = cognito.list_user_pools(MaxResults=60)
        for pool in response.get('UserPools', []):
            if pool['Name'] == pool_name:
                print(f"   ℹ️  User pool already exists: {pool['Id']}")
                return pool['Id']

        print(f"   📋 Creating user pool: {pool_name}")
        response = cognito.create_user_pool(
            PoolName=pool_name,
            Policies={
                'PasswordPolicy': {
                    'MinimumLength': 8,
                    'RequireUppercase': False,
                    'RequireLowercase': False,
                    'RequireNumbers': False,
                    'RequireSymbols': False
                }
            }
        )
        pool_id = response['UserPool']['Id']
        print(f"   ✅ Created user pool: {pool_id}")
        return pool_id
    except ClientError as e:
        print(f"   ❌ Error with user pool: {e}")
        raise


def ensure_user_pool_domain(cognito, user_pool_id, domain_prefix):
    """Ensure user pool has a domain configured."""
    try:
        response = cognito.describe_user_pool(UserPoolId=user_pool_id)
        existing_domain = response['UserPool'].get('Domain')
        if existing_domain:
            print(f"   ℹ️  Domain already exists: {existing_domain}")
            return existing_domain

        print(f"   📋 Creating domain: {domain_prefix}")
        cognito.create_user_pool_domain(
            Domain=domain_prefix,
            UserPoolId=user_pool_id
        )
        print(f"   ✅ Created domain: {domain_prefix}")
        return domain_prefix
    except ClientError as e:
        if e.response['Error']['Code'] == 'InvalidParameterException':
            domain_prefix_alt = f"{domain_prefix}-{int(time.time())}"
            print(f"   ⚠️  Domain taken, trying: {domain_prefix_alt}")
            cognito.create_user_pool_domain(
                Domain=domain_prefix_alt,
                UserPoolId=user_pool_id
            )
            print(f"   ✅ Created domain: {domain_prefix_alt}")
            return domain_prefix_alt
        else:
            print(f"   ❌ Error with domain: {e}")
            raise


def get_or_create_resource_server(cognito, user_pool_id, server_id, server_name, scopes):
    """Get existing resource server or create new one."""
    try:
        try:
            cognito.describe_resource_server(
                UserPoolId=user_pool_id,
                Identifier=server_id
            )
            print(f"   ℹ️  Resource server already exists")
            return
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceNotFoundException':
                raise

        print(f"   📋 Creating resource server: {server_name}")
        cognito.create_resource_server(
            UserPoolId=user_pool_id,
            Identifier=server_id,
            Name=server_name,
            Scopes=scopes
        )
        print(f"   ✅ Created resource server")
    except ClientError as e:
        print(f"   ❌ Error with resource server: {e}")
        raise


def get_or_create_m2m_client(cognito, user_pool_id, client_name, resource_server_id):
    """Get existing M2M client or create new one."""
    try:
        response = cognito.list_user_pool_clients(
            UserPoolId=user_pool_id,
            MaxResults=60
        )
        for client in response.get('UserPoolClients', []):
            if client['ClientName'] == client_name:
                client_details = cognito.describe_user_pool_client(
                    UserPoolId=user_pool_id,
                    ClientId=client['ClientId']
                )
                print(f"   ℹ️  Client already exists: {client['ClientId']}")
                return client['ClientId'], client_details['UserPoolClient'].get('ClientSecret')

        print(f"   📋 Creating M2M client: {client_name}")
        response = cognito.create_user_pool_client(
            UserPoolId=user_pool_id,
            ClientName=client_name,
            GenerateSecret=True,
            AllowedOAuthFlows=['client_credentials'],
            AllowedOAuthScopes=[
                f"{resource_server_id}/gateway:read",
                f"{resource_server_id}/gateway:write"
            ],
            AllowedOAuthFlowsUserPoolClient=True
        )
        client_id = response['UserPoolClient']['ClientId']
        client_secret = response['UserPoolClient']['ClientSecret']
        print(f"   ✅ Created client: {client_id}")
        return client_id, client_secret
    except ClientError as e:
        print(f"   ❌ Error with client: {e}")
        raise


def get_gateway_role_arn():
    """Get the pre-created PersonalAgentGatewayRole ARN."""
    iam = boto3.client('iam')
    try:
        response = iam.get_role(RoleName=GATEWAY_ROLE_NAME)
        role_arn = response['Role']['Arn']
        print(f"   ✅ Using existing role: {role_arn}")
        return role_arn
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchEntity':
            print(f"   ❌ Role '{GATEWAY_ROLE_NAME}' not found. Please ensure it is pre-created.")
            raise
        raise


def add_gateway_access_to_agent_role():
    """Attach the pre-created GatewayAccessPolicy managed policy to BedrockAgentCoreExecutionRole."""
    iam = boto3.client('iam')
    sts = boto3.client('sts')
    account_id = sts.get_caller_identity()['Account']
    policy_arn = f"arn:aws:iam::{account_id}:policy/GatewayAccessPolicy"

    try:
        print(f"\n📋 Attaching GatewayAccessPolicy to BedrockAgentCoreExecutionRole...")
        iam.attach_role_policy(
            RoleName="BedrockAgentCoreExecutionRole",
            PolicyArn=policy_arn
        )
        print(f"   ✅ Attached GatewayAccessPolicy (SSM, Secrets Manager, and Cognito permissions)")
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchEntity':
            print(f"   ⚠️  BedrockAgentCoreExecutionRole or GatewayAccessPolicy not found")
        else:
            print(f"   ⚠️  Error attaching policy: {e}")


def ensure_cdk_permissions_boundary():
    """Ensure CDK context has permissions boundary set for all IAM roles."""
    import glob
    import pathlib

    # Look for cdk.json in expected locations
    home = pathlib.Path.home()
    candidates = [
        home / "agentcore-runtime-quickstart" / "personalAgent" / "agentcore" / "cdk" / "cdk.json",
    ]
    # Also search for any cdk.json under the project
    candidates.extend(pathlib.Path(home / "agentcore-runtime-quickstart").rglob("cdk.json"))

    boundary_name = "CDKBootstrapPolicyAndBoundary"
    found = False

    for cdk_json_path in candidates:
        if not cdk_json_path.exists():
            continue
        found = True
        try:
            with open(cdk_json_path) as f:
                cfg = json.load(f)

            ctx = cfg.get("context", {})
            existing = ctx.get("@aws-cdk/core:permissionsBoundary", {})

            if existing.get("name") == boundary_name:
                print(f"   ℹ️  Permissions boundary already set in {cdk_json_path}")
                continue

            # Add it
            ctx["@aws-cdk/core:permissionsBoundary"] = {"name": boundary_name}
            cfg["context"] = ctx

            with open(cdk_json_path, "w") as f:
                json.dump(cfg, f, indent=2)

            print(f"   ✅ Injected permissions boundary into {cdk_json_path}")
        except Exception as e:
            print(f"   ⚠️  Error updating {cdk_json_path}: {e}")

    if not found:
        print(f"   ⚠️  No cdk.json found — permissions boundary not set")


def create_gateway(gateway_client, role_arn, client_id, discovery_url):
    """Create AgentCore Gateway with Cognito authorizer, or retrieve existing one."""
    auth_config = {
        "customJWTAuthorizer": {
            "allowedClients": [client_id],
            "discoveryUrl": discovery_url
        }
    }

    try:
        print(f"\n🚀 Creating gateway: {GATEWAY_NAME}")
        response = gateway_client.create_gateway(
            name=GATEWAY_NAME,
            roleArn=role_arn,
            protocolType='MCP',
            authorizerType='CUSTOM_JWT',
            authorizerConfiguration=auth_config,
            description='Personal Agent Gateway with Lambda targets'
        )
        gateway_id = response['gatewayId']
        gateway_url = response['gatewayUrl']
        print(f"   ✅ Gateway created")
        print(f"   Gateway ID: {gateway_id}")
        print(f"   Gateway URL: {gateway_url}")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConflictException':
            print(f"   ℹ️  Gateway already exists, retrieving...")
            paginator = gateway_client.get_paginator('list_gateways')
            for page in paginator.paginate():
                for gw in page.get('items', []):
                    if gw['name'] == GATEWAY_NAME:
                        gateway_id = gw['gatewayId']
                        status_response = gateway_client.get_gateway(
                            gatewayIdentifier=gateway_id
                        )
                        gateway_url = status_response['gatewayUrl']
                        print(f"   ✅ Found existing gateway")
                        print(f"   Gateway ID: {gateway_id}")
                        print(f"   Gateway URL: {gateway_url}")
                        return gateway_id, gateway_url
            raise Exception("Gateway exists but could not be found in list")
        else:
            print(f"   ❌ Error creating gateway: {e}")
            raise

    # Wait for gateway to be ready
    print(f"   ⏳ Waiting for gateway to be ready...")
    max_attempts = 60
    for attempt in range(max_attempts):
        try:
            status_response = gateway_client.get_gateway(
                gatewayIdentifier=gateway_id
            )
            status = status_response['status']
            if status in ['ACTIVE', 'READY']:
                print(f"   ✅ Gateway is ready")
                break
            elif status == 'FAILED':
                raise Exception(f"Gateway creation failed")
            print(f"   ⏳ Status: {status}, waiting... ({attempt + 1}/{max_attempts})")
            time.sleep(5)
        except ClientError as e:
            if attempt == max_attempts - 1:
                raise
            time.sleep(5)
    else:
        raise Exception("Gateway did not become ready in time")

    return gateway_id, gateway_url


def get_lambda_arn(function_name):
    """Get Lambda function ARN by name."""
    lambda_client = boto3.client('lambda', region_name=REGION)
    try:
        response = lambda_client.get_function(FunctionName=function_name)
        return response['Configuration']['FunctionArn']
    except ClientError as e:
        print(f"   ⚠️  Could not find Lambda function {function_name}: {e}")
        return None


def create_lambda_target(gateway_client, gateway_id, lambda_config):
    """Create Lambda target in gateway."""
    lambda_arn = os.getenv(lambda_config['arn_env'])
    if not lambda_arn:
        fn_name = lambda_config.get('function_name', lambda_config['name'])
        print(f"\n🔧 Looking up Lambda ARN for: {fn_name}")
        lambda_arn = get_lambda_arn(fn_name)

    if not lambda_arn:
        print(f"   ⚠️  Skipping {lambda_config['name']}: Lambda function not found")
        return None

    target_config = {
        "mcp": {
            "lambda": {
                "lambdaArn": lambda_arn,
                "toolSchema": {
                    "inlinePayload": lambda_config['tools']
                }
            }
        }
    }

    credential_config = [
        {"credentialProviderType": "GATEWAY_IAM_ROLE"}
    ]

    try:
        print(f"   📦 Creating Lambda target: {lambda_config['name']}")
        response = gateway_client.create_gateway_target(
            gatewayIdentifier=gateway_id,
            name=lambda_config['name'],
            description=f"Lambda target for {lambda_config['name']}",
            targetConfiguration=target_config,
            credentialProviderConfigurations=credential_config
        )
        print(f"   ✅ Target created")
        return response
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConflictException':
            print(f"   ℹ️  Target already exists: {lambda_config['name']}")
            return None
        else:
            print(f"   ❌ Error creating target: {e}")
            raise


def store_parameters(gateway_id, gateway_url, user_pool_id, client_id, client_secret):
    """Store gateway configuration in SSM and Secrets Manager."""
    ssm = boto3.client('ssm', region_name=REGION)
    secrets = boto3.client('secretsmanager', region_name=REGION)

    print("\n💾 Storing configuration...")

    # Store in SSM Parameter Store
    ssm_params = {
        '/personal-agent/gateway/id': gateway_id,
        '/personal-agent/gateway/url': gateway_url,
        '/personal-agent/cognito/user-pool-id': user_pool_id
    }

    for param_name, param_value in ssm_params.items():
        try:
            ssm.put_parameter(
                Name=param_name,
                Value=param_value,
                Type='String',
                Overwrite=True
            )
            print(f"   ✅ Stored SSM parameter: {param_name}")
        except ClientError as e:
            print(f"   ⚠️  Error storing {param_name}: {e}")

    # Store credentials in Secrets Manager
    secret_name = '/personal-agent/cognito/client-credentials'
    secret_value = {
        'client_id': client_id,
        'client_secret': client_secret
    }

    try:
        try:
            secrets.create_secret(
                Name=secret_name,
                SecretString=json.dumps(secret_value),
                Description='Cognito client credentials for Personal Agent Gateway'
            )
            print(f"   ✅ Created secret: {secret_name}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceExistsException':
                secrets.update_secret(
                    SecretId=secret_name,
                    SecretString=json.dumps(secret_value)
                )
                print(f"   ✅ Updated secret: {secret_name}")
            else:
                raise
    except ClientError as e:
        print(f"   ⚠️  Error storing secret: {e}")


def main():
    """Main gateway creation function."""
    print("=" * 80)
    print("AGENTCORE GATEWAY DEPLOYMENT")
    print("=" * 80)

    cognito = boto3.client("cognito-idp", region_name=REGION)
    gateway_client = boto3.client('bedrock-agentcore-control', region_name=REGION)

    # Step 1: Cognito setup
    print("\n📋 Setting up Cognito authorization...")
    user_pool_id = get_or_create_user_pool(cognito, USER_POOL_NAME)
    domain = ensure_user_pool_domain(cognito, user_pool_id, "personal-agent-gateway")
    get_or_create_resource_server(cognito, user_pool_id, RESOURCE_SERVER_ID, RESOURCE_SERVER_NAME, SCOPES)
    client_id, client_secret = get_or_create_m2m_client(cognito, user_pool_id, CLIENT_NAME, RESOURCE_SERVER_ID)
    discovery_url = f'https://cognito-idp.{REGION}.amazonaws.com/{user_pool_id}/.well-known/openid-configuration'

    print(f"\n   User Pool ID: {user_pool_id}")
    print(f"   Client ID: {client_id}")
    print(f"   Discovery URL: {discovery_url}")

    # Step 2: Get pre-created gateway role
    print(f"\n📋 Retrieving gateway IAM role...")
    role_arn = get_gateway_role_arn()

    # Step 2.5: Add gateway access to agent execution role
    add_gateway_access_to_agent_role()

    # Step 2.6: Ensure CDK permissions boundary is configured
    print(f"\n📋 Checking CDK permissions boundary...")
    ensure_cdk_permissions_boundary()

    # Step 3: Create gateway
    gateway_id, gateway_url = create_gateway(gateway_client, role_arn, client_id, discovery_url)

    # Step 4: Create Lambda targets
    print("\n🔧 Creating Lambda targets...")
    for lambda_config in LAMBDA_TOOLS:
        create_lambda_target(gateway_client, gateway_id, lambda_config)

    # Step 5: Store configuration
    store_parameters(gateway_id, gateway_url, user_pool_id, client_id, client_secret)

    # Print summary
    print("\n" + "=" * 80)
    print("DEPLOYMENT SUMMARY")
    print("=" * 80)
    print(f"\nGateway ID: {gateway_id}")
    print(f"Gateway URL: {gateway_url}")
    print(f"User Pool ID: {user_pool_id}")
    print(f"Client ID: {client_id}")
    if client_secret:
        print("Cognito client secret configured successfully.")
    print("\n📍 Configuration stored in:")
    print("   SSM Parameters: /personal-agent/gateway/* and /personal-agent/cognito/user-pool-id")
    print("   Secrets Manager: /personal-agent/cognito/client-credentials")
    print("\n✅ Gateway deployment complete!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Deployment failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
