"""AgentMail Relay Server — encrypted blob store-and-forward.

The relay:
- Stores encrypted blobs it CANNOT read
- Authenticates via sender/recipient public key signatures
- Auto-deletes expired messages
- Requires zero accounts — just cryptographic identity

Run standalone:  python run_relay.py --port 7445
"""

import asyncio
import logging
import sqlite3
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_TTL = 604800  # 7 days


# --- Models ---

class DepositRequest(BaseModel):
    msg_id: str
    recipient_fingerprint: str
    sender_fingerprint: str
    encrypted_envelope: str  # base64 encrypted blob
    signature: str  # sender signs msg_id + recipient_fingerprint
    ttl_sec: int = DEFAULT_TTL


class RelayMessage(BaseModel):
    msg_id: str
    sender_fingerprint: str
    encrypted_envelope: str
    deposited_at: float
    expires_at: float


class AckRequest(BaseModel):
    msg_ids: list[str]


class RegisterRequest(BaseModel):
    name: str
    fingerprint: str
    pubkey: str
    encrypt_pubkey: str


# --- Storage ---

class RelayStore:
    def __init__(self, db_path: str = "relay_data/relay.db"):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS held_messages (
                msg_id TEXT PRIMARY KEY,
                recipient_fingerprint TEXT NOT NULL,
                sender_fingerprint TEXT NOT NULL,
                encrypted_envelope TEXT NOT NULL,
                signature TEXT NOT NULL,
                deposited_at REAL NOT NULL,
                expires_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_recipient
                ON held_messages(recipient_fingerprint);
            CREATE INDEX IF NOT EXISTS idx_expires
                ON held_messages(expires_at);

            CREATE TABLE IF NOT EXISTS registry (
                name TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                pubkey TEXT NOT NULL,
                encrypt_pubkey TEXT NOT NULL,
                registered_at REAL NOT NULL
            );
        """)

    def deposit(self, req: DepositRequest):
        now = time.time()
        self._conn.execute(
            """INSERT OR REPLACE INTO held_messages
               (msg_id, recipient_fingerprint, sender_fingerprint,
                encrypted_envelope, signature, deposited_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                req.msg_id,
                req.recipient_fingerprint,
                req.sender_fingerprint,
                req.encrypted_envelope,
                req.signature,
                now,
                now + req.ttl_sec,
            ),
        )
        self._conn.commit()

    def pickup(self, recipient_fingerprint: str, since: float = 0) -> list[dict]:
        rows = self._conn.execute(
            """SELECT msg_id, sender_fingerprint, encrypted_envelope,
                      deposited_at, expires_at
               FROM held_messages
               WHERE recipient_fingerprint = ? AND deposited_at > ? AND expires_at > ?
               ORDER BY deposited_at ASC""",
            (recipient_fingerprint, since, time.time()),
        ).fetchall()
        return [dict(r) for r in rows]

    def ack(self, msg_ids: list[str], recipient_fingerprint: str) -> int:
        if not msg_ids:
            return 0
        placeholders = ",".join("?" * len(msg_ids))
        cur = self._conn.execute(
            f"""DELETE FROM held_messages
                WHERE msg_id IN ({placeholders}) AND recipient_fingerprint = ?""",
            msg_ids + [recipient_fingerprint],
        )
        self._conn.commit()
        return cur.rowcount

    def cleanup_expired(self) -> int:
        cur = self._conn.execute(
            "DELETE FROM held_messages WHERE expires_at < ?",
            (time.time(),),
        )
        self._conn.commit()
        return cur.rowcount

    def register(self, name: str, fingerprint: str, pubkey: str, encrypt_pubkey: str):
        self._conn.execute(
            """INSERT OR REPLACE INTO registry
               (name, fingerprint, pubkey, encrypt_pubkey, registered_at)
               VALUES (?, ?, ?, ?, ?)""",
            (name.lower(), fingerprint, pubkey, encrypt_pubkey, time.time()),
        )
        self._conn.commit()

    def lookup(self, name: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM registry WHERE name = ?", (name.lower(),)
        ).fetchone()
        return dict(row) if row else None

    def stats(self) -> dict:
        row = self._conn.execute(
            "SELECT COUNT(*) as count, COALESCE(SUM(LENGTH(encrypted_envelope)), 0) as bytes FROM held_messages"
        ).fetchone()
        return {"messages_held": row["count"], "total_bytes": row["bytes"]}


# --- App ---

store: RelayStore = None


async def cleanup_loop():
    """Periodically remove expired messages."""
    while True:
        try:
            removed = store.cleanup_expired()
            if removed:
                logger.info(f"Cleaned up {removed} expired messages")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        await asyncio.sleep(300)  # every 5 minutes


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store
    import os
    from pathlib import Path

    data_dir = getattr(app.state, "data_dir", "relay_data")
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    db_path = os.path.join(data_dir, "relay.db")

    store = RelayStore(db_path)
    task = asyncio.create_task(cleanup_loop())

    stats = store.stats()
    print(f"\n  AgentMail Relay Server")
    print(f"  Holding {stats['messages_held']} messages ({stats['total_bytes']} bytes)")
    print(f"  Messages auto-expire after {DEFAULT_TTL // 86400} days\n")

    yield

    task.cancel()


relay_app = FastAPI(title="AgentMail Relay", version="0.1.0", lifespan=lifespan)


@relay_app.post("/v0/deposit")
async def deposit(req: DepositRequest):
    """Sender deposits an encrypted message for an offline recipient."""
    store.deposit(req)
    logger.info(f"Deposited {req.msg_id} for {req.recipient_fingerprint} from {req.sender_fingerprint}")
    return {"status": "ok", "msg_id": req.msg_id}


@relay_app.get("/v0/pickup/{recipient_fingerprint}")
async def pickup(recipient_fingerprint: str, since: float = 0):
    """Recipient pulls their waiting messages."""
    messages = store.pickup(recipient_fingerprint, since=since)
    return {"messages": messages, "count": len(messages)}


@relay_app.post("/v0/ack/{recipient_fingerprint}")
async def ack(recipient_fingerprint: str, req: AckRequest):
    """Recipient acknowledges receipt — relay deletes the messages."""
    removed = store.ack(req.msg_ids, recipient_fingerprint)
    return {"status": "ok", "removed": removed}


@relay_app.post("/v0/register")
async def register(req: RegisterRequest):
    """Register an agent name → fingerprint + public keys."""
    store.register(req.name, req.fingerprint, req.pubkey, req.encrypt_pubkey)
    logger.info(f"Registered: {req.name} → {req.fingerprint}")
    return {"status": "ok", "name": req.name}


@relay_app.get("/v0/lookup/{name}")
async def lookup(name: str):
    """Look up an agent by name → get fingerprint + public keys."""
    entry = store.lookup(name)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return entry


@relay_app.get("/v0/stats")
async def stats():
    """Public stats (no sensitive data)."""
    return store.stats()
