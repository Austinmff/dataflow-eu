#!/bin/bash
BUCKET_NAME="${S3_BUCKET_NAME:-dataflow-eu-bronze}"
REGION="${AWS_DEFAULT_REGION:-eu-west-1}"
awslocal s3api create-bucket --bucket "${BUCKET_NAME}" --region "${REGION}" --create-bucket-configuration LocationConstraint="${REGION}"
awslocal s3api put-bucket-versioning --bucket "${BUCKET_NAME}" --versioning-configuration Status=Enabled
echo "Bucket ${BUCKET_NAME} created."
