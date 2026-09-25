# NEXO — ARCHITECTURE

## Actual architecture

Android / cliente web
        |
      HTTPS
        |
NEXO API / Gateway
        |
   +----+-------------------+
   |    |        |          |
Memory ToolHub Orchestrator Verification
   |    |        |          |
Postgres Web/Calc route plan evidence
        |
     ModelHub
        |
 ProviderCascade
   |       |       |
provider provider provider
        |
 circuit breaker / failover
        |
  response + metadata
        |
 fallback local determinista

## Current contracts

- `/v1/chat`: chat HTTP.
- `/v1/ai/stream`: streaming SSE.
- `/health`: liveness only.
- `/ready`: infrastructure readiness.
- `/v1/ai-ready`: active remote AI probe without local fallback.
- `/status`: aggregate system status.
- `/v1/ai/diagnostics`: provider and resilience diagnostics.

Response metadata includes provider, model, failover state, latency, request ID, conversation ID, memory synchronization and web-source information.

## Resilience

Provider state is persisted in PostgreSQL:

```text
CLOSED -> OPEN -> HALF_OPEN -> CLOSED
```

Provider failures are classified, timed and recorded. The cascade can continue to other providers within a bounded deadline.

## Memory

Conversation data is durable in PostgreSQL. `MemoryEngine` ranks retrieved entries independently of storage.

The current ranking is deterministic textual matching. It is not yet the semantic/research memory system described by the master map.

## Web

`WebTool` performs real search/fetch operations. The Brain records source URLs and explicitly marks lookup failures instead of claiming successful browsing.

## Model and tools

`ModelHub` gives the provider layer a provider-neutral surface. `ProviderSpec` can expose capability tags such as `fast`, `reasoning`, `economical`, `local` and `private`. `ModelSelectionPolicy` classifies the request and chooses a configured capability deterministically.

The selected remote provider is passed into `ProviderCascade` for both HTTP generation and SSE. The remaining configured providers remain available as failover peers. When a request requires local/private handling and no local capability exists, NEXO uses its explicit deterministic local fallback instead of silently sending the request to a remote provider.

`ToolHub` registers tools with explicit network, mutation and risk policy. The currently integrated tools include web search/fetch, calculation and UTC time. The full planned tool catalog is not complete.

## Local capability

The current local fallback is a deterministic responder. It is deliberately not represented as a local LLM.

## Android

The mobile client is a Capacitor/Vite application. The current declared mobile version is NEXO 0.1.6. The client has bounded connection checks, SSE handling, local circuit state and HTTP recovery.

## Security and observability

Secrets remain in runtime environment variables. Diagnostic output is designed to avoid secret values. Requests receive correlation IDs and aggregate metrics. Replication uses signed payloads and a versioned internal protocol.

## Rule

A module existing in the repository is not equivalent to certification. A layer is considered certified only when its contract, tests, deployed commit and observed runtime behavior agree.