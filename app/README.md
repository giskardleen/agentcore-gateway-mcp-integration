# Personal Nutrition Agent Application

This directory contains the published application used in the AgentCore Gateway MCP integration lab. It is a Strands-based personal nutrition agent hosted through Amazon Bedrock AgentCore Runtime. The agent combines a local meal-logging tool with remote tools discovered through an MCP-compatible AgentCore Gateway.

The application is provided as an implementation reference. It depends on AWS resources and configuration created through the original hybrid lab workflow and is not a self-contained deployment package.

## Architecture

At runtime, `main.py` coordinates these components:

- `BedrockAgentCoreApp` exposes the Runtime entrypoint and streams response data.
- A Strands `Agent` provides model reasoning and tool orchestration.
- The local `log_meal` tool writes meal records to DynamoDB.
- A Strands `MCPClient` discovers remote tools from AgentCore Gateway over streamable HTTP.
- Amazon Cognito supplies an OAuth 2.0 client-credentials access token for Gateway requests.
- Amazon Bedrock provides inference through the configured Nova Pro inference profile.

The Gateway and its Lambda-backed tools are external resources. Their implementations are not contained in this directory.

## Entrypoint and Invocation Lifecycle

`main.py` creates a `BedrockAgentCoreApp` and registers the asynchronous `invoke(payload, context)` function with `@app.entrypoint`. Direct execution calls `app.run()`.

For each invocation, the entrypoint:

1. Reads and logs the Runtime session ID and assigns the fixed application user ID `default-user`.
2. Opens the module-level MCP client as a context manager.
3. Calls `list_tools_sync()` to discover the currently exposed MCP tools.
4. Creates a new Strands `Agent` with the configured model, system prompt, local `log_meal` tool, and discovered remote tools.
5. Extracts `prompt` from a dictionary payload, or uses a non-dictionary payload directly.
6. Streams the prompt through `agent.stream_async()` and yields string-valued `data` events to AgentCore Runtime.

The session ID is logged but is not supplied to Strands as conversation history. A new agent is constructed for every invocation.

## Strands Agent and Model

`model/load.py` returns a Strands `BedrockModel` configured with the cross-Region inference profile:

```text
us.amazon.nova-pro-v1:0
```

The system prompt defines a supportive personal nutrition coach and instructs the agent to use `log_meal` only when a user reports a specific meal with foods and a time.

`model/mantle_compat.py` contains an OpenAI Responses compatibility class for a Bedrock Mantle message-format issue. It is not imported by `main.py` or used by the active Nova Pro model path.

## Local Meal-Logging Tool

The `log_meal` Strands tool accepts:

- `meal_type`
- `foods`
- `time`
- an optional `feeling`

It writes a DynamoDB item containing the fixed user ID, a UTC timestamp, record type, date, and the supplied meal data. `infrastructure/load.py` lazily creates and reuses the DynamoDB table resource.

The application references an existing table; it does not create one. Successful meal persistence was not independently verified during the recorded validation.

## MCP Client and AgentCore Gateway

`mcp_client/client.py` loads Gateway configuration from AWS Systems Manager Parameter Store and AWS Secrets Manager:

| Configuration | Location |
|---|---|
| Gateway URL | SSM parameter `/personal-agent/gateway/url` |
| Cognito user pool ID | SSM parameter `/personal-agent/cognito/user-pool-id` |
| Cognito client ID and secret | Secrets Manager secret `/personal-agent/cognito/client-credentials` |

The client describes the Cognito user pool to obtain its configured domain, then requests a token from the pool's `/oauth2/token` endpoint using the OAuth 2.0 client-credentials grant. It requests these resource-server scopes:

```text
personal-agent-gateway-id/gateway:read
personal-agent-gateway-id/gateway:write
```

When a token is obtained, the MCP streamable HTTP transport sends it to the Gateway as a Bearer token. The entrypoint discovers the Gateway's available tools while the MCP connection is open and registers them alongside `log_meal`.

If Gateway configuration or token acquisition fails, the current implementation constructs an MCP client for `https://mcp.exa.ai/mcp` and prints a fallback message. The validation documentation does not establish that this fallback path was exercised.

## Configuration Dependencies

The application reads these environment variables:

| Variable | Required | Behavior |
|---|---|---|
| `AWS_REGION` | Environment-dependent | Region used by the AWS clients. Modules that provide a default use `us-west-2`. |
| `HEALTH_TRACKER_TABLE_NAME` | No | DynamoDB table name; defaults to `health-tracker`. |

`LOCAL_DEV`, which appeared in the original generated README, is not read by the published implementation.

The application references AWS resources that must already exist and be accessible to its credentials or Runtime execution role:

- The DynamoDB health-tracker table.
- The configured Amazon Bedrock Nova Pro inference profile and required model access.
- AgentCore Gateway and its remote tool targets.
- A Cognito user pool with a domain, resource server, and M2M application client.
- The SSM parameters and Secrets Manager secret listed above.
- IAM permissions and network access needed for the AWS and Gateway calls made by the code.

The repository does not contain a complete definition or provisioning workflow for these resources.

## Supporting Skill Fetcher

`skills/fetcher.py` implements helpers for resolving skill packages from S3 or Git into a temporary cache. The current `main.py` does not import the module, construct `AgentSkills`, or attach fetched skills to the agent. These helpers are therefore supporting code rather than active application behavior.

## Implementation and Validation Boundaries

- The application uses the fixed identity `default-user`; it does not derive an end-user identity from the Runtime context.
- Runtime session IDs are logged, but no stored message history is passed to the newly created Strands agent. Reusing a session ID did not demonstrate conversational memory in validation.
- MCP tools are rediscovered and the Strands agent is recreated for every invocation.
- The Gateway access token is obtained when the module-level MCP client is constructed; the application does not implement an explicit per-invocation token refresh path.
- The entrypoint does not explicitly validate a missing or malformed prompt before passing it to Strands.
- `log_meal` stores the current user ID on a function attribute, which is shared mutable process state.
- Validation confirmed direct Gateway tool discovery and invocation and successful Runtime responses. It did not independently trace the intended tool for every agent response, verify meal persistence, establish nutritional correctness, or demonstrate production reliability.

See [Validation Results](../docs/validation-results.md) for the recorded evidence and claim boundaries.
