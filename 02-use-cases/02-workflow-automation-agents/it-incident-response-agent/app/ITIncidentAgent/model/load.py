"""Model loader for the IT Incident Response Agent.

Claude is called through Claude Platform on AWS (the Anthropic-operated
endpoint ``https://aws-external-anthropic.<region>.api.aws``), not Amazon
Bedrock. Requests are signed with SigV4 using the default AWS credential
chain (container role in AgentCore, local profile on a dev machine), so no
API key is stored. Model IDs are bare Anthropic IDs such as
``claude-sonnet-4-6`` and ``claude-haiku-4-5``.

IAM requirement: the calling principal (the AgentCore runtime role when
deployed) must be allowed ``aws-external-anthropic:CallWithBearerToken``.

Reads model IDs, workspace ID and region from centralized config.

Supports cost-efficient routing: use a cheaper/faster model for LOW priority
tickets and the full model for MEDIUM/HIGH/CRITICAL.
"""

import os

import anthropic
from config import (
    AGENT_MODEL_ID,
    ANTHROPIC_AWS_WORKSPACE_ID,
    CLAUDE_AWS_AUTH_MODE,
    FAST_MODEL_ID,
    REGION,
)
from strands.models.anthropic import AnthropicModel

# strands' AnthropicModel requires max_tokens in its config.
MAX_TOKENS = 4096


class ClaudePlatformAWSModel(AnthropicModel):
    """Strands AnthropicModel backed by the SigV4 Claude Platform on AWS client.

    strands hardcodes ``anthropic.AsyncAnthropic`` and offers no injection
    point (``client_args`` is passed straight to that class), so we let the
    parent set up ``self.config`` and then replace ``self.client``.
    """

    def __init__(self, *, aws_region: str, workspace_id: str, **model_config):
        super().__init__(**model_config)
        self.client = anthropic.AsyncAnthropicAWS(
            aws_region=aws_region,
            workspace_id=workspace_id,
        )
        # The SDK silently switches to API-key auth when ANTHROPIC_AWS_API_KEY
        # is set. We promise SigV4, so fail loudly instead.
        if not getattr(self.client, "_use_sigv4", not os.environ.get("ANTHROPIC_AWS_API_KEY")):
            raise RuntimeError(
                "AsyncAnthropicAWS did not select SigV4 auth. Unset ANTHROPIC_AWS_API_KEY "
                "so the default AWS credential chain is used."
            )


def load_model(priority: str = "MEDIUM") -> ClaudePlatformAWSModel:
    """Get the Claude Platform on AWS model, selecting based on ticket priority.

    Cost routing pattern: LOW priority tickets use a cheaper/faster model
    (Haiku) for classification and simple resolutions. MEDIUM+ tickets use
    the full model (Sonnet) for complex reasoning.

    This demonstrates the 'cost shape' principle: filter cheap at the event
    plane and only use expensive reasoning when warranted.
    """
    if CLAUDE_AWS_AUTH_MODE.lower() != "sigv4":
        raise NotImplementedError(
            f"CLAUDE_AWS_AUTH_MODE={CLAUDE_AWS_AUTH_MODE!r} is not supported; only 'sigv4' is implemented."
        )
    if not ANTHROPIC_AWS_WORKSPACE_ID:
        raise ValueError("ANTHROPIC_AWS_WORKSPACE_ID must be set to your Claude Platform on AWS workspace ID.")
    if not REGION:
        raise ValueError("AWS_REGION must be set and match the Claude Platform on AWS workspace region.")

    model_id = AGENT_MODEL_ID

    # STEP: COST ROUTING — Use cheaper model for low-priority tickets
    if priority == "LOW":
        model_id = FAST_MODEL_ID

    return ClaudePlatformAWSModel(
        aws_region=REGION,
        workspace_id=ANTHROPIC_AWS_WORKSPACE_ID,
        model_id=model_id,
        max_tokens=MAX_TOKENS,
    )
