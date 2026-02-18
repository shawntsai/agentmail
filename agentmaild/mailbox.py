"""Local SQLite mailbox store."""

import json
import sqlite3
from typing import Optional

from .models import MessageEnvelope, PeerInfo


class Mailbox:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                msg_id TEXT PRIMARY KEY,
                thread_id TEXT,
                from_addr TEXT NOT NULL,
                to_addr TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                subject TEXT DEFAULT '',
                intent TEXT DEFAULT 'human_message',
                body TEXT DEFAULT '',
                envelope_json TEXT NOT NULL,
                encrypted INTEGER DEFAULT 0,
                direction TEXT NOT NULL,
                status TEXT DEFAULT 'delivered',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS peers (
                node_id TEXT PRIMARY KEY,
                node_name TEXT NOT NULL,
                address TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                pubkey TEXT NOT NULL,
                encrypt_pubkey TEXT NOT NULL,
                last_seen TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS outbox_queue (
                msg_id TEXT PRIMARY KEY,
                to_addr TEXT NOT NULL,
                envelope_json TEXT NOT NULL,
                attempts INTEGER DEFAULT 0,
                next_retry TEXT,
                status TEXT DEFAULT 'pending'
            );

            CREATE INDEX IF NOT EXISTS idx_messages_direction ON messages(direction);
            CREATE INDEX IF NOT EXISTS idx_messages_from ON messages(from_addr);
            CREATE INDEX IF NOT EXISTS idx_messages_to ON messages(to_addr);
            CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox_queue(status);
        """)

    def store_message(self, envelope: MessageEnvelope, direction: str, status: str = "delivered"):
        self._conn.execute(
            """INSERT OR REPLACE INTO messages
               (msg_id, thread_id, from_addr, to_addr, sent_at, subject, intent, body,
                envelope_json, encrypted, direction, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                envelope.msg_id,
                envelope.thread_id,
                envelope.from_addr,
                envelope.to_addr,
                envelope.sent_at,
                envelope.payload.subject,
                envelope.payload.intent,
                envelope.payload.body,
                envelope.model_dump_json(),
                1 if envelope.encrypted else 0,
                direction,
                status,
            ),
        )
        self._conn.commit()

    def get_messages(self, direction: Optional[str] = None, limit: int = 100) -> list[dict]:
        if direction:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE direction = ? ORDER BY sent_at DESC LIMIT ?",
                (direction, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM messages ORDER BY sent_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_message(self, msg_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM messages WHERE msg_id = ?", (msg_id,)
        ).fetchone()
        return dict(row) if row else None

    def upsert_peer(self, peer: PeerInfo):
        self._conn.execute(
            """INSERT OR REPLACE INTO peers
               (node_id, node_name, address, host, port, pubkey, encrypt_pubkey, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                peer.node_id,
                peer.node_name,
                peer.address,
                peer.host,
                peer.port,
                peer.pubkey,
                peer.encrypt_pubkey,
                peer.last_seen,
            ),
        )
        self._conn.commit()

    def get_peers(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM peers ORDER BY last_seen DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_peer_by_address(self, address: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM peers WHERE address = ?", (address,)
        ).fetchone()
        return dict(row) if row else None

    def queue_outbox(self, envelope: MessageEnvelope):
        self._conn.execute(
            """INSERT OR REPLACE INTO outbox_queue (msg_id, to_addr, envelope_json, status)
               VALUES (?, ?, ?, 'pending')""",
            (envelope.msg_id, envelope.to_addr, envelope.model_dump_json()),
        )
        self._conn.commit()

    def get_pending_outbox(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM outbox_queue WHERE status = 'pending' ORDER BY rowid"
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_outbox_sent(self, msg_id: str):
        self._conn.execute(
            "UPDATE outbox_queue SET status = 'sent' WHERE msg_id = ?", (msg_id,)
        )
        self._conn.commit()

    def mark_outbox_failed(self, msg_id: str, attempts: int):
        self._conn.execute(
            "UPDATE outbox_queue SET status = 'pending', attempts = ? WHERE msg_id = ?",
            (attempts, msg_id),
        )
        self._conn.commit()
