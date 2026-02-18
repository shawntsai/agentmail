"""FastAPI application — the AgentMail daemon."""

import asyncio
import logging
import os
import socket
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import NodeConfig
from .crypto import Identity
from .discovery import PeerDiscovery
from .mailbox import Mailbox
from .models import MessageEnvelope, NodeIdentity, PeerInfo, SendRequest, now_iso
from .router import Router

logger = logging.getLogger(__name__)

# Global state (initialized at startup)
config: NodeConfig = None
identity: Identity = None
mailbox: Mailbox = None
discovery: PeerDiscovery = None
router: Router = None
node_address: str = ""
retry_task: asyncio.Task = None


def on_peer_found(peer_data: dict):
    """Called by discovery when a new peer appears on LAN."""
    address = f"{peer_data['node_name']}@{peer_data['node_name']}.local"
    peer = PeerInfo(
        node_id=peer_data["node_id"],
        node_name=peer_data["node_name"],
        address=address,
        host=peer_data["host"],
        port=peer_data["port"],
        pubkey=peer_data["pubkey"],
        encrypt_pubkey=peer_data["encrypt_pubkey"],
        last_seen=now_iso(),
    )
    mailbox.upsert_peer(peer)
    logger.info(f"Peer registered: {peer.node_name} ({peer.host}:{peer.port})")


def on_peer_removed(name: str):
    logger.info(f"Peer removed from LAN: {name}")


async def retry_loop():
    """Background task to retry queued messages."""
    while True:
        try:
            await router.retry_queued()
        except Exception as e:
            logger.error(f"Retry loop error: {e}")
        await asyncio.sleep(15)


async def relay_pull_loop():
    """Background task to pull messages from relay."""
    while True:
        try:
            await router.pull_from_relay()
        except Exception as e:
            logger.error(f"Relay pull error: {e}")
        await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global config, identity, mailbox, discovery, router, node_address, retry_task

    # Config comes from app.state (set by run.py)
    config = app.state.config
    config.ensure_dirs()

    # Load or create identity
    identity = Identity.load_or_create(config.identity_path)
    logger.info(f"Node identity: {identity.fingerprint}")

    # Init mailbox
    mailbox = Mailbox(config.db_path)

    # Node address
    node_address = f"{config.node_name}@{config.node_name}.local"

    # Init router (with optional relay)
    router = Router(identity, mailbox, node_address, relay_url=config.relay_url)

    # Start peer discovery
    discovery = PeerDiscovery(
        node_id=identity.fingerprint,
        node_name=config.node_name,
        port=config.port,
        pubkey=identity.pubkey_b64,
        encrypt_pubkey=identity.encrypt_pubkey_b64,
        on_peer_found=on_peer_found,
        on_peer_removed=on_peer_removed,
    )
    await discovery.start()

    # Register with relay (phone book)
    if config.relay_url:
        try:
            import httpx
            httpx.post(f"{config.relay_url.rstrip('/')}/v0/register", json={
                "name": config.node_name,
                "fingerprint": identity.fingerprint,
                "pubkey": identity.pubkey_b64,
                "encrypt_pubkey": identity.encrypt_pubkey_b64,
            }, timeout=5)
            print(f"  Registered as '{config.node_name}' on relay")
        except Exception as e:
            logger.warning(f"Could not register with relay: {e}")

    # Start background loops
    retry_task = asyncio.create_task(retry_loop())
    relay_task = asyncio.create_task(relay_pull_loop()) if config.relay_url else None

    local_ip = discovery._get_local_ip()
    print(f"\n  AgentMail daemon running!")
    print(f"  Address:  {node_address}")
    if config.relay_url:
        print(f"  Relay:    {config.relay_url}")
    print(f"  Web UI:   http://{local_ip}:{config.port}")
    # Show all IPs so user can find the one their phone can reach
    import netifaces
    try:
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface).get(netifaces.AF_INET, [])
            for addr in addrs:
                ip = addr.get("addr", "")
                if ip and ip != "127.0.0.1":
                    print(f"  Also try: http://{ip}:{config.port}  ({iface})")
    except Exception:
        pass
    print(f"\n  Open one of the URLs above on your iPhone (same WiFi)\n")

    yield

    # Shutdown
    retry_task.cancel()
    if relay_task:
        relay_task.cancel()
    await discovery.stop()
    logger.info("AgentMail daemon stopped.")


app = FastAPI(title="AgentMail", version="0.1.0", lifespan=lifespan)


# --- API Routes ---


@app.get("/v0/identity")
async def get_identity() -> NodeIdentity:
    return NodeIdentity(
        node_id=identity.fingerprint,
        node_name=config.node_name,
        address=node_address,
        pubkey=identity.pubkey_b64,
        encrypt_pubkey=identity.encrypt_pubkey_b64,
        fingerprint=identity.fingerprint,
    )


@app.get("/v0/peers")
async def get_peers():
    return mailbox.get_peers()


@app.get("/v0/messages")
async def get_messages(direction: str = None, limit: int = 100):
    return mailbox.get_messages(direction=direction, limit=limit)


@app.get("/v0/messages/{msg_id}")
async def get_message(msg_id: str):
    msg = mailbox.get_message(msg_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return msg


@app.post("/v0/send")
async def send_message(req: SendRequest):
    """Send a message from this node."""
    envelope = await router.send(
        to_addr=req.to,
        subject=req.subject,
        body=req.body,
        intent=req.intent,
        encrypt=req.encrypt,
    )
    return {"status": "ok", "msg_id": envelope.msg_id, "delivered": envelope.msg_id not in [
        item["msg_id"] for item in mailbox.get_pending_outbox()
    ]}


@app.post("/v0/inbox")
async def receive_message(envelope: MessageEnvelope):
    """Receive a message from a peer."""
    processed = await router.receive(envelope)
    return {"status": "ok", "msg_id": processed.msg_id}


# --- Web UI ---

WEB_DIR = Path(__file__).parent / "web"


@app.get("/")
async def web_ui():
    return FileResponse(WEB_DIR / "index.html")
