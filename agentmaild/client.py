"""AgentMail Client SDK — for agents and scripts to send/receive messages.

Usage:
    from agentmaild.client import AgentMailClient

    # Connect to a running AgentMail node
    client = AgentMailClient("http://localhost:7443")

    # Send a message to another agent
    client.send("bob@bob.local", subject="Task complete", body="Finished processing the data.")

    # Send structured agent message
    client.send_task("planner@planner.local", task="Summarize the latest news", metadata={"priority": "high"})

    # Read inbox
    messages = client.inbox()
    for msg in messages:
        print(f"From: {msg['from_addr']} — {msg['subject']}")
        print(f"  {msg['body']}")

    # Read a specific message
    msg = client.get_message("msg-id-here")

    # List peers on LAN
    peers = client.peers()

    # Get this node's identity
    me = client.identity()
"""

import httpx
from typing import Optional


class AgentMailClient:
    """Client for interacting with a running AgentMail daemon."""

    def __init__(self, base_url: str = "http://localhost:7443", timeout: float = 10.0):
        """Connect to an AgentMail node.

        Args:
            base_url: URL of the running AgentMail daemon
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str, params: dict = None) -> dict | list:
        with httpx.Client(timeout=self.timeout) as c:
            resp = c.get(f"{self.base_url}{path}", params=params)
            resp.raise_for_status()
            return resp.json()

    def _post(self, path: str, data: dict) -> dict:
        with httpx.Client(timeout=self.timeout) as c:
            resp = c.post(f"{self.base_url}{path}", json=data)
            resp.raise_for_status()
            return resp.json()

    # --- Identity & Peers ---

    def identity(self) -> dict:
        """Get this node's identity (name, address, public keys)."""
        return self._get("/v0/identity")

    def peers(self) -> list[dict]:
        """List all discovered peers on LAN."""
        return self._get("/v0/peers")

    # --- Messages ---

    def send(self, to: str, subject: str = "", body: str = "",
             intent: str = "human_message", encrypt: bool = True) -> dict:
        """Send a message to a peer or external email.

        Args:
            to: Recipient address (e.g. "bob@bob.local")
            subject: Message subject
            body: Message body
            intent: Message intent (human_message, task, notify, ask, tool_call, tool_result)
            encrypt: Whether to encrypt for peer (ignored for external email)

        Returns:
            {"status": "ok", "msg_id": "...", "delivered": true/false}
        """
        return self._post("/v0/send", {
            "to": to,
            "subject": subject,
            "body": body,
            "intent": intent,
            "encrypt": encrypt,
        })

    def send_task(self, to: str, task: str, metadata: dict = None) -> dict:
        """Send a task to an agent.

        Args:
            to: Agent address
            task: Task description
            metadata: Optional metadata (priority, tags, etc)
        """
        body = task
        if metadata:
            import json
            body = json.dumps({"task": task, "metadata": metadata})
        return self.send(to=to, subject=f"Task: {task[:50]}", body=body, intent="task")

    def send_tool_call(self, to: str, tool_name: str, arguments: dict) -> dict:
        """Send a tool call request to an agent.

        Args:
            to: Agent address
            tool_name: Name of the tool to call
            arguments: Tool arguments
        """
        import json
        body = json.dumps({"tool": tool_name, "arguments": arguments})
        return self.send(to=to, subject=f"tool_call: {tool_name}", body=body, intent="tool_call")

    def send_tool_result(self, to: str, tool_name: str, result: str) -> dict:
        """Send a tool result back to an agent.

        Args:
            to: Agent address
            tool_name: Name of the tool
            result: Tool execution result
        """
        import json
        body = json.dumps({"tool": tool_name, "result": result})
        return self.send(to=to, subject=f"tool_result: {tool_name}", body=body, intent="tool_result")

    def inbox(self, limit: int = 100) -> list[dict]:
        """Get inbound messages (newest first).

        Returns:
            List of message dicts with keys: msg_id, from_addr, to_addr,
            subject, body, intent, sent_at, encrypted, status
        """
        return self._get("/v0/messages", params={"direction": "inbound", "limit": limit})

    def sent(self, limit: int = 100) -> list[dict]:
        """Get sent messages (newest first)."""
        return self._get("/v0/messages", params={"direction": "outbound", "limit": limit})

    def all_messages(self, limit: int = 100) -> list[dict]:
        """Get all messages (inbox + sent)."""
        return self._get("/v0/messages", params={"limit": limit})

    def get_message(self, msg_id: str) -> dict:
        """Get a specific message by ID."""
        return self._get(f"/v0/messages/{msg_id}")

    # --- Convenience ---

    def wait_for_message(self, timeout: float = 60, poll_interval: float = 2) -> Optional[dict]:
        """Block until a new message arrives in inbox.

        Args:
            timeout: Max seconds to wait
            poll_interval: Seconds between polls

        Returns:
            The new message, or None if timeout
        """
        import time
        existing = {m["msg_id"] for m in self.inbox()}
        start = time.time()
        while time.time() - start < timeout:
            messages = self.inbox()
            for msg in messages:
                if msg["msg_id"] not in existing:
                    return msg
            time.sleep(poll_interval)
        return None
