# Integration Scripts Technical Reference

This directory contains three Python scripts used in the original hybrid AgentCore Gateway MCP implementation. They cover Gateway configuration, direct Gateway validation, and invocation of an already deployed AgentCore Runtime.

The scripts reflect interactions performed during the lab, but they are not a complete deployment pipeline. They rely on AWS resources, permissions, deployment state, and manual configuration managed outside this directory. Running them does not recreate the original environment.

## Relationship Between the Scripts

`create-gateway.py` configures the Cognito machine-to-machine authorization used by AgentCore Gateway, creates or reuses the Gateway, registers Lambda-backed tool targets, and stores configuration for later access. `test_gateway.py` consumes that stored configuration to connect directly to the Gateway and exercise its tools. `invoke_agent.py` follows a separate authentication path to invoke an AgentCore Runtime that must already be deployed and configured.

Conceptually, the original implementation used them in this order:

1. Gateway and target configuration with `create-gateway.py`.
2. Direct Gateway discovery and tool checks with `test_gateway.py`.
3. Separate Runtime configuration and deployment outside these scripts.
4. Runtime requests with `invoke_agent.py`.

This relationship describes the implementation, not a reproducible setup procedure.

## Region Configuration

All three scripts read `AWS_REGION`, but their defaults differ:

| Script | Default region |
|---|---|
| `create-gateway.py` | `us-east-1` |
| `test_gateway.py` | `us-east-1` |
| `invoke_agent.py` | `us-west-2` |

The recorded validation environment used `us-west-2`. The scripts expect the selected region to contain the corresponding resources and stored configuration; resources written in one region are not automatically visible to a script using another.

## `create-gateway.py`

### Purpose

Configures the Cognito client-credentials authorization and AgentCore Gateway used to expose two existing nutrition Lambda functions as MCP tools.

### Services and configuration

The script interacts with Amazon Cognito, AgentCore Gateway control-plane APIs, IAM, STS, Lambda, Systems Manager Parameter Store, and Secrets Manager. Its fixed resource names include:

- Cognito user pool `PersonalAgentUserPool`
- Cognito resource server `personal-agent-gateway-id`
- Cognito M2M client `personal-agent-gateway-client`
- Gateway `PersonalAgentGateway`
- Pre-existing IAM role `PersonalAgentGatewayRole`
- Lambda functions `calculate-calories` and `suggest-recipes`

The Lambda ARNs can instead be supplied through `CALCULATE_CALORIES_LAMBDA_ARN` and `SUGGEST_RECIPES_LAMBDA_ARN`. The functions themselves are not created by the script.

### Important operations and side effects

The script:

- Finds or creates the Cognito user pool, domain, resource server, scopes, and secret-bearing M2M client.
- Requires `PersonalAgentGatewayRole`; it fails if that role does not exist.
- Attempts to attach the account-managed `GatewayAccessPolicy` to `BedrockAgentCoreExecutionRole`. A missing role or policy produces a warning rather than terminating the script.
- Searches below `~/agentcore-runtime-quickstart` for AgentCore CDK `cdk.json` files and may write the `CDKBootstrapPolicyAndBoundary` permissions-boundary setting into them.
- Creates or reuses the custom-JWT-authorized MCP Gateway. When it creates a new Gateway, it polls for readiness; when it reuses an existing Gateway, it returns without readiness polling.
- Creates the `calculatecalories` and `suggestrecipes` Gateway targets. Existing target conflicts are left unchanged; a target is skipped if its Lambda cannot be resolved.
- Writes or overwrites `/personal-agent/gateway/id`, `/personal-agent/gateway/url`, and `/personal-agent/cognito/user-pool-id` in SSM Parameter Store.
- Creates or updates `/personal-agent/cognito/client-credentials` in Secrets Manager.

The inline tool schemas accept `meal_description` for calorie estimation and `dietary_preferences` for recipe suggestions. The script does not deploy the Lambda implementations or the AgentCore Runtime application.

## `test_gateway.py`

### Purpose

Connects directly to the configured AgentCore Gateway, verifies MCP tool discovery, and exercises the two Lambda-backed tools with fixed example inputs. It also creates a small Strands agent and asks it to describe its available tools.

### Inputs and authentication

The script reads the values produced by `create-gateway.py`:

- SSM `/personal-agent/gateway/id`
- SSM `/personal-agent/gateway/url`
- SSM `/personal-agent/cognito/user-pool-id`
- Secrets Manager `/personal-agent/cognito/client-credentials`

It uses the Cognito OAuth 2.0 client-credentials grant with the Gateway read and write scopes. The resulting access token is sent as a Bearer token on the MCP streamable HTTP connection.

### Operations and limitations

Within the MCP client connection, the script:

- Discovers the Gateway tools and supplies them to a Strands agent configured with `us.amazon.nova-pro-v1:0` and temperature `0.7`.
- Locates the calorie and recipe tools by partial name matching.
- Calls the calorie tool with an oatmeal example.
- Calls the recipe tool with vegetarian, high-protein, quick-meal preferences.

These are live Gateway, Lambda, and model interactions and can generate AWS usage. Recorded validation confirmed discovery of both Lambda-backed tools and HTTP 200 responses from the direct calls. Those responses do not establish the semantic accuracy of the nutritional output.

## `invoke_agent.py`

### Purpose

Sends a prompt to an AgentCore Runtime that has already been deployed. It is an invocation client, not a Runtime deployment or configuration script.

### Inputs and authentication

At import time, the script reads the test user's `username` and `password` from Secrets Manager secret `/personal-agent/cognito/test-user-credentials`. During initialization it reads:

- Runtime ARN from SSM `/personal-agent/agent-arn`
- Cognito application client ID from SSM `/personal-agent/cognito/client-id`

It obtains a user access token with Cognito `USER_PASSWORD_AUTH`. This is distinct from the client-credentials flow used by the application and `test_gateway.py` for Gateway access.

The invocation request first uses that token as a Bearer token. If the service returns the specific authorization-method-mismatch response, the script retries with AWS SigV4 credentials. It refreshes the Cognito token after an HTTP 401 response.

### Operations and side effects

The script:

- Sends a JSON `prompt` to the Runtime's streaming invocation endpoint.
- Supplies an `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id`, using a generated value unless `--session-id` is provided.
- Parses server-sent streaming data and prints response chunks.
- On a stale or invalid Runtime ARN, may run `agentcore status`, extract the current ARN, and overwrite `/personal-agent/agent-arn` in SSM before retrying.
- If Cognito rejects the stored test password, may read `/personal-agent/cognito/discovery-url`, derive the user pool ID, and reset the test user's permanent password with `admin_set_user_password` before retrying authentication.

The SSM parameters and test-user secret used by this script are not created by `create-gateway.py`. They depend on the separately managed Runtime authorizer, Cognito test-user configuration, and deployment state from the original hybrid workflow. The `agentcore` CLI and its local project state are also required for the optional ARN-discovery fallback.

The script permits reuse of a session ID, but validation showed only client-side session reuse. Reliable conversational recall or retrieval of prior meal details was not demonstrated.

## Implementation and Validation Boundaries

- The scripts assume AWS credentials with access to every API they call, but this directory does not define a complete IAM policy set.
- This directory has no independent dependency manifest or environment bootstrap procedure.
- Gateway creation depends on pre-existing IAM and Lambda resources.
- Runtime invocation depends on a separately deployed application, authorizer configuration, test user, and stored deployment references.
- The scripts perform live mutations and invocations; they are retained as implementation references rather than general production recommendations.
- Validation confirmed Gateway readiness, target discovery, direct tool responses, Runtime deployment, and natural-language Runtime responses in the original lab environment. It did not independently verify every agent-side tool call, meal persistence, conversational memory, nutritional correctness, or production behavior.

See [Validation Results](../docs/validation-results.md) for the recorded observations and their evidence boundaries.
