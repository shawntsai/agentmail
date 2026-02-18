---
description: Send a message to an agent via AgentMail
---

Send a message to an agent using the `agentmail_send` MCP tool.

The user said: $ARGUMENTS

Parse the agent name and message from the user's input. Examples:
- "/agentmail:send planner summarize AI news" → agent="planner", message="summarize AI news"
- "/agentmail:send bob hello there" → agent="bob", message="hello there"

Use the `agentmail_send` tool with the parsed agent name and message.
