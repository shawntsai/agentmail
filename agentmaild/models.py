"""Message and peer models."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


def new_msg_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentInfo(BaseModel):
    name: str = "default"
    capabilities: list[str] = []
    requires_human_approval: bool = False


class MessagePayload(BaseModel):
    intent: str = "human_message"  # task|notify|ask|tool_call|tool_result|human_message
    subject: str = ""
    body: str = ""
    agent: Optional[AgentInfo] = None
    metadata: dict = {}


class MessageEnvelope(BaseModel):
    v: int = 0
    msg_id: str = Field(default_factory=new_msg_id)
    thread_id: Optional[str] = None
    from_addr: str
    to_addr: str
    sent_at: str = Field(default_factory=now_iso)
    ttl_sec: int = 604800  # 7 days
    signature: Optional[str] = None
    encrypted: bool = False
    payload: MessagePayload = Field(default_factory=MessagePayload)


class PeerInfo(BaseModel):
    node_id: str
    node_name: str
    address: str  # e.g. "alice@alice.local"
    host: str  # IP
    port: int
    pubkey: str  # base64 verify key
    encrypt_pubkey: str  # base64 encryption key
    last_seen: str = Field(default_factory=now_iso)


class SendRequest(BaseModel):
    to: str  # recipient address
    subject: str = ""
    body: str = ""
    intent: str = "human_message"
    encrypt: bool = True


class NodeIdentity(BaseModel):
    node_id: str
    node_name: str
    address: str
    pubkey: str
    encrypt_pubkey: str
    fingerprint: str
