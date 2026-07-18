#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROJECT_ID="${GCP_PROJECT_ID:-${1:-}}"
REGION="${GCP_REGION:-us-central1}"
SERVICE="${CAUSALGATE_SERVICE:-causal-gate}"
REPOSITORY="${GCP_ARTIFACT_REPOSITORY:-causalgate}"
ATTESTATION_SECRET="${GCP_ATTESTATION_SECRET:-causalgate-attestation-key}"
GRANT_SECRET="${GCP_GRANT_SECRET:-causalgate-grant-signing-key}"

for command_name in gcloud openssl curl; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
done

if [[ -z "$PROJECT_ID" ]]; then
  PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
fi
if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "Set GCP_PROJECT_ID or pass the Google Cloud project ID as the first argument." >&2
  exit 1
fi
if [[ -z "$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null)" ]]; then
  echo "No active gcloud login. Run: gcloud auth login" >&2
  exit 1
fi

gcloud config set project "$PROJECT_ID" >/dev/null
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com iam.googleapis.com

if ! gcloud artifacts repositories describe "$REPOSITORY" --location "$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$REPOSITORY" --repository-format docker --location "$REGION" --description "CausalGate images"
fi

SERVICE_ACCOUNT="causalgate-web@$PROJECT_ID.iam.gserviceaccount.com"
if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT" >/dev/null 2>&1; then
  gcloud iam service-accounts create causalgate-web --display-name "CausalGate runtime"
fi

create_secret_if_missing() {
  local secret_name="$1"
  if ! gcloud secrets describe "$secret_name" >/dev/null 2>&1; then
    openssl rand -hex 32 | gcloud secrets create "$secret_name" --replication-policy automatic --data-file=-
  fi
  gcloud secrets add-iam-policy-binding "$secret_name" \
    --member "serviceAccount:$SERVICE_ACCOUNT" \
    --role roles/secretmanager.secretAccessor >/dev/null
}

create_secret_if_missing "$ATTESTATION_SECRET"
create_secret_if_missing "$GRANT_SECRET"

REVISION="${CAUSALGATE_REVISION:-$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || date -u +%Y%m%d%H%M%S)}"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$SERVICE:$REVISION"

gcloud builds submit "$ROOT_DIR" --tag "$IMAGE"
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "$SERVICE_ACCOUNT" \
  --set-env-vars "CAUSALGATE_DEMO_MODE=true,CAUSALGATE_LIVE_ANALYSIS_ENABLED=true,CAUSALGATE_LIVE_ANALYSIS_LIMIT=3,OPENAI_MODEL=gpt-5.6-sol,CAUSALGATE_SOURCE_REVISION=$REVISION,CAUSALGATE_RUNNER_IDENTITY=gcp-cloud-run" \
  --set-secrets "CAUSALGATE_ATTESTATION_KEY=$ATTESTATION_SECRET:latest,CAUSALGATE_GRANT_SIGNING_KEY=$GRANT_SECRET:latest" \
  --port 8080 \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 1 \
  --concurrency 8

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
curl --fail --silent --show-error "$URL/health" >/dev/null
echo "CausalGate is deployed and healthy: $URL"
echo "No OpenAI key was deployed. Optional live analysis uses the explicit ephemeral BYOK field."
