"""Path sanitization for file operations."""

from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import unquote


class PathValidationError(Exception):
    """Raised when a file path fails validation."""


class PathSanitizer:
    def __init__(self, allowed_extensions: list[str], max_size_mb: int = 50) -> None:
        self._allowed_extensions = {ext.lower() for ext in allowed_extensions}
        self._max_size_bytes = max_size_mb * 1024 * 1024

    def validate_filename(self, filename: str) -> str:
        """Validate and sanitize a filename. Returns the clean filename or raises."""
        decoded = unquote(filename)

        if "\x00" in decoded:
            raise PathValidationError(f"Filename contains null byte: {filename!r}")

        if len(decoded) > 255:
            raise PathValidationError("Filename too long (max 255 characters)")

        normalized = decoded.replace("\\", "/")

        if normalized.startswith("/"):
            raise PathValidationError(f"Filename is an absolute path: {filename!r}")

        parts = PurePosixPath(normalized).parts
        if ".." in parts:
            raise PathValidationError(f"Filename contains path traversal: {filename!r}")

        suffix = PurePosixPath(normalized).suffix.lower()
        if not suffix or suffix not in self._allowed_extensions:
            raise PathValidationError(
                f"Disallowed file extension {suffix!r}. Allowed: {sorted(self._allowed_extensions)}"
            )

        return normalized

    def validate_subfolder(self, subfolder: str) -> str:
        """Validate and sanitize a subfolder path."""
        if not subfolder:
            return ""

        decoded = unquote(subfolder)

        if "\x00" in decoded:
            raise PathValidationError(f"Subfolder contains null byte: {subfolder!r}")

        normalized = decoded.replace("\\", "/").strip("/")

        if normalized.startswith("/"):
            raise PathValidationError(f"Subfolder is an absolute path: {subfolder!r}")

        parts = PurePosixPath(normalized).parts
        if ".." in parts:
            raise PathValidationError(f"Subfolder contains path traversal: {subfolder!r}")

        if any(c in normalized for c in ["\n", "\r", "\0"]):
            raise PathValidationError(f"Subfolder contains invalid characters: {subfolder!r}")

        return normalized

    def validate_size(self, size_bytes: int) -> None:
        """Validate file size against the configured maximum."""
        if size_bytes < 0:
            raise PathValidationError("File size cannot be negative")
        if size_bytes > self._max_size_bytes:
            max_mb = self._max_size_bytes / (1024 * 1024)
            actual_mb = size_bytes / (1024 * 1024)
            raise PathValidationError(f"File size {actual_mb:.1f}MB exceeds maximum {max_mb:.0f}MB")
