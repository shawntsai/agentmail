#!/usr/bin/env python3
"""Example: A simple AI agent that listens on AgentMail and responds.

This agent:
  1. Connects to its own AgentMail node
  2. Polls for new messages
  3. Processes them and sends replies

Usage:
  # Terminal 1: Start the agent's mail node
  python run.py --name agent --port 7444 --relay http://147.224.10.61:7445

  # Terminal 2: Run the agent
  python examples/simple_agent.py --node http://localhost:7444

  # Terminal 3: Send it a message from alice
  python run.py --name alice --port 7443 --relay http://147.224.10.61:7445
  # Then from another terminal:
  python examples/send_to_agent.py
"""

import argparse
import time
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agentmaild.client import AgentMailClient


def handle_message(client: AgentMailClient, msg: dict):
    """Process an incoming message and send a reply."""
    sender = msg["from_addr"]
    intent = msg["intent"]
    subject = msg["subject"]
    body = msg["body"]

    print(f"\n  New message from: {sender}")
    print(f"  Intent:  {intent}")
    print(f"  Subject: {subject}")
    print(f"  Body:    {body[:200]}")

    # Route based on intent
    if intent == "task":
        # Agent received a task
        print(f"  -> Processing task...")
        # In a real agent, you'd call an LLM here
        reply_body = f"Task received and processed: {body[:100]}"
        client.send(
            to=sender,
            subject=f"Re: {subject}",
            body=reply_body,
            intent="tool_result",
        )
        print(f"  -> Reply sent to {sender}")

    elif intent == "tool_call":
        # Agent received a tool call
        try:
            data = json.loads(body)
            tool = data.get("tool", "unknown")
            args = data.get("arguments", {})
            print(f"  -> Executing tool: {tool} with args: {args}")
            # In a real agent, you'd execute the tool here
            result = f"Tool '{tool}' executed successfully with args: {json.dumps(args)}"
            client.send_tool_result(to=sender, tool_name=tool, result=result)
            print(f"  -> Tool result sent to {sender}")
        except json.JSONDecodeError:
            client.send(to=sender, subject="Error", body="Invalid tool_call format", intent="notify")

    elif intent == "ask":
        # Someone is asking the agent a question
        print(f"  -> Answering question...")
        # In a real agent, you'd call an LLM here
        reply_body = f"Thanks for your question about: {subject}. Here is my answer: [agent would respond here]"
        client.send(to=sender, subject=f"Re: {subject}", body=reply_body, intent="human_message")
        print(f"  -> Answer sent to {sender}")

    else:
        # Generic human message — just acknowledge
        print(f"  -> Acknowledging message...")
        client.send(
            to=sender,
            subject=f"Re: {subject}",
            body=f"Got your message: '{body[:50]}'. I'm an agent — send me a task or tool_call for action.",
            intent="notify",
        )
        print(f"  -> Acknowledgment sent to {sender}")


def main():
    parser = argparse.ArgumentParser(description="Simple AgentMail agent")
    parser.add_argument("--node", default="http://localhost:7444", help="AgentMail node URL")
    parser.add_argument("--poll", type=float, default=3, help="Poll interval in seconds")
    args = parser.parse_args()

    client = AgentMailClient(args.node)

    # Get identity
    me = client.identity()
    print(f"\n  Agent running on AgentMail")
    print(f"  Address: {me['address']}")
    print(f"  Node:    {args.node}")
    print(f"  Waiting for messages...\n")

    # Track seen messages
    seen = {m["msg_id"] for m in client.inbox()}
    print(f"  ({len(seen)} existing messages in inbox)\n")

    # Poll loop
    while True:
        try:
            messages = client.inbox()
            for msg in messages:
                if msg["msg_id"] not in seen:
                    seen.add(msg["msg_id"])
                    handle_message(client, msg)
        except KeyboardInterrupt:
            print("\n  Agent stopped.")
            break
        except Exception as e:
            print(f"  Error: {e}")
        time.sleep(args.poll)


if __name__ == "__main__":
    main()
