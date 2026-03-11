"""URL and extension validation for model downloads."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import urlparse


class DownloadValidationError(Exception):
    """Raised when a download URL or filename fails validation."""


# Known direct-download path patterns for allowlisted domains.
_DOMAIN_PATH_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "huggingface.co": [
        re.compile(r"^/[^/]+/[^/]+/resolve/"),  # /{org}/{repo}/resolve/{ref}/...
    ],
    "civitai.com": [
        re.compile(r"^/api/download/"),  # /api/download/models/{id}
    ],
}


class DownloadValidator:
    """Validates download URLs against domain and extension allowlists."""

    def __init__(
        self,
        allowed_domains: list[str],
        allowed_extensions: list[str],
    ) -> None:
        self._allowed_domains = [d.lower() for d in allowed_domains]
        self._allowed_extensions = {ext.lower() for ext in allowed_extensions}

    def validate_url(self, url: str) -> None:
        """Validate that a URL is from an allowed domain with a valid path pattern."""
        parsed = urlparse(url)

        if parsed.scheme != "https":
            raise DownloadValidationError(f"Download URL must use https, got {parsed.scheme!r}")

        hostname = (parsed.hostname or "").lower()
        if not self._is_allowed_domain(hostname):
            raise DownloadValidationError(
                f"Domain {hostname!r} not in allowed domains: {', '.join(self._allowed_domains)}"
            )

        self._validate_path_pattern(hostname, parsed.path)

    def _is_allowed_domain(self, hostname: str) -> bool:
        """Check if hostname matches or is a subdomain of an allowed domain."""
        for domain in self._allowed_domains:
            if hostname == domain or hostname.endswith(f".{domain}"):
                return True
        return False

    def _validate_path_pattern(self, hostname: str, path: str) -> None:
        """Validate URL path against known patterns for specific domains."""
        matched_domain = None
        for domain in self._allowed_domains:
            if hostname == domain or hostname.endswith(f".{domain}"):
                matched_domain = domain
                break

        if matched_domain is None:
            return

        patterns = _DOMAIN_PATH_PATTERNS.get(matched_domain)
        if patterns is None:
            return  # No path restrictions for custom domains

        if not any(p.search(path) for p in patterns):
            raise DownloadValidationError(
                f"URL path {path!r} does not match expected download patterns for {matched_domain}"
            )

    def validate_extension(self, filename: str) -> None:
        """Validate that a filename has an allowed model extension."""
        suffix = PurePosixPath(filename).suffix.lower()
        if not suffix or suffix not in self._allowed_extensions:
            raise DownloadValidationError(
                f"File extension {suffix!r} not allowed. "
                f"Allowed: {sorted(self._allowed_extensions)}"
            )
