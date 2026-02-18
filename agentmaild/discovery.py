"""mDNS/Bonjour LAN peer discovery using zeroconf (async API)."""

import asyncio
import logging
import socket
from typing import Callable, Optional

from zeroconf import IPVersion, ServiceInfo, ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_agentmail._tcp.local."


class PeerDiscovery:
    """Advertise this node and discover peers on LAN via mDNS."""

    def __init__(
        self,
        node_id: str,
        node_name: str,
        port: int,
        pubkey: str,
        encrypt_pubkey: str,
        on_peer_found: Optional[Callable] = None,
        on_peer_removed: Optional[Callable] = None,
    ):
        self.node_id = node_id
        self.node_name = node_name
        self.port = port
        self.pubkey = pubkey
        self.encrypt_pubkey = encrypt_pubkey
        self.on_peer_found = on_peer_found
        self.on_peer_removed = on_peer_removed
        self._async_zc: Optional[AsyncZeroconf] = None
        self._browser: Optional[AsyncServiceBrowser] = None
        self._service_info: Optional[ServiceInfo] = None

    def _get_local_ip(self) -> str:
        """Get the LAN IP address of this machine."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
        finally:
            s.close()

    async def start(self):
        """Start advertising and browsing (async)."""
        self._async_zc = AsyncZeroconf(ip_version=IPVersion.V4Only)

        local_ip = self._get_local_ip()
        service_name = f"{self.node_name}-{self.node_id[:8]}.{SERVICE_TYPE}"

        properties = {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "pubkey": self.pubkey,
            "encrypt_pubkey": self.encrypt_pubkey,
            "v": "0",
        }

        self._service_info = ServiceInfo(
            SERVICE_TYPE,
            service_name,
            addresses=[socket.inet_aton(local_ip)],
            port=self.port,
            properties=properties,
        )

        await self._async_zc.async_register_service(self._service_info, allow_name_change=True)
        logger.info(f"Advertising as {service_name} at {local_ip}:{self.port}")

        self._browser = AsyncServiceBrowser(
            self._async_zc.zeroconf,
            SERVICE_TYPE,
            handlers=[self._on_service_state_change],
        )
        logger.info("Browsing for peers...")

    def _on_service_state_change(
        self, zeroconf, service_type: str, name: str, state_change: ServiceStateChange
    ):
        """Handle discovered service — schedule async resolution."""
        if state_change == ServiceStateChange.Added:
            asyncio.ensure_future(self._async_resolve_and_add(zeroconf, service_type, name))
        elif state_change == ServiceStateChange.Removed:
            if self.on_peer_removed:
                self.on_peer_removed(name)

    async def _async_resolve_and_add(self, zeroconf, service_type: str, name: str):
        """Resolve service info asynchronously and register peer."""
        try:
            info = AsyncServiceInfo(service_type, name)
            if await info.async_request(zeroconf, 3000):
                if info.properties:
                    props = {k.decode(): v.decode() for k, v in info.properties.items()}
                    peer_node_id = props.get("node_id", "")

                    # Don't discover ourselves
                    if peer_node_id == self.node_id:
                        return

                    addresses = info.parsed_addresses()
                    if addresses and self.on_peer_found:
                        peer_data = {
                            "node_id": peer_node_id,
                            "node_name": props.get("node_name", "unknown"),
                            "host": addresses[0],
                            "port": info.port,
                            "pubkey": props.get("pubkey", ""),
                            "encrypt_pubkey": props.get("encrypt_pubkey", ""),
                        }
                        logger.info(f"Discovered peer: {peer_data['node_name']} at {peer_data['host']}:{peer_data['port']}")
                        self.on_peer_found(peer_data)
        except Exception as e:
            logger.warning(f"Failed to resolve service {name}: {e}")

    async def stop(self):
        """Stop advertising and browsing (async)."""
        if self._browser:
            await self._browser.async_cancel()
        if self._service_info and self._async_zc:
            await self._async_zc.async_unregister_service(self._service_info)
        if self._async_zc:
            await self._async_zc.async_close()
        logger.info("Discovery stopped.")
