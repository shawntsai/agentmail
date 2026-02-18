"""AgentMail daemon — Local-first, peer-to-peer agent communication protocol."""

# Re-export client for backwards compatibility
from agentmail import AgentMailClient, __version__

__all__ = ["AgentMailClient", "__version__"]
