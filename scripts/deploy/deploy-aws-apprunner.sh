#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
SERVICE="${CAUSALGATE_SERVICE:-causal-gate}"
ECR_REPOSITORY="${AWS_ECR_REPOSITORY:-causal-gate}"
ATTESTATION_SECRET_NAME="${AWS_ATTESTATION_SECRET:-causalgate/attestation-key}"
GRANT_SECRET_NAME="${AWS_GRANT_SECRET:-causalgate/grant-signing-key}"
ECR_ROLE_NAME="${AWS_APPRUNNER_ECR_ROLE:-CausalGateAppRunnerEcrAccess}"
INSTANCE_ROLE_NAME="${AWS_APPRUNNER_INSTANCE_ROLE:-CausalGateAppRunnerInstance}"
AUTOSCALING_NAME="${AWS_APPRUNNER_AUTOSCALING:-causalgate-single-instance}"

for command_name in aws docker openssl jq curl; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
done

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text --region "$REGION")"
if [[ -z "$ACCOUNT_ID" || "$ACCOUNT_ID" == "None" ]]; then
  echo "AWS credentials are unavailable. Run: aws configure" >&2
  exit 1
fi
if [[ ! "$SERVICE" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{3,39}$ ]]; then
  echo "Invalid App Runner service name: $SERVICE" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d /tmp/causalgate-aws-XXXXXX)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT
chmod 700 "$TMP_DIR"

if ! aws ecr describe-repositories --repository-names "$ECR_REPOSITORY" --region "$REGION" >/dev/null 2>&1; then
  aws ecr create-repository \
    --repository-name "$ECR_REPOSITORY" \
    --image-scanning-configuration scanOnPush=true \
    --encryption-configuration encryptionType=AES256 \
    --region "$REGION" >/dev/null
fi

REVISION="${CAUSALGATE_REVISION:-$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || date -u +%Y%m%d%H%M%S)}"
REGISTRY="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
IMAGE="$REGISTRY/$ECR_REPOSITORY:$REVISION"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"
docker build --platform linux/amd64 -t "$IMAGE" "$ROOT_DIR"
docker push "$IMAGE"

create_secret_if_missing() {
  local secret_name="$1"
  local secret_file="$TMP_DIR/$(echo "$secret_name" | tr '/' '_').txt"
  local secret_arn
  secret_arn="$(aws secretsmanager describe-secret --secret-id "$secret_name" --region "$REGION" --query ARN --output text 2>/dev/null || true)"
  if [[ -z "$secret_arn" || "$secret_arn" == "None" ]]; then
    openssl rand -hex 32 | tr -d '\n' > "$secret_file"
    chmod 600 "$secret_file"
    secret_arn="$(aws secretsmanager create-secret --name "$secret_name" --secret-string "file://$secret_file" --region "$REGION" --query ARN --output text)"
  fi
  printf '%s' "$secret_arn"
}

ATTESTATION_SECRET_ARN="$(create_secret_if_missing "$ATTESTATION_SECRET_NAME")"
GRANT_SECRET_ARN="$(create_secret_if_missing "$GRANT_SECRET_NAME")"

jq -n '{Version:"2012-10-17",Statement:[{Effect:"Allow",Principal:{Service:"build.apprunner.amazonaws.com"},Action:"sts:AssumeRole"}]}' > "$TMP_DIR/ecr-trust.json"
if ! aws iam get-role --role-name "$ECR_ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ECR_ROLE_NAME" --assume-role-policy-document "file://$TMP_DIR/ecr-trust.json" >/dev/null
fi
aws iam attach-role-policy --role-name "$ECR_ROLE_NAME" --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess
ECR_ROLE_ARN="$(aws iam get-role --role-name "$ECR_ROLE_NAME" --query Role.Arn --output text)"

jq -n '{Version:"2012-10-17",Statement:[{Effect:"Allow",Principal:{Service:"tasks.apprunner.amazonaws.com"},Action:"sts:AssumeRole"}]}' > "$TMP_DIR/instance-trust.json"
if ! aws iam get-role --role-name "$INSTANCE_ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-role --role-name "$INSTANCE_ROLE_NAME" --assume-role-policy-document "file://$TMP_DIR/instance-trust.json" >/dev/null
fi
INSTANCE_ROLE_ARN="$(aws iam get-role --role-name "$INSTANCE_ROLE_NAME" --query Role.Arn --output text)"
jq -n --arg attestation "$ATTESTATION_SECRET_ARN" --arg grant "$GRANT_SECRET_ARN" \
  '{Version:"2012-10-17",Statement:[{Effect:"Allow",Action:["secretsmanager:GetSecretValue"],Resource:[$attestation,$grant]}]}' > "$TMP_DIR/secret-policy.json"
aws iam put-role-policy --role-name "$INSTANCE_ROLE_NAME" --policy-name CausalGateRuntimeSecrets --policy-document "file://$TMP_DIR/secret-policy.json"
sleep 10

AUTOSCALING_ARN="$(aws apprunner list-auto-scaling-configurations \
  --auto-scaling-configuration-name "$AUTOSCALING_NAME" \
  --region "$REGION" \
  --query 'AutoScalingConfigurationSummaryList[?Status==`ACTIVE`] | [0].AutoScalingConfigurationArn' \
  --output text)"
if [[ -z "$AUTOSCALING_ARN" || "$AUTOSCALING_ARN" == "None" ]]; then
  AUTOSCALING_ARN="$(aws apprunner create-auto-scaling-configuration \
    --auto-scaling-configuration-name "$AUTOSCALING_NAME" \
    --max-concurrency 100 --min-size 1 --max-size 1 \
    --region "$REGION" \
    --query AutoScalingConfiguration.AutoScalingConfigurationArn --output text)"
fi

jq -n \
  --arg image "$IMAGE" \
  --arg accessRole "$ECR_ROLE_ARN" \
  --arg attestation "$ATTESTATION_SECRET_ARN" \
  --arg grant "$GRANT_SECRET_ARN" \
  --arg revision "$REVISION" \
  '{AuthenticationConfiguration:{AccessRoleArn:$accessRole},AutoDeploymentsEnabled:false,ImageRepository:{ImageIdentifier:$image,ImageRepositoryType:"ECR",ImageConfiguration:{Port:"8080",RuntimeEnvironmentVariables:{CAUSALGATE_DEMO_MODE:"true",CAUSALGATE_LIVE_ANALYSIS_ENABLED:"true",CAUSALGATE_LIVE_ANALYSIS_LIMIT:"3",OPENAI_MODEL:"gpt-5.6-sol",CAUSALGATE_SOURCE_REVISION:$revision,CAUSALGATE_RUNNER_IDENTITY:"aws-app-runner"},RuntimeEnvironmentSecrets:{CAUSALGATE_ATTESTATION_KEY:$attestation,CAUSALGATE_GRANT_SIGNING_KEY:$grant}}}}' \
  > "$TMP_DIR/source.json"
jq -n --arg role "$INSTANCE_ROLE_ARN" '{Cpu:"1 vCPU",Memory:"2 GB",InstanceRoleArn:$role}' > "$TMP_DIR/instance.json"

SERVICE_ARN="$(aws apprunner list-services --region "$REGION" --query "ServiceSummaryList[?ServiceName=='$SERVICE'] | [0].ServiceArn" --output text)"
if [[ -z "$SERVICE_ARN" || "$SERVICE_ARN" == "None" ]]; then
  SERVICE_ARN="$(aws apprunner create-service \
    --service-name "$SERVICE" \
    --source-configuration "file://$TMP_DIR/source.json" \
    --instance-configuration "file://$TMP_DIR/instance.json" \
    --auto-scaling-configuration-arn "$AUTOSCALING_ARN" \
    --health-check-configuration 'Protocol=HTTP,Path=/health,Interval=10,Timeout=5,HealthyThreshold=1,UnhealthyThreshold=5' \
    --region "$REGION" \
    --query Service.ServiceArn --output text)"
else
  aws apprunner update-service \
    --service-arn "$SERVICE_ARN" \
    --source-configuration "file://$TMP_DIR/source.json" \
    --instance-configuration "file://$TMP_DIR/instance.json" \
    --auto-scaling-configuration-arn "$AUTOSCALING_ARN" \
    --region "$REGION" >/dev/null
fi

for _ in {1..60}; do
  STATUS="$(aws apprunner describe-service --service-arn "$SERVICE_ARN" --region "$REGION" --query Service.Status --output text)"
  if [[ "$STATUS" == "RUNNING" ]]; then break; fi
  if [[ "$STATUS" == "CREATE_FAILED" || "$STATUS" == "UPDATE_FAILED" || "$STATUS" == "DELETE_FAILED" ]]; then
    echo "AWS App Runner deployment failed with status: $STATUS" >&2
    exit 1
  fi
  sleep 10
done
if [[ "$STATUS" != "RUNNING" ]]; then
  echo "Timed out waiting for AWS App Runner. Current status: $STATUS" >&2
  exit 1
fi

DOMAIN="$(aws apprunner describe-service --service-arn "$SERVICE_ARN" --region "$REGION" --query Service.ServiceUrl --output text)"
URL="https://$DOMAIN"
curl --fail --silent --show-error "$URL/health" >/dev/null
echo "CausalGate is deployed and healthy: $URL"
echo "No OpenAI key was deployed. Optional live analysis uses the explicit ephemeral BYOK field."
