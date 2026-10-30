# Validation Results — AgentCore Gateway MCP Integration

**Project:** AgentCore Gateway MCP Integration  
**Lab:** AWS Skill Builder — *Integrate Agents with MCP Servers and Tools using AgentCore Gateway*  
**Environment:** Temporary AWS educational lab, `us-west-2`  
**Validation date:** 2026-10-30  
**Evidence type:** Recorded command outputs and observed agent responses  
**Status:** Completed lab validation, with explicitly documented evidence limits

## 1. Validation Scope

This document records the outcomes of the completed lab. It distinguishes **directly verified infrastructure and tool behavior** from **agent responses that were observed but not independently traced**.

The tested integration consisted of a Strands-based personal nutrition agent hosted on Amazon Bedrock AgentCore Runtime, an MCP client connecting to AgentCore Gateway, and two Lambda-backed remote tools. Amazon Cognito supplied machine-to-machine OAuth credentials. The Lambda tools used Amazon Bedrock for model inference.

```text
User request
    |
    v
AgentCore Runtime -> Strands personalAgent
    |                  |
    |                  +-- local tool: log_meal
    |                  |
    |                  +-- MCP client -- OAuth 2.0 / Cognito
    |                                         |
    |                                         v
    |                                   AgentCore Gateway
    |                                         |
    |                        +----------------+----------------+
    |                        |                                 |
    |                        v                                 v
    |                  calculate_calories                 suggest_recipes
    |                        |                                 |
    |                        v                                 v
    |                     Lambda                            Lambda
    |                        |                                 |
    +------------------------+----------- Amazon Bedrock -----+
```

## 2. Gateway Validation

**Procedure:** Run the lab's `create-gateway.py` and `test_gateway.py` scripts.

| Check | Recorded result | Evidence strength |
|---|---|---|
| Gateway provisioning | `PersonalAgentGateway` reached `READY` | Direct provisioning output |
| Lambda target registration | `calculatecalories` and `suggestrecipes` reached `Ready` | Direct provisioning output |
| Cognito client-credentials authentication | Test script obtained an access token | Direct script execution |
| MCP tool discovery | `calculatecalories___calculate_calories` and `suggestrecipes___suggest_recipes` were discovered | Direct MCP client output |
| Calorie tool invocation | HTTP 200 response | Direct tool test |
| Recipe tool invocation | HTTP 200 response | Direct tool test |

**Interpretation:** The Gateway exposed both Lambda-backed tools to the MCP client, and direct invocations succeeded under the lab configuration. HTTP 200 confirms request-level success in these tests; it does not, by itself, establish semantic accuracy of nutritional estimates or recipes.

**Provisioning note:** A warning about an expected execution role or Gateway access policy appeared during setup. Subsequent direct Gateway tests succeeded. The warning was not investigated further because it did not block the prescribed validation path.

## 3. Agent Runtime Integration

**Procedure:** Update the MCP client implementation, configure the Runtime JWT authorizer, deploy the agent, update the SSM-stored Runtime ARN, and invoke the deployed agent with `invoke_agent.py`.

| Check | Recorded result | Evidence strength |
|---|---|---|
| MCP client configured for Gateway access | Integration code updated per lab instructions | Implementation step completed |
| Runtime authentication | Custom JWT authorizer configured | Deployment configuration |
| Runtime deployment | CloudFormation stack `AgentCore-personalAgent-default` deployed successfully | Deployment output |
| Runtime reference | SSM parameter updated with agent ARN | Configuration step completed |
| Agent invocation | Requests received natural-language responses | Direct invocation output |

**Interpretation:** The deployed Runtime was reachable and responded to the test prompts. These results support successful deployment and invocation; they do not independently prove which remote tool was called during every agent interaction.

## 4. End-to-End Interaction Tests

The following prompts were submitted through the lab's agent invocation script. The outcomes below describe the **observed agent responses**, not independent verification of each side effect.

| Scenario | Prompt / intent | Observed outcome | Boundary |
|---|---|---|---|
| Meal logging | Oatmeal with berries and honey for breakfast at 8 a.m. | Agent stated that the meal was logged | Persistence was not independently checked |
| Calorie estimation | Calories in oatmeal with berries and honey | Agent estimated approximately 350 kcal and described macronutrients | Numerical accuracy and tool trace not independently verified |
| Recipe suggestions | High-protein vegetarian lunch ideas | Agent returned three recipe suggestions | Response observed; tool trace not independently verified |
| Calorie-constrained recipes | Dinner recipes under 500 calories | Agent returned three recipes | Response observed; constraints not independently evaluated |
| Multi-intent request | Log chicken salad, estimate calories, suggest a snack | Agent stated the meal was logged and estimated approximately 350 kcal; suggestions were chicken-salad recipes rather than snacks | Partial intent satisfaction; persistence and tool trace unverified |
| Follow-up in reused session | Recommend dinner while staying under 2,000 daily calories | Agent requested that the user restate meal history | Session ID was reused; memory retrieval was not demonstrated |

### 4.1 Multi-tool behavior

The agent produced responses to prompts that would plausibly require a combination of local meal logging and remote nutritional tools. However, the captured evidence does **not** contain independent per-invocation traces sufficient to attribute every response to specific tool calls.

**Supported claim:** The deployed agent handled multi-intent requests and returned responses.  
**Unsupported stronger claim:** Every expected tool was invoked correctly in every scenario.

### 4.2 Session continuity versus memory

The same session identifier was reused for follow-up prompts. This verifies the **client-side session reuse**, not successful retention or retrieval of previous meal details. When asked for a daily calorie-aware dinner recommendation, the agent requested meal history again.

**Supported claim:** The invocation workflow reused a session ID.  
**Not demonstrated:** Reliable conversational recall or persistent meal-history retrieval.

### 4.3 Response-quality limitation

In the combined lunch-and-snack scenario, the agent responded with chicken-salad recipe suggestions instead of snack suggestions. This is a recorded intent-alignment limitation, not evidence that Gateway connectivity failed.

## 5. CloudWatch Telemetry Collected

These metrics were collected separately from the functional tests. They support the production-cost projection but are **not** a substitute for per-request tool traces.

### 5.1 Lambda metrics

**Source:** CloudWatch `AWS/Lambda` metrics, 2026-10-30 UTC, one-day aggregation.

| Function | Invocations | Average duration | Total duration | Errors |
|---|---:|---:|---:|---:|
| `calculate-calories` | 3 | 2,642.02 ms | 7,926.05 ms | 0 |
| `suggest-recipes` | 4 | 5,213.27 ms | 20,853.09 ms | 0 |
| **Combined** | **7** | **4,111.31 ms (weighted)** | **28,779.14 ms** | **0** |

Both functions were configured with 128 MB memory, x86_64 architecture, and a 30-second timeout. The sample is too small to establish production latency distributions or error rates.

### 5.2 Bedrock metrics

**Source:** CloudWatch `AWS/Bedrock` metrics, 2026-10-30 UTC, aggregated without model dimensions.

| Metric | Observed |
|---|---:|
| Invocations | 22 |
| Input tokens | 16,755 |
| Output tokens | 5,942 |
| Total tokens | 22,697 |
| Input share | 73.82% |
| Output share | 26.18% |

Because the query did not filter by model or application, the aggregate cannot conclusively be attributed solely to this agent or to Nova Lite. Nor can 22 model invocations be interpreted as 22 user requests.

See [Telemetry-Informed Production Cost Projection](telemetry-informed-production-cost-projection.md) for the separate workload assumptions, pricing assumptions, and cost extrapolation.

## 6. Evidence and Claim Boundaries

| Claim | Assessment |
|---|---|
| Gateway and both targets were ready | **Verified** by provisioning output |
| MCP discovery exposed two Lambda-backed tools | **Verified** by direct tool discovery |
| Both remote tools returned HTTP 200 | **Verified** by direct tests |
| AgentCore Runtime deployed and responded | **Verified** by deployment and invocation outputs |
| Every agent response used the intended remote tool | **Not independently verified** |
| Meal records persisted successfully | **Not independently verified** |
| Reusing a session ID preserved meal history | **Not demonstrated** |
| Production reliability or nutritional correctness | **Not established** by this lab |

## 7. Security and Publication Notes

- Do not commit raw Cognito client secrets, access tokens, Secrets Manager values, or unredacted execution logs.
- Resource identifiers, temporary account details, and environment-specific deployment state are intentionally excluded from the public repository.
- The original AWS-provided lab starter code is not reproduced in this public documentation pending confirmation of redistribution rights.
- Results describe a temporary educational environment, not a hardened production deployment.

## 8. Conclusion

The lab demonstrated successful **Gateway provisioning, MCP tool discovery, direct Lambda-backed tool invocation, Runtime deployment, and natural-language agent invocation**. It also exposed two meaningful evaluation boundaries: agent responses alone are insufficient proof of tool execution or state persistence, and session ID reuse does not establish conversational memory.

The collected Lambda and Bedrock metrics provide a small empirical baseline for the separate telemetry-informed cost projection. They should not be presented as production measurements.
