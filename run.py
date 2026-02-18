#!/usr/bin/env python3
"""AgentMail — Local-first, peer-to-peer agent communication.

Usage:
    python run.py                          # default node
    python run.py --name alice --port 7443
    python run.py --name bob --port 7444   # second node on same machine

Then open http://<your-lan-ip>:<port> on your iPhone or browser.
"""

import argparse
import logging
import sys

import uvicorn

from agentmaild.config import NodeConfig
from agentmaild.main import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(description="AgentMail daemon")
    parser.add_argument("--name", default="my-node", help="Node name (e.g. alice, bob)")
    parser.add_argument("--port", type=int, default=7443, help="Port to listen on")
    parser.add_argument("--data-dir", default=None, help="Data directory (default: ./agentmail_data_<name>)")
    parser.add_argument("--relay", default="", help="Relay server URL (e.g. http://localhost:7445)")
    args = parser.parse_args()

    data_dir = args.data_dir or f"./agentmail_data_{args.name}"

    config = NodeConfig(
        node_name=args.name,
        port=args.port,
        data_dir=data_dir,
        relay_url=args.relay,
    )

    # Attach config to app state so lifespan can read it
    app.state.config = config

    print(f"\n  AgentMail v0.1.0")
    print(f"  Node:  {args.name}")
    print(f"  Port:  {args.port}")
    print(f"  Data:  {data_dir}")
    if args.relay:
        print(f"  Relay: {args.relay}")
    print()

    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
