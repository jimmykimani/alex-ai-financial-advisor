"""
Bedrock / LiteLLM region alignment for AWS Lambda.

Lambda injects AWS_REGION with the *function* region (often us-east-1). LiteLLM and
some boto3 code paths prefer AWS_REGION over AWS_REGION_NAME, so Bedrock calls were
being sent to the wrong region while models are configured in BEDROCK_REGION.

RDS Data API clients created with an explicit region_name are unaffected by these
environment overrides for the lifetime of that client object.
"""

from __future__ import annotations

import os


def ensure_litellm_bedrock_region(region: str | None = None) -> None:
    """Point LiteLLM Bedrock at BEDROCK_REGION (or explicit ``region``)."""
    r = (region or os.getenv("BEDROCK_REGION") or "us-west-2").strip()
    if not r:
        r = "us-west-2"
    os.environ["AWS_REGION_NAME"] = r
    os.environ["AWS_DEFAULT_REGION"] = r
    os.environ["AWS_REGION"] = r
