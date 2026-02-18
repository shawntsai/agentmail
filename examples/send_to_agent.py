#!/usr/bin/env python3
"""Example: Send messages to an agent from Alice's node.

Usage:
  # Make sure alice (port 7443) and agent (port 7444) are running
  python examples/send_to_agent.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agentmail import AgentMailClient

alice = AgentMailClient("http://localhost:7443")

print("\n  Sending messages to agent@agent.local...\n")

# 1. Send a regular message
print("  1. Sending human message...")
r = alice.send("agent@agent.local", subject="Hello agent", body="Hey, are you there?")
print(f"     -> {r['status']} (delivered={r['delivered']})")

# 2. Send a task
print("  2. Sending task...")
r = alice.send_task("agent@agent.local", task="Summarize the latest AI news", metadata={"priority": "high"})
print(f"     -> {r['status']} (delivered={r['delivered']})")

# 3. Send a tool call
print("  3. Sending tool_call...")
r = alice.send_tool_call("agent@agent.local", tool_name="web_search", arguments={"query": "AgentMail protocol"})
print(f"     -> {r['status']} (delivered={r['delivered']})")

# 4. Wait for replies
print("\n  Waiting for agent replies...")
import time
time.sleep(5)

replies = alice.inbox()
print(f"\n  Alice inbox ({len(replies)} messages):")
for msg in replies:
    print(f"    From: {msg['from_addr']}")
    print(f"    Subject: {msg['subject']}")
    print(f"    Body: {msg['body'][:100]}")
    print()
