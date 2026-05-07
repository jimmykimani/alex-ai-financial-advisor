#!/usr/bin/env python3
"""
Pre-deploy checks for portfolio analysis (Aurora, SQS, Lambdas, Bedrock API).

Does **not** run an analysis or call model inference — no Bedrock token usage.
Use this before `package_native.py` / `terraform apply` so you do not ship when
the environment is misconfigured.

Usage:
    cd scripts && uv sync && uv run python verify_analysis_ready.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        print("Install dependencies: cd scripts && uv sync", file=sys.stderr)
        sys.exit(2)
    root = _repo_root()
    env_path = root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=True)
    else:
        print(f"Missing {env_path} — copy from .env.example and fill values.", file=sys.stderr)
        sys.exit(2)


def _rds_region(cluster_arn: str) -> str:
    m = re.match(r"arn:aws:rds:([^:]+):", cluster_arn)
    if m:
        return m.group(1)
    return os.getenv("DEFAULT_AWS_REGION", "us-east-1")


def main() -> int:
    _load_env()

    required = [
        "AURORA_CLUSTER_ARN",
        "AURORA_SECRET_ARN",
        "SQS_QUEUE_URL",
        "BEDROCK_MODEL_ID",
        "BEDROCK_REGION",
    ]
    missing = [k for k in required if not (os.getenv(k) or "").strip()]
    if missing:
        print("FAIL: missing environment variables:", ", ".join(missing))
        print("  Copy values from Terraform outputs / your deployed .env.")
        return 1

    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        print("FAIL: boto3 not installed. Run: cd scripts && uv sync")
        return 2

    default_region = (os.getenv("DEFAULT_AWS_REGION") or "us-east-1").strip()
    cluster_arn = os.environ["AURORA_CLUSTER_ARN"].strip()
    rds_region = _rds_region(cluster_arn)

    print("== Alex analysis preflight (no LLM calls) ==")
    print(f"  Default AWS region: {default_region}")
    print(f"  Aurora Data API region: {rds_region}")
    print(f"  Bedrock region: {os.environ['BEDROCK_REGION'].strip()}")
    print(f"  Bedrock model: {os.environ['BEDROCK_MODEL_ID'].strip()}")
    print()

    # 1) STS
    try:
        ident = boto3.client("sts", region_name=default_region).get_caller_identity()
        print(f"OK  AWS identity: {ident.get('Arn', ident.get('Account'))}")
    except ClientError as e:
        print(f"FAIL  STS / credentials: {e}")
        return 1

    # 2) Aurora Data API
    db_name = (os.getenv("AURORA_DATABASE") or "alex").strip()
    try:
        rds = boto3.client("rds-data", region_name=rds_region)
        rds.execute_statement(
            resourceArn=os.environ["AURORA_CLUSTER_ARN"].strip(),
            secretArn=os.environ["AURORA_SECRET_ARN"].strip(),
            database=db_name,
            sql="SELECT 1 AS ok",
        )
        print(f"OK  Aurora Data API (database={db_name})")
    except ClientError as e:
        print(f"FAIL  Aurora Data API: {e}")
        return 1

    # 3) SQS queue
    queue_url = os.environ["SQS_QUEUE_URL"].strip()
    try:
        sqs = boto3.client("sqs", region_name=default_region)
        sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])
        print("OK  SQS queue reachable")
    except ClientError as e:
        print(f"FAIL  SQS: {e}")
        return 1

    # 4) Agent Lambdas exist
    lam = boto3.client("lambda", region_name=default_region)
    for name in (
        "alex-planner",
        "alex-tagger",
        "alex-reporter",
        "alex-charter",
        "alex-retirement",
    ):
        try:
            lam.get_function(FunctionName=name)
            print(f"OK  Lambda {name}")
        except ClientError as e:
            print(f"FAIL  Lambda {name}: {e}")
            return 1

    # 5) Bedrock control plane (no inference; confirms API + region)
    br_region = os.environ["BEDROCK_REGION"].strip()
    try:
        br = boto3.client("bedrock", region_name=br_region)
        br.list_foundation_models()
        print(f"OK  Bedrock API in {br_region} (list models only; does not invoke)")
    except ClientError as e:
        print(f"FAIL  Bedrock list_models in {br_region}: {e}")
        return 1

    if not (os.getenv("POLYGON_API_KEY") or "").strip():
        print("WARN  POLYGON_API_KEY empty — price updates may skip (non-fatal).")

    print()
    print("All preflight checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
