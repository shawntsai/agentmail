"""AgentMail MCP Server — 2 tools: send and inbox."""

import os
import httpx
from mcp.server.fastmcp import FastMCP

NODE_URL = os.environ.get("AGENTMAIL_NODE", "http://localhost:7443")

mcp = FastMCP("agentmail")


@mcp.tool()
def send(to: str, message: str) -> str:
    """Send a message to an agent.

    Args:
        to: Agent name (e.g. "planner", "bob"). Will be sent to planner@planner.local.
        message: The message to send.
    """
    address = f"{to}@{to}.local"
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(f"{NODE_URL}/v0/send", json={
                "to": address,
                "subject": message[:80],
                "body": message,
                "intent": "task",
                "encrypt": True,
            })
            data = resp.json()
            return f"Sent to {address} (msg_id: {data.get('msg_id', '?')}, delivered: {data.get('delivered', '?')})"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def inbox() -> str:
    """Check inbox for new messages from other agents."""
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{NODE_URL}/v0/messages", params={"direction": "inbound", "limit": 20})
            messages = resp.json()
            if not messages:
                return "Inbox empty."
            lines = []
            for msg in messages:
                lines.append(f"From: {msg['from_addr']}")
                lines.append(f"Subject: {msg.get('subject', '')}")
                lines.append(f"Body: {msg.get('body', '')[:200]}")
                lines.append(f"Time: {msg['sent_at']}")
                lines.append("---")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    mcp.run()
