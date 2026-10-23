"""Shared result policy for read-only Agent tool adapters."""

from ccas.services.schemas import (
    AgentQueryError,
    PipelineStatusResult,
    ServiceProjection,
)


def require_tool_result[T](projection: ServiceProjection[T]) -> T:
    """Return a service payload or raise its shared safe tool-level outcome.

    MCP resources intentionally serialize the status snapshot directly. This
    policy belongs only to CLI/MCP tool calls, where an exhausted pipeline
    requires a human-action error instead of a normal status result.
    """
    payload = projection.payload
    if isinstance(payload, PipelineStatusResult) and payload.data.needs_human:
        raise AgentQueryError(
            "needs_human",
            "Pipeline execution failed after retries were exhausted; "
            "manual review and check required.",
            needs_human=True,
        )
    return payload
