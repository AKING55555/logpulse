# LogPulse LocalStack Initialization for PowerShell
$ErrorActionPreference = "Stop"

$Region = if ($env:AWS_REGION) { $env:AWS_REGION } else { "us-east-1" }
$AccountId = "000000000000"

Write-Host "=================================================="
Write-Host "Initializing LocalStack AWS Resources for LogPulse"
Write-Host "Region: $Region"
Write-Host "=================================================="

# Function to execute awslocal via docker
function Invoke-AwsLocal {
    param([string[]]$Arguments)
    docker exec logpulse-localstack awslocal @Arguments
}

# 1. Create SQS Dead Letter Queue (DLQ)
Write-Host "Checking/Creating SQS DLQ: logpulse-events-dlq..."
$dlqUrl = (Invoke-AwsLocal @("sqs", "create-queue", "--queue-name", "logpulse-events-dlq", "--query", "QueueUrl", "--output", "text")).Trim()
Write-Host "DLQ created/verified: $dlqUrl"
$dlqArn = "arn:aws:sqs:${Region}:${AccountId}:logpulse-events-dlq"

# 2. Create SQS Main Queue
Write-Host "Checking/Creating SQS Main Queue: logpulse-events..."
$attributes = '{"VisibilityTimeout":"30","RedrivePolicy":"{\"deadLetterTargetArn\":\"' + $dlqArn + '\",\"maxReceiveCount\":\"3\"}"}'

try {
    $existingQueueUrl = (Invoke-AwsLocal @("sqs", "get-queue-url", "--queue-name", "logpulse-events", "--query", "QueueUrl", "--output", "text") 2>$null).Trim()
} catch {
    $existingQueueUrl = ""
}

if ($existingQueueUrl -and -not ($existingQueueUrl -match "error")) {
    Write-Host "Main queue exists ($existingQueueUrl). Updating attributes..."
    Invoke-AwsLocal @("sqs", "set-queue-attributes", "--queue-url", $existingQueueUrl, "--attributes", $attributes) | Out-Null
    $mainQueueUrl = $existingQueueUrl
} else {
    $mainQueueUrl = (Invoke-AwsLocal @("sqs", "create-queue", "--queue-name", "logpulse-events", "--attributes", $attributes, "--query", "QueueUrl", "--output", "text")).Trim()
}
Write-Host "Main Queue ready: $mainQueueUrl"

# 3. Create S3 Raw Archive Bucket
Write-Host "Checking/Creating S3 Bucket: logpulse-raw..."
$s3Check = docker exec logpulse-localstack awslocal s3api head-bucket --bucket logpulse-raw 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "S3 Bucket 'logpulse-raw' already exists."
} else {
    if ($Region -eq "us-east-1") {
        Invoke-AwsLocal @("s3api", "create-bucket", "--bucket", "logpulse-raw", "--region", $Region) | Out-Null
    } else {
        Invoke-AwsLocal @("s3api", "create-bucket", "--bucket", "logpulse-raw", "--region", $Region, "--create-bucket-configuration", "LocationConstraint=$Region") | Out-Null
    }
    Write-Host "S3 Bucket 'logpulse-raw' created."
}

# 4. Create SNS Alert Topic
Write-Host "Checking/Creating SNS Topic: logpulse-alerts..."
$topicArn = (Invoke-AwsLocal @("sns", "create-topic", "--name", "logpulse-alerts", "--query", "TopicArn", "--output", "text")).Trim()
Write-Host "SNS Topic ready: $topicArn"

Write-Host "=================================================="
Write-Host "LocalStack Initialization Complete!"
Write-Host "SQS Main Queue : $mainQueueUrl"
Write-Host "SQS DLQ        : $dlqUrl"
Write-Host "S3 Bucket      : logpulse-raw"
Write-Host "SNS Topic      : $topicArn"
Write-Host "=================================================="
