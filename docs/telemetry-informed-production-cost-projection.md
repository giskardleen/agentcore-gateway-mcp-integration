# Telemetry-Informed Production Cost Projection

**Version:** 1.0  
**Observation date:** 2026-10-30  
**Region:** `us-west-2`  
**System:** Nutrition Coach — AWS AgentCore Gateway + MCP guided lab  
**Classification:** Preliminary modeled subtotal, informed by development telemetry; **not actual AWS billed spend**.

## 1. Scope and architecture

```text
User request
    |
    v
AgentCore Runtime (Strands personalAgent / Bedrock model)
    |
    v
AgentCore Gateway (MCP, Cognito M2M)
    |-------------------------|
    v                         v
calculate-calories         suggest-recipes
Lambda (128 MB)            Lambda (128 MB)
    |                         |
    v                         v
Amazon Bedrock             Amazon Bedrock

Supporting services: Cognito, SSM Parameter Store, Secrets Manager,
CloudWatch; additional usage-dependent charges may apply.
```

This architecture was assembled in an AWS Skill Builder guided lab using AWS-provided starter resources and scripts. The exercise demonstrated Gateway discovery, direct MCP tool calls, agent invocation, and session-ID reuse. It did **not** establish that every intended tool executed during each agent response, or that session history was successfully retrieved.

## 2. Production workload assumptions

| Parameter | Assumption |
|---|---:|
| User requests per day | 10,000 |
| Days per month | 30 |
| User requests per month | 300,000 |
| Tool calls per user request | 1.5 |
| Tool calls per month | 450,000 |
| Aggregate model tokens per user request | 3,000 |
| Aggregate model tokens per month | 900,000,000 |
| Gateway ListTools operations | 1 per user request (300,000/month) |
| Lambda allocation | 3/7 calorie analysis; 4/7 recipe suggestions, based on observed sample |

**Token boundary:** 3,000 tokens per request is a user-defined production assumption covering *all* Bedrock calls triggered by that request, including agent reasoning and model calls inside Lambda tools. It is **not** a measured per-user-request average. If it excludes tool-side inference, Bedrock cost will be higher.

## 3. Development telemetry (observed)

### AWS Lambda

CloudWatch statistics for 2026-10-30 (UTC):

| Metric | `calculate-calories` | `suggest-recipes` |
|---|---:|---:|
| Invocations | 3 | 4 |
| Mean duration | 2,642.0167 ms | 5,213.2725 ms |
| Maximum duration | 2,688.42 ms | 6,135.23 ms |
| Errors | 0 | 0 |
| Configured memory | 128 MB | 128 MB |
| Architecture | x86_64 | x86_64 |
| Configured timeout | 30 s | 30 s |

Observed call-weighted mean duration: **4.1113 seconds**. The 30-second timeout is a configuration limit, not observed execution time. Only seven invocations were recorded, so these measurements are a development baseline, not a production latency benchmark.

### Amazon Bedrock

CloudWatch `AWS/Bedrock` metrics for 2026-10-30 (UTC), queried without model dimensions:

| Metric | Observed |
|---|---:|
| Invocations | 22 |
| Input tokens | 16,755 |
| Output tokens | 5,942 |
| Total tokens | 22,697 |
| Input share | 73.82% |
| Output share | 26.18% |
| Mean tokens per Bedrock invocation | 1,031.68 |

These metrics are **aggregated** and were not isolated by model ID, inference profile, Lambda, or Runtime. A Bedrock invocation is not equivalent to one user request. Consequently, they inform the *input/output split* but do not validate the assumption of 3,000 tokens per user request.

## 4. Pricing assumptions and calculation

Prices below are **reference rates carried forward from the working estimate**, not independently verified against a current regional price sheet or actual account billing. Confirm pricing, tier, inference profile, and applicable discounts before using this as a budget commitment.

| Component | Reference assumption | Calculation | USD/month |
|---|---|---|---:|
| Amazon Nova Lite input | $0.06 / 1M input tokens | 900M × (16,755 / 22,697) × $0.06 / 1M | $39.86 |
| Amazon Nova Lite output | $0.24 / 1M output tokens | 900M × (5,942 / 22,697) × $0.24 / 1M | $56.55 |
| AgentCore Runtime | Hypothetical Runtime v1 CPU/memory activity | Prior illustrative runtime model; **not telemetry-derived** | $30.26 |
| AgentCore Gateway | $0.005 / 1,000 operations | (450,000 InvokeTool + 300,000 ListTools) / 1,000 × $0.005 | $3.75 |
| Lambda compute | $0.0000166667 / GB-second | 450,000 × 0.125 GB × 4.1113057 s × rate | $3.85 |
| Lambda requests | $0.20 / 1M requests | 450,000 / 1M × $0.20 | $0.09 |
| Secrets Manager | $0.40 / secret-month | 1 secret | $0.40 |
| **Modeled subtotal** | | Sum before rounding | **$134.77** |

Lambda compute plus request cost, before rounding: **$3.9444/month**. Token cost, before rounding: **$96.4111/month**. Modeled subtotal before rounding: **$134.7654/month**.

**Exclusions:** Cognito pricing, SSM API/storage charges where applicable, Secrets Manager API requests, CloudWatch logs and metrics, network transfer, additional Runtime charges, and any other chargeable service usage. No free-tier allowance, credits, discounts, taxes, or savings plans are modeled.

## 5. Time-horizon projection (constant workload and prices)

| Horizon | Modeled subtotal |
|---|---:|
| 30 days | $134.77 |
| 12 months | $1,617.18 |
| 36 months | $4,851.56 |

Values use the unrounded monthly subtotal and are **not** total cost of ownership. They exclude engineering labor, support, incident response, maintenance, and all unquantified AWS charges. No growth or price changes are assumed.

## 6. Evidence, assumptions, and interpretation boundaries

**Observed:** Two Lambda configurations (128 MB, x86_64, 30-second timeout); three calorie-function invocations; four recipe-function invocations; zero Lambda errors; average durations; 22 aggregated Bedrock invocations; 16,755 input tokens; 5,942 output tokens.

**Inferred / extrapolated:** Future distribution of Lambda tool calls, input/output token proportions, and monthly Lambda duration from the seven-call sample.

**User-defined workload assumptions:** 10,000 requests/day; 1.5 tool calls/request; 3,000 aggregate tokens/request; 30-day months.

**Illustrative pricing and infrastructure assumptions:** Published-rate reference values as recorded in the working calculation; Runtime CPU/memory profile; one Gateway ListTools operation per user request; one stored secret. Runtime usage was **not** measured.

**Not established:** Actual development bill; actual cost per end-user request; model-specific token consumption; production concurrency, cold starts, scaling behavior, latency percentiles, or complete production bill.

## 7. Next measurement opportunities (optional)

If access to the temporary lab remains available, the highest-value improvements are: model/inference-profile-dimensioned Bedrock metrics; per-request tracing of model invocations and token usage; Runtime CPU/memory metering; CloudWatch log ingestion; and applicable regional pricing verification. These are improvements to estimate confidence, **not prerequisites for documenting the current lab results**.

## 8. Security and publication

Publish only sanitized excerpts. Do not commit raw deployment logs, Cognito client secrets, access tokens, session credentials, or other secret material. A Cognito client secret appeared in an earlier development transcript; rotate or revoke it if the lab resources remain active and the secret may have been exposed outside a controlled environment.

## 9. Reference pages for price verification

- AWS Bedrock pricing: https://aws.amazon.com/bedrock/pricing/
- Amazon Bedrock AgentCore pricing: https://aws.amazon.com/bedrock/agentcore/pricing/
- AWS Lambda pricing: https://aws.amazon.com/lambda/pricing/
- AWS Secrets Manager pricing: https://aws.amazon.com/secrets-manager/pricing/
- Amazon CloudWatch pricing: https://aws.amazon.com/cloudwatch/pricing/

**Publication label:** *Telemetry-informed production projection (preliminary, not billed cost).*  
**Confidence:** Direct Lambda and aggregate Bedrock observations are recorded; total production spend remains a partial estimate with significant unmeasured components.
