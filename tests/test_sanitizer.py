"""Tests for path sanitization."""

import pytest

from comfyui_mcp.security.sanitizer import PathSanitizer, PathValidationError


class TestPathSanitizer:
    @pytest.fixture
    def sanitizer(self):
        return PathSanitizer(
            allowed_extensions=[".png", ".jpg", ".jpeg", ".webp", ".json"],
            max_size_mb=50,
        )

    def test_clean_filename_passes(self, sanitizer):
        result = sanitizer.validate_filename("image_001.png")
        assert result == "image_001.png"

    def test_subdirectory_filename_passes(self, sanitizer):
        result = sanitizer.validate_filename("subfolder/image.png")
        assert result == "subfolder/image.png"

    def test_path_traversal_blocked(self, sanitizer):
        with pytest.raises(PathValidationError, match="traversal"):
            sanitizer.validate_filename("../../etc/passwd")

    def test_path_traversal_encoded_blocked(self, sanitizer):
        with pytest.raises(PathValidationError, match="traversal"):
            sanitizer.validate_filename("..%2F..%2Fetc%2Fpasswd")

    def test_null_byte_blocked(self, sanitizer):
        with pytest.raises(PathValidationError, match="null"):
            sanitizer.validate_filename("image.png\x00.sh")

    def test_absolute_path_blocked(self, sanitizer):
        with pytest.raises(PathValidationError, match="absolute"):
            sanitizer.validate_filename("/etc/passwd")

    def test_disallowed_extension_blocked(self, sanitizer):
        with pytest.raises(PathValidationError, match="extension"):
            sanitizer.validate_filename("script.py")

    def test_no_extension_blocked(self, sanitizer):
        with pytest.raises(PathValidationError, match="extension"):
            sanitizer.validate_filename("Makefile")

    def test_double_extension_uses_last(self, sanitizer):
        result = sanitizer.validate_filename("photo.backup.png")
        assert result == "photo.backup.png"

    def test_validate_size_passes(self, sanitizer):
        sanitizer.validate_size(1024 * 1024)  # 1 MB

    def test_validate_size_too_large(self, sanitizer):
        with pytest.raises(PathValidationError, match="size"):
            sanitizer.validate_size(100 * 1024 * 1024)  # 100 MB

    def test_backslash_traversal_blocked(self, sanitizer):
        with pytest.raises(PathValidationError, match="traversal"):
            sanitizer.validate_filename("..\\..\\windows\\system32")


class TestSubfolderValidation:
    @pytest.fixture
    def sanitizer(self):
        return PathSanitizer(
            allowed_extensions=[".png", ".jpg"],
            max_size_mb=50,
        )

    def test_empty_subfolder_passes(self, sanitizer):
        assert sanitizer.validate_subfolder("") == ""

    def test_simple_subfolder_passes(self, sanitizer):
        assert sanitizer.validate_subfolder("inputs") == "inputs"

    def test_nested_subfolder_passes(self, sanitizer):
        assert sanitizer.validate_subfolder("inputs/masks") == "inputs/masks"

    def test_traversal_blocked(self, sanitizer):
        with pytest.raises(PathValidationError, match="traversal"):
            sanitizer.validate_subfolder("../../../etc")

    def test_null_byte_blocked(self, sanitizer):
        with pytest.raises(PathValidationError, match="null"):
            sanitizer.validate_subfolder("inputs\x00evil")

    def test_absolute_path_stripped(self, sanitizer):
        result = sanitizer.validate_subfolder("/inputs/")
        assert not result.startswith("/")

    def test_encoded_traversal_blocked(self, sanitizer):
        with pytest.raises(PathValidationError, match="traversal"):
            sanitizer.validate_subfolder("..%2F..%2Fetc")

    def test_control_characters_blocked(self, sanitizer):
        with pytest.raises(PathValidationError, match="invalid"):
            sanitizer.validate_subfolder("inputs\nmalicious")


class TestPathSegmentValidation:
    @pytest.fixture
    def sanitizer(self):
        return PathSanitizer(allowed_extensions=[".png", ".jpg"])

    def test_valid_segment(self, sanitizer):
        assert sanitizer.validate_path_segment("checkpoints", "folder") == "checkpoints"

    def test_empty_segment_blocked(self, sanitizer):
        with pytest.raises(PathValidationError, match="must not be empty"):
            sanitizer.validate_path_segment("", "folder")

    def test_traversal_blocked(self, sanitizer):
        with pytest.raises(PathValidationError, match="path traversal"):
            sanitizer.validate_path_segment("..", "folder")

    def test_slash_blocked(self, sanitizer):
        with pytest.raises(PathValidationError, match="path separator"):
            sanitizer.validate_path_segment("a/b", "folder")

    def test_backslash_blocked(self, sanitizer):
        with pytest.raises(PathValidationError, match="path separator"):
            sanitizer.validate_path_segment("a\\b", "folder")

    def test_null_byte_blocked(self, sanitizer):
        with pytest.raises(PathValidationError, match="null byte"):
            sanitizer.validate_path_segment("check\x00points", "folder")

    def test_encoded_traversal_blocked(self, sanitizer):
        with pytest.raises(PathValidationError, match="path traversal"):
            sanitizer.validate_path_segment("%2e%2e", "folder")

    def test_newline_blocked(self, sanitizer):
        with pytest.raises(PathValidationError, match="invalid characters"):
            sanitizer.validate_path_segment("check\npoints", "folder")
