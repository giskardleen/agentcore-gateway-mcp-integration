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
| Amazon Bedrock Nova Pro | Provides model inference for the published Strands agent |
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

This repository is a technical implementation and validation reference for the AgentCore Gateway MCP integration lab. It includes the published [AgentCore Runtime application](app/README.md), [Gateway and Runtime integration scripts](lab-scripts/README.md), validation results, and telemetry-informed cost analysis.

The original implementation used a hybrid workflow: Python application code and scripts were combined with AWS resources, service configuration, and manual development-environment interactions that are not represented as a single deployment system in this repository.

The published code makes the implementation inspectable; it is not a tutorial, infrastructure-as-code template, or self-contained environment-recreation package. The validation documentation records what was observed in the completed lab and preserves the distinction between implementation behavior and independently verified outcomes.

The application configures the Amazon Nova Pro inference profile `us.amazon.nova-pro-v1:0`. The cost projection separately uses Amazon Nova Lite reference pricing as a modeling assumption; the recorded aggregate Bedrock telemetry was not isolated by model.

## References

- [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Strands Agents](https://strandsagents.com/)
- [AWS AgentCore CLI](https://github.com/aws/agentcore-cli)
