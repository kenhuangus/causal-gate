# CausalGate SaaS and BYOK Design

## Product shape

CausalGate can become a SaaS control plane in addition to its Python SDK. The SDK remains the instrumentation and enforcement edge; the SaaS product provides workspace management, trace ingestion, investigation, policy distribution, replay orchestration, evidence retention, collaboration, and software-factory release gates.

The commercial boundary is deliberately simple: customers pay CausalGate for the control plane and use their own OpenAI project for optional model inference. Deterministic capture, authorization, findings, replay, reporting, and promotion evidence do not depend on an OpenAI key.

## Judge experience

The public judge deployment exposes synthetic data only and requires no account.

1. Run the vulnerable scenario without a key.
2. Inspect deterministic authorization, the Intent Causal Record, findings, and evidence.
3. Replay the identical fixture under enforcement and inspect the promotion gate.
4. Optionally open **Bring Your Own Key**, paste a restricted OpenAI project key, and request one GPT-5.6 Sol analysis.
5. CausalGate sends only the minimized redacted trace, validates the structured response and evidence identifiers, clears the browser input, and does not persist the key.

Judges should use a restricted project key with a small budget and rotate it after testing. The live call is optional and cannot change authorization or promotion outcomes.

## Shipped BYOK boundary

- The public Cloud Run service contains no shared OpenAI credential.
- The key is accepted only on explicit live endpoints through `X-OpenAI-API-Key`.
- The UI keeps no key in local storage, session storage, cookies, URLs, traces, exports, analytics, or error messages.
- The backend passes the key directly to a request-scoped OpenAI client and retains no copy after the request.
- Same-origin HTTPS, request-size bounds, bounded provider timeout, sanitized errors, and rate limits reduce exposure and abuse.
- Self-hosted operators can avoid browser entry by using a server-side `OPENAI_API_KEY` environment variable.

This is a transparent third-party BYOK trust boundary, not zero-knowledge secret handling. Users must trust the deployed backend. A production service should prefer tenant vaulting or one-request BYOK according to customer policy and should complete an independent security review before accepting production credentials.

## Production SaaS architecture

```text
Agent SDK / CI / adapters
          |
          v
Authenticated ingestion API ──> Cloud Tasks ──> private analysis workers
          |                                      |
          v                                      v
Tenant-scoped Cloud SQL                  deterministic + optional OpenAI
          |                                      |
          +────────> evidence store <────────────+
                           |
                           v
                 investigation + release UI
```

Required production components:

- OIDC authentication, organizations, workspaces, and role-based access;
- tenant IDs on every row, object, task, cache entry, and authorization decision;
- Cloud SQL with row-level tenant controls and transactional nonce consumption;
- private Cloud Run workers invoked only by Cloud Tasks;
- Cloud Storage for immutable redacted evidence packages;
- Cloud KMS and Secret Manager for customers choosing persisted BYOK;
- audit records for policy, grant, approval, key-reference, replay, and promotion changes;
- per-tenant quotas, spend guards, concurrency limits, retention, export, and deletion controls;
- regional placement and data-processing configuration; and
- OpenTelemetry ingestion so teams can adopt CausalGate without replacing existing observability.

## Credential modes

| Mode | Use case | Persistence | Recommended control |
|---|---|---:|---|
| Deterministic | Default demo and core product | None | No provider credential |
| Ephemeral BYOK | Judge or occasional analysis | None | Restricted project key, one request, immediate clear |
| Self-hosted environment | Private deployment | Operator managed | Runtime environment or managed secret |
| Tenant vault | Production SaaS | Encrypted | Per-tenant secret, KMS envelope encryption, rotation and audit |

The service must never pool customer keys, silently fall back to the operator's OpenAI account, or use one tenant's key for another tenant.

## Practical SaaS packaging

- **Developer:** local SDK, one workspace, deterministic rules and CI gate.
- **Team:** hosted investigations, retention, collaboration, policy registry, and exports.
- **Factory:** signed suite gates, private workers, release integrations, organization policy, and tenant-vault BYOK.

OpenAI usage is billed directly to the customer's OpenAI project. CausalGate pricing can therefore be based on retained executions, protected tool decisions, workspaces, and release-gate runs rather than reselling model tokens.

## Production acceptance gates

Before calling the hosted service production-ready, verify tenant-isolation tests, authorization bypass tests, log and export secret scans, key rotation and deletion, atomic permit replay prevention, queue idempotency, regional restore, retention deletion, rate limiting, spend guards, dependency scanning, external penetration testing, and incident response. The current single-instance SQLite and in-memory rate/nonce profiles remain judge and local-development profiles only.
