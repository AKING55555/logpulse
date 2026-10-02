#!/usr/bin/env bash
set -euo pipefail

# Configuration
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID="000000000000"
ENDPOINT_URL="${AWS_ENDPOINT_URL:-http://localhost:4566}"

# Helper to determine whether we are inside LocalStack container or running on host
if command -v awslocal >/dev/null 2>&1; then
    run_aws() {
        awslocal "$@"
    }
elif command -v docker >/dev/null 2>&1 && docker ps --filter "name=logpulse-localstack" --format '{{.Names}}' | grep -q "logpulse-localstack"; then
    run_aws() {
        docker exec logpulse-localstack awslocal "$@"
    }
elif command -v aws >/dev/null 2>&1; then
    run_aws() {
        aws --endpoint-url="$ENDPOINT_URL" --region="$REGION" "$@"
    }
else
    echo "Error: Neither awslocal, docker, nor aws CLI found." >&2
    exit 1
fi

echo "=================================================="
echo "Initializing LocalStack AWS Resources for LogPulse"
echo "Region: $REGION"
echo "=================================================="

# 1. Create SQS Dead Letter Queue (DLQ)
echo "Checking/Creating SQS DLQ: logpulse-events-dlq..."
DLQ_URL=$(run_aws sqs create-queue --queue-name logpulse-events-dlq --query "QueueUrl" --output text)
echo "DLQ created/verified: $DLQ_URL"

# Extract or construct DLQ ARN
DLQ_ARN="arn:aws:sqs:${REGION}:${ACCOUNT_ID}:logpulse-events-dlq"
echo "DLQ ARN: $DLQ_ARN"

# 2. Create SQS Main Queue with RedrivePolicy and VisibilityTimeout=30
echo "Checking/Creating SQS Main Queue: logpulse-events..."
REDRIVE_POLICY="{\"deadLetterTargetArn\":\"${DLQ_ARN}\",\"maxReceiveCount\":\"3\"}"

# Check if main queue already exists
EXISTING_QUEUE_URL=$(run_aws sqs get-queue-url --queue-name logpulse-events --query "QueueUrl" --output text 2>/dev/null || true)

if [ -n "$EXISTING_QUEUE_URL" ]; then
    echo "Main queue exists ($EXISTING_QUEUE_URL). Updating attributes..."
    run_aws sqs set-queue-attributes \
        --queue-url "$EXISTING_QUEUE_URL" \
        --attributes "{\"VisibilityTimeout\":\"30\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${DLQ_ARN}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}"
    MAIN_QUEUE_URL="$EXISTING_QUEUE_URL"
else
    MAIN_QUEUE_URL=$(run_aws sqs create-queue \
        --queue-name logpulse-events \
        --attributes "{\"VisibilityTimeout\":\"30\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${DLQ_ARN}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}" \
        --query "QueueUrl" --output text)
fi
echo "Main Queue ready: $MAIN_QUEUE_URL"

# 3. Create S3 Raw Archive Bucket
echo "Checking/Creating S3 Bucket: logpulse-raw..."
if run_aws s3api head-bucket --bucket logpulse-raw 2>/dev/null; then
    echo "S3 Bucket 'logpulse-raw' already exists."
else
    if [ "$REGION" = "us-east-1" ]; then
        run_aws s3api create-bucket --bucket logpulse-raw --region "$REGION"
    else
        run_aws s3api create-bucket --bucket logpulse-raw --region "$REGION" \
            --create-bucket-configuration LocationConstraint="$REGION"
    fi
    echo "S3 Bucket 'logpulse-raw' created."
fi

# 4. Create SNS Alert Topic
echo "Checking/Creating SNS Topic: logpulse-alerts..."
TOPIC_ARN=$(run_aws sns create-topic --name logpulse-alerts --query "TopicArn" --output text)
echo "SNS Topic ready: $TOPIC_ARN"

echo "=================================================="
echo "LocalStack Initialization Complete!"
echo "SQS Main Queue : $MAIN_QUEUE_URL"
echo "SQS DLQ        : $DLQ_URL"
echo "S3 Bucket      : logpulse-raw"
echo "SNS Topic      : $TOPIC_ARN"
echo "=================================================="
