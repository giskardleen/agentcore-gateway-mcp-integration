# AgentCore Gateway MCP Integration

A documented implementation and validation study of integrating a Strands-based AI agent with remote tools through Amazon Bedrock AgentCore Gateway and the Model Context Protocol (MCP).

## Overview

This project was developed during the AWS Skill Builder lab **Integrate Agents with MCP Servers and Tools using AgentCore Gateway**.

The exercise demonstrates how an AI agent can discover and invoke tools exposed through an MCP-compatible gateway, using OAuth 2.0 client credentials for gateway authentication.

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
        |   (access token)
        |
        v
    AgentCore Gateway
        |
        |-- calculate_calories --> AWS Lambda --> Amazon Bedrock
        |
        |-- suggest_recipes   --> AWS Lambda --> Amazon Bedrock
```

The MCP client authenticates with Amazon Cognito and uses the resulting access token to communicate with AgentCore Gateway. The Gateway exposes two Lambda-backed tools that invoke Amazon Bedrock for calorie estimation and recipe suggestions.

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

Gateway tool discovery and direct tool invocation were validated. AgentCore Runtime invocation also succeeded.

Session ID reuse was tested, but persistent conversational memory was not independently demonstrated.

### Validation Evidence

Detailed validation results, observed behavior, execution metrics, and verification limitations are documented in [Validation Results](docs/validation-results.md).

The validation distinguishes confirmed infrastructure and tool execution from agent-generated claims that were not independently verified.

## Cost Analysis

The project includes a [Telemetry-Informed Production Cost Projection](docs/telemetry-informed-production-cost-projection.md) based on observed Lambda execution durations, aggregate Amazon Bedrock token metrics, workload assumptions, and estimated AWS pricing.

The projection distinguishes observed measurements from assumptions and modeled costs. It is not an AWS billing statement.

## Repository Scope

This repository publicly documents the architecture, implementation process, validation results, and cost analysis of the AgentCore Gateway MCP integration lab.

The original executable implementation and lab scripts have been preserved separately in a private Git snapshot. The AWS-provided starter code is not redistributed here because explicit redistribution permissions were not established.

The documentation describes the implementation that was executed and tested; it does not claim that this public repository is a standalone deployable application.

## References

- [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Strands Agents](https://strandsagents.com/)
- [AWS AgentCore CLI](https://github.com/aws/agentcore-cli)
