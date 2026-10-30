# AgentCore Gateway MCP Integration

A documented implementation and validation study of integrating a Strands-based AI agent with remote tools through Amazon Bedrock AgentCore Gateway and the Model Context Protocol (MCP).

## Overview

This project was developed during the AWS Skill Builder lab **Integrate Agents with MCP Servers and Tools using AgentCore Gateway**.

The exercise demonstrates how an AI agent can discover and invoke tools exposed through an MCP-compatible gateway, using OAuth 2.0 client credentials for gateway access.

## Architecture

```text
User
  |
  v
AgentCore Runtime
  |
  v
Strands Agent
  |-- Local tool: log_meal
  |
  |-- MCP Client
        |
        |-- Cognito OAuth 2.0 / M2M
        v
    AgentCore Gateway
        |
        |-- calculate_calories --> AWS Lambda --> Amazon Bedrock
        |
        |-- suggest_recipes   --> AWS Lambda --> Amazon Bedrock
```

## Components

| Component | Responsibility |
|---|---|
| Amazon Bedrock AgentCore Runtime | Hosts the Strands agent |
| Strands Agents | Coordinates model reasoning and tool invocation |
| AgentCore Gateway | Exposes Lambda functions as MCP tools |
| Amazon Cognito | Issues OAuth 2.0 access tokens |
| AWS Lambda | Implements calorie estimation and recipe suggestions |
| Amazon Bedrock Nova Lite | Provides model inference |
| AWS Systems Manager / Secrets Manager | Stores configuration and credentials |

## Implementation and Validation

The lab included:

1. Creating an AgentCore Gateway with two Lambda targets.
2. Discovering and invoking MCP tools directly.
3. Integrating the MCP client into the Strands agent.
4. Configuring Runtime authentication and deploying the agent.
5. Testing natural-language requests and multi-tool interactions.
6. Collecting CloudWatch telemetry for a production cost projection.

Gateway tool discovery and direct tool invocation were validated. Agent Runtime invocation also succeeded.

Session ID reuse was tested, but persistent conversational memory was not independently demonstrated.

## Cost Analysis

The project includes a telemetry-informed production cost projection using observed Lambda durations and aggregate Amazon Bedrock token metrics.

The projection distinguishes observed measurements from workload assumptions and estimated AWS pricing.

See `docs/telemetry-informed-production-cost-projection.md` once published.

## Repository Scope

This repository documents the integration, architecture, validation results, and engineering analysis.

AWS-provided lab starter code and environment-specific deployment configuration are excluded from the public repository pending confirmation of redistribution permissions.

No live credentials or secrets are intended to be published.

## References

- [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Strands Agents](https://strandsagents.com/)
- [AWS AgentCore CLI](https://github.com/aws/agentcore-cli)
