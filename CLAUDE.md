# AgentMail

## Overview

AgentMail is a local-first, P2P encrypted messaging protocol for AI agents. The codebase is Python 3.14+ with FastAPI.

## Project Structure

- `agentmaild/` — core daemon package
  - `crypto.py` — Ed25519 signing + X25519 sealed box encryption (PyNaCl)
  - `models.py` — Pydantic models: MessageEnvelope, MessagePayload, PeerInfo
  - `mailbox.py` — SQLite storage for messages, peers, outbox queue
  - `discovery.py` — AsyncZeroconf mDNS peer discovery on LAN
  - `router.py` — message routing: P2P direct → relay lookup → relay deposit → outbox queue
  - `main.py` — FastAPI app with lifespan, background loops, API endpoints
  - `relay_server.py` — standalone relay: store-and-forward + name registry
  - `client.py` — Python SDK for agents to send/receive messages
  - `web/index.html` — mobile-friendly dark theme SPA
- `agentmail-plugin/` — Claude Code plugin (MCP server with 2 tools: send, inbox)
- `run.py` — CLI entry point for agent node
- `run_relay.py` — CLI entry point for relay server
- `deploy/` — Oracle Cloud VPS deployment scripts

## Key Patterns

- All async: uses AsyncZeroconf, httpx.AsyncClient, asyncio background tasks
- Identity is Ed25519 keypair stored in `{data_dir}/keys/identity.json`
- Fingerprints are URL-safe base64 (first 16 chars of urlsafe_b64encode(pubkey))
- Messages are encrypted with X25519 sealed box before P2P or relay delivery
- Relay at 147.224.10.61:7445 — name registry + encrypted blob store

## Running

```bash
# Activate venv
source .venv/bin/activate

# Start a node
python run.py --name alice --port 7443 --relay http://147.224.10.61:7445

# Start relay
python run_relay.py --port 7445
```

## Common Issues

- **zeroconf**: Must use AsyncZeroconf + AsyncServiceInfo (not sync versions) — uvicorn's event loop conflicts
- **Fingerprints**: Must use urlsafe_b64encode (standard base64 has `/` and `+` which break URLs)
- **Peer conflicts**: If a node restarts with new identity, other nodes may have stale cached keys — delete stale peers from SQLite
- **Oracle VM**: Uses `opc` user, `dnf` not `apt`, SELinux requires bash wrapper for systemd
