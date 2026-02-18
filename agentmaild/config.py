"""Node configuration and identity persistence."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class NodeConfig:
    node_name: str = "my-node"
    port: int = 7443
    data_dir: str = "./agentmail_data"
    host: str = "0.0.0.0"
    relay_url: str = ""  # e.g. "http://localhost:7445" or "http://your-server:7445"

    @property
    def db_path(self) -> str:
        return os.path.join(self.data_dir, "mailbox.db")

    @property
    def keys_dir(self) -> str:
        return os.path.join(self.data_dir, "keys")

    @property
    def identity_path(self) -> str:
        return os.path.join(self.keys_dir, "identity.json")

    def ensure_dirs(self):
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        Path(self.keys_dir).mkdir(parents=True, exist_ok=True)
