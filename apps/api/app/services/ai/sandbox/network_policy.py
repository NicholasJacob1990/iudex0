"""Network security policies for tool execution and web access."""
import ipaddress
import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# Domains allowed for legal research tools
LEGAL_DOMAIN_ALLOWLIST = {
    # Tribunais
    "stf.jus.br", "stj.jus.br", "trf1.jus.br", "trf2.jus.br",
    "trf3.jus.br", "trf4.jus.br", "trf5.jus.br", "trf6.jus.br",
    "tjsp.jus.br", "tjrj.jus.br", "tjmg.jus.br", "tjrs.jus.br",
    "tjpr.jus.br", "tjsc.jus.br",
    # Governo
    "planalto.gov.br", "senado.leg.br", "camara.leg.br",
    "in.gov.br", "gov.br",
    # DataJud
    "datajud.cnj.jus.br", "cnj.jus.br",
    # Diarios
    "dje.tjsp.jus.br", "diario.tjrj.jus.br",
    # Bases juridicas
    "jusbrasil.com.br", "conjur.com.br",
}

# Private/reserved IP ranges (SSRF protection)
PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10 MB


class NetworkPolicy:
    """Enforces network access policies for tool execution."""

    def __init__(
        self,
        domain_allowlist: set[str] | None = None,
        block_private_ips: bool = True,
        max_response_size: int = MAX_RESPONSE_SIZE,
        allow_all_domains: bool = False,
    ):
        self.domain_allowlist = domain_allowlist or LEGAL_DOMAIN_ALLOWLIST
        self.block_private_ips = block_private_ips
        self.max_response_size = max_response_size
        self.allow_all_domains = allow_all_domains

    def check_url(self, url: str) -> tuple[bool, str]:
        """Check if a URL is allowed. Returns (allowed, reason)."""
        try:
            parsed = urlparse(url)
        except Exception:
            return False, "Invalid URL"

        # Require http(s)
        if parsed.scheme not in ("http", "https"):
            return False, f"Scheme '{parsed.scheme}' not allowed"

        hostname = parsed.hostname or ""

        # Block private IPs
        if self.block_private_ips:
            try:
                ip = ipaddress.ip_address(hostname)
                for network in PRIVATE_RANGES:
                    if ip in network:
                        return False, f"Private IP {hostname} blocked (SSRF protection)"
            except ValueError:
                pass  # hostname is a domain, not an IP

        # Domain allowlist
        if not self.allow_all_domains:
            allowed = False
            for domain in self.domain_allowlist:
                if hostname == domain or hostname.endswith(f".{domain}"):
                    allowed = True
                    break
            if not allowed:
                return False, f"Domain '{hostname}' not in allowlist"

        return True, "OK"


# Default policies
STRICT_POLICY = NetworkPolicy(allow_all_domains=False)
PERMISSIVE_POLICY = NetworkPolicy(allow_all_domains=True, block_private_ips=True)


def validate_url(url: str, strict: bool = True) -> tuple[bool, str]:
    """Convenience function to validate a URL."""
    policy = STRICT_POLICY if strict else PERMISSIVE_POLICY
    return policy.check_url(url)
