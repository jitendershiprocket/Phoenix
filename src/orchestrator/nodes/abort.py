"""Abort Node - Set status when validation fails after max retries."""

from src.orchestrator.state import PhoenixState


def abort_node(state: PhoenixState) -> dict:
    """Mark run as aborted with reason."""
    return {"status": "aborted"}
