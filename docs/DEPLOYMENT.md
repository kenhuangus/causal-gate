# CausalGate deployment guide

This guide covers the supported judge/demo deployment profile:

- local Docker on Windows, macOS, or Linux;
- Google Cloud Run; and
- AWS App Runner.

Every path runs the complete deterministic demonstration without an OpenAI API key. Optional GPT-5.6 Sol investigation uses an explicit ephemeral BYOK field in the UI. The supplied key is sent once to the same-origin CausalGate backend, held only for that request, and never written to CausalGate storage.

## Security and scope

The scripts create CausalGate attestation and grant-signing secrets. They never create, request, or deploy an OpenAI API key.

The cloud configurations intentionally use one application instance because the judge profile uses local SQLite and a process-local permit ledger. Container storage is ephemeral on Cloud Run and App Runner. This is appropriate for the synthetic demonstration, but not for a horizontally scaled production SaaS. Before enabling multiple instances or customer workspaces, use a durable database, an atomic shared permit store, workload identity, tenant authorization, private workers, and managed audit storage as described in [SAAS-BYOK.md](SAAS-BYOK.md).

Cloud deployments create billable resources. Review your provider account, region, quotas, and budget alerts before running them.

## Local deployment

### Prerequisites

- Git
- Docker Desktop on Windows or macOS, or Docker Engine with Compose v2 on Linux
- OpenSSL and curl on macOS/Linux
- PowerShell 5.1 or newer on Windows

Clone the project first:

```bash
git clone https://github.com/kenhuangus/causal-gate.git
cd causal-gate
```

### Windows

From PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\local\run-windows.ps1
```

Use another port or avoid opening the browser automatically:

```powershell
.\scripts\local\run-windows.ps1 -Port 8088 -NoBrowser
```

Stop while preserving the local Docker volume:

```powershell
.\scripts\local\stop-windows.ps1
```

Explicitly remove the local demo volume:

```powershell
.\scripts\local\stop-windows.ps1 -RemoveData
```

### macOS

```bash
./scripts/local/run-macos-linux.sh
```

Stop while preserving the local Docker volume:

```bash
./scripts/local/stop-macos-linux.sh
```

### Linux

```bash
./scripts/local/run-macos-linux.sh
```

If the host uses a non-root Docker group, make sure the current user can run `docker compose` before starting. Stop with:

```bash
./scripts/local/stop-macos-linux.sh
```

On macOS or Linux, choose a different host port with `CAUSALGATE_PORT=8088`. Set `CAUSALGATE_OPEN_BROWSER=false` for a headless machine.

The first local launch creates `.causalgate.local.env` with random runtime signing keys and mode settings. Git ignores this file. Do not commit or share it.

After launch, open `http://localhost:8080`, select **Run vulnerable scenario**, inspect the deterministic evidence, and select **Replay with protection**. Only enter an OpenAI key if you explicitly want the optional live semantic investigation.

## Google Cloud Run

The cloud deployment scripts are Bash scripts. Windows operators can run them from WSL 2 with Docker Desktop integration. macOS and Linux can run them directly.

### Prerequisites

- a Google Cloud project with billing enabled;
- `gcloud`, OpenSSL, and curl;
- an active `gcloud auth login`; and
- permission to enable APIs, create Artifact Registry repositories, service accounts and secrets, submit Cloud Builds, and deploy Cloud Run services.

Deploy with:

```bash
export GCP_PROJECT_ID="your-project-id"
export GCP_REGION="us-central1"
./scripts/deploy/deploy-gcp-cloud-run.sh
```

You may also pass the project ID directly:

```bash
./scripts/deploy/deploy-gcp-cloud-run.sh your-project-id
```

The script:

1. enables Cloud Run, Cloud Build, Artifact Registry, Secret Manager, and IAM APIs;
2. creates the `causalgate` Docker repository when absent;
3. creates a least-purpose `causalgate-web` runtime service account;
4. creates random attestation and grant-signing secrets when absent;
5. grants the runtime account access only to those secrets;
6. builds and pushes the current source revision;
7. deploys one public Cloud Run instance; and
8. verifies `/health` before returning the public URL.

Optional configuration:

| Variable | Default | Purpose |
| --- | --- | --- |
| `GCP_REGION` | `us-central1` | Artifact Registry and Cloud Run region |
| `CAUSALGATE_SERVICE` | `causal-gate` | Cloud Run service name |
| `GCP_ARTIFACT_REPOSITORY` | `causalgate` | Artifact Registry repository |
| `GCP_ATTESTATION_SECRET` | `causalgate-attestation-key` | Secret Manager name |
| `GCP_GRANT_SECRET` | `causalgate-grant-signing-key` | Secret Manager name |

## AWS App Runner

### Prerequisites

- an AWS account with billing enabled;
- AWS CLI v2, Docker, OpenSSL, jq, and curl;
- working `aws configure` credentials; and
- permission to use STS, ECR, IAM, Secrets Manager, and App Runner.

Deploy with:

```bash
export AWS_REGION="us-east-1"
./scripts/deploy/deploy-aws-apprunner.sh
```

The script:

1. creates an encrypted, scan-on-push ECR repository when absent;
2. builds and pushes the current source revision for Linux AMD64;
3. creates random CausalGate runtime secrets in Secrets Manager when absent;
4. creates narrowly scoped App Runner ECR and runtime IAM roles;
5. restricts the judge profile to one instance;
6. creates or updates the public App Runner service; and
7. waits for `RUNNING` and verifies `/health` before returning its URL.

Optional configuration:

| Variable | Default | Purpose |
| --- | --- | --- |
| `AWS_REGION` | `us-east-1` | AWS deployment region |
| `CAUSALGATE_SERVICE` | `causal-gate` | App Runner service name |
| `AWS_ECR_REPOSITORY` | `causal-gate` | ECR repository name |
| `AWS_ATTESTATION_SECRET` | `causalgate/attestation-key` | Secrets Manager name |
| `AWS_GRANT_SECRET` | `causalgate/grant-signing-key` | Secrets Manager name |

App Runner keeps one warm instance in this profile and therefore incurs charges until the service is paused or deleted.

## Post-deployment acceptance test

For either cloud URL:

1. `GET /health` returns `status: ok`, `mode: deterministic`, and `live_analysis: byok_required`.
2. The landing page loads without entering a key.
3. **Run vulnerable scenario** produces eight evidence-linked findings.
4. Intent-Based Access Control and the Intent Causal Record load.
5. **Replay with protection** produces zero findings and a scoped `promote` recommendation.
6. The OpenAI key field is clearly marked optional and is disabled until a baseline exists.
7. A restricted test project key can run the optional live analysis and is cleared immediately afterward.
8. Browser console and network logs contain no key value or unredacted protected payload.

The final two checks should be performed with a restricted, low-budget OpenAI project key created only for testing.
