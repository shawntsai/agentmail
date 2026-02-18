#!/usr/bin/env python3
"""AgentMail Relay Server — run standalone.

Usage:
    python run_relay.py                  # default port 7445
    python run_relay.py --port 7445      # custom port

The relay stores encrypted blobs for offline recipients.
It cannot read any message content.
"""

import argparse

import uvicorn

from agentmaild.relay_server import relay_app


def main():
    parser = argparse.ArgumentParser(description="AgentMail Relay Server")
    parser.add_argument("--port", type=int, default=7445, help="Port to listen on")
    parser.add_argument("--data-dir", default="relay_data", help="Data directory")
    args = parser.parse_args()

    relay_app.state.data_dir = args.data_dir

    print(f"\n  AgentMail Relay v0.1.0")
    print(f"  Port:  {args.port}")
    print(f"  Data:  {args.data_dir}\n")

    uvicorn.run(relay_app, host="0.0.0.0", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
