"""Message routing and delivery to peers, with relay fallback."""

import asyncio
import logging
from typing import Optional

import httpx

from .crypto import Identity
from .mailbox import Mailbox
from .models import MessageEnvelope, MessagePayload, PeerInfo, now_iso

logger = logging.getLogger(__name__)


class Router:
    """Routes messages to local peers or relay."""

    def __init__(self, identity: Identity, mailbox: Mailbox, node_address: str,
                 relay_url: str = ""):
        self.identity = identity
        self.mailbox = mailbox
        self.node_address = node_address
        self.relay_url = relay_url.rstrip("/") if relay_url else ""

    async def send(self, to_addr: str, subject: str, body: str, intent: str = "human_message", encrypt: bool = True) -> MessageEnvelope:
        """Compose, sign, and deliver a message.

        Routing order:
          1. Known peer online → direct P2P
          2. Known peer offline + relay configured → relay deposit
          3. Otherwise → local outbox queue for retry
        """
        envelope = MessageEnvelope(
            from_addr=self.node_address,
            to_addr=to_addr,
            payload=MessagePayload(
                intent=intent,
                subject=subject,
                body=body,
            ),
        )

        # Sign the envelope
        sign_data = f"{envelope.msg_id}:{envelope.from_addr}:{envelope.to_addr}:{envelope.sent_at}".encode()
        envelope.signature = self.identity.sign(sign_data)

        # Route 1-3: Local/P2P/Relay delivery
        peer = self.mailbox.get_peer_by_address(to_addr)

        # If peer unknown locally, look up on relay registry
        if not peer and self.relay_url:
            peer = await self._lookup_from_relay(to_addr)

        if peer and encrypt:
            payload_json = envelope.payload.model_dump_json().encode()
            encrypted = self.identity.encrypt_for(payload_json, peer["encrypt_pubkey"])
            envelope.payload = MessagePayload(
                intent="encrypted",
                subject="[encrypted]",
                body=encrypted,
            )
            envelope.encrypted = True

        self.mailbox.store_message(envelope, direction="outbound", status="sending")

        # Try P2P direct
        delivered = False
        if peer:
            delivered = await self._deliver_to_peer(envelope, peer)

        if not delivered and self.relay_url and peer:
            deposited = await self._deposit_to_relay(envelope, peer)
            if deposited:
                self.mailbox.store_message(envelope, direction="outbound", status="relayed")
                return envelope

        if delivered:
            self.mailbox.store_message(envelope, direction="outbound", status="delivered")
        else:
            self.mailbox.queue_outbox(envelope)
            self.mailbox.store_message(envelope, direction="outbound", status="queued")
            logger.warning(f"Peer not reachable, queued message {envelope.msg_id}")

        return envelope

    async def _lookup_from_relay(self, to_addr: str) -> Optional[dict]:
        """Look up a peer by name from the relay registry."""
        # Extract name from address (e.g. "kai@kai.local" → "kai")
        name = to_addr.split("@")[0] if "@" in to_addr else to_addr
        url = f"{self.relay_url}/v0/lookup/{name}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None
                data = resp.json()
                # Cache as peer for future use
                peer_info = PeerInfo(
                    node_id=data["fingerprint"],
                    node_name=name,
                    address=to_addr,
                    host="",  # no direct IP — relay only
                    port=0,
                    pubkey=data["pubkey"],
                    encrypt_pubkey=data["encrypt_pubkey"],
                    last_seen=now_iso(),
                )
                self.mailbox.upsert_peer(peer_info)
                logger.info(f"Resolved '{name}' from relay registry")
                return {
                    "node_id": data["fingerprint"],
                    "node_name": name,
                    "address": to_addr,
                    "host": "",
                    "port": 0,
                    "pubkey": data["pubkey"],
                    "encrypt_pubkey": data["encrypt_pubkey"],
                }
        except Exception as e:
            logger.warning(f"Relay lookup failed: {e}")
            return None

    async def _deliver_to_peer(self, envelope: MessageEnvelope, peer: dict) -> bool:
        """Deliver a message directly to a peer via HTTP."""
        url = f"http://{peer['host']}:{peer['port']}/v0/inbox"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=envelope.model_dump())
                if resp.status_code == 200:
                    logger.info(f"Delivered {envelope.msg_id} to {peer['host']}:{peer['port']}")
                    return True
                else:
                    logger.warning(f"Delivery failed: {resp.status_code} {resp.text}")
                    return False
        except Exception as e:
            logger.warning(f"Could not reach peer: {e}")
            return False

    async def _deposit_to_relay(self, envelope: MessageEnvelope, peer: dict) -> bool:
        """Deposit encrypted message to relay for offline recipient."""
        url = f"{self.relay_url}/v0/deposit"
        # Compute URL-safe fingerprint matching Identity.fingerprint
        from base64 import b64decode, urlsafe_b64encode
        recipient_fp = urlsafe_b64encode(b64decode(peer["pubkey"])).decode()[:16]
        sig_data = f"{envelope.msg_id}:{recipient_fp}".encode()
        signature = self.identity.sign(sig_data)

        payload = {
            "msg_id": envelope.msg_id,
            "recipient_fingerprint": recipient_fp,
            "sender_fingerprint": self.identity.fingerprint,
            "encrypted_envelope": envelope.model_dump_json(),
            "signature": signature,
            "ttl_sec": envelope.ttl_sec,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    logger.info(f"Deposited {envelope.msg_id} to relay for {recipient_fp}")
                    return True
                else:
                    logger.warning(f"Relay deposit failed: {resp.status_code} {resp.text}")
                    return False
        except Exception as e:
            logger.warning(f"Could not reach relay: {e}")
            return False

    async def pull_from_relay(self):
        """Pull any waiting messages from the relay for this node."""
        if not self.relay_url:
            return
        url = f"{self.relay_url}/v0/pickup/{self.identity.fingerprint}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return
                data = resp.json()
                messages = data.get("messages", [])
                if not messages:
                    return

                acked_ids = []
                for msg in messages:
                    try:
                        envelope = MessageEnvelope.model_validate_json(msg["encrypted_envelope"])
                        await self.receive(envelope)
                        acked_ids.append(msg["msg_id"])
                        logger.info(f"Pulled {msg['msg_id']} from relay")
                    except Exception as e:
                        logger.error(f"Failed to process relay message {msg['msg_id']}: {e}")

                # Acknowledge receipt so relay deletes them
                if acked_ids:
                    ack_url = f"{self.relay_url}/v0/ack/{self.identity.fingerprint}"
                    await client.post(ack_url, json={"msg_ids": acked_ids})
                    logger.info(f"Acknowledged {len(acked_ids)} messages from relay")

        except Exception as e:
            logger.warning(f"Could not pull from relay: {e}")

    async def receive(self, envelope: MessageEnvelope) -> MessageEnvelope:
        """Process an incoming message."""
        # Verify signature if present
        if envelope.signature:
            sign_data = f"{envelope.msg_id}:{envelope.from_addr}:{envelope.to_addr}:{envelope.sent_at}".encode()
            peer = self.mailbox.get_peer_by_address(envelope.from_addr)
            if peer:
                valid = Identity.verify(sign_data, envelope.signature, peer["pubkey"])
                if not valid:
                    logger.warning(f"Invalid signature on message {envelope.msg_id} from {envelope.from_addr}")

        # Decrypt if encrypted
        if envelope.encrypted and envelope.payload.intent == "encrypted":
            try:
                decrypted = self.identity.decrypt(envelope.payload.body)
                original_payload = MessagePayload.model_validate_json(decrypted)
                envelope.payload = original_payload
                envelope.encrypted = False
            except Exception as e:
                logger.error(f"Failed to decrypt message {envelope.msg_id}: {e}")

        # Store locally as inbound (skip if already exists)
        existing = self.mailbox.get_message(envelope.msg_id)
        if existing and existing["direction"] == "inbound":
            return envelope

        self.mailbox.store_message(envelope, direction="inbound")
        logger.info(f"Received message {envelope.msg_id} from {envelope.from_addr}")
        return envelope

    async def retry_queued(self):
        """Retry sending queued messages — try P2P, then relay."""
        pending = self.mailbox.get_pending_outbox()
        for item in pending:
            envelope = MessageEnvelope.model_validate_json(item["envelope_json"])
            peer = self.mailbox.get_peer_by_address(envelope.to_addr)
            if peer:
                delivered = await self._deliver_to_peer(envelope, peer)
                if delivered:
                    self.mailbox.mark_outbox_sent(envelope.msg_id)
                    self.mailbox.store_message(envelope, direction="outbound", status="delivered")
                    logger.info(f"Retry succeeded for {envelope.msg_id}")
                elif self.relay_url:
                    deposited = await self._deposit_to_relay(envelope, peer)
                    if deposited:
                        self.mailbox.mark_outbox_sent(envelope.msg_id)
                        self.mailbox.store_message(envelope, direction="outbound", status="relayed")
                else:
                    self.mailbox.mark_outbox_failed(envelope.msg_id, item["attempts"] + 1)
