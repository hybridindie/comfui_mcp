"""Tests for structured audit logging."""

import asyncio
import json

from comfyui_mcp.audit import AuditLogger, AuditRecord


class TestAuditRecord:
    def test_record_has_required_fields(self):
        record = AuditRecord(tool="run_workflow", action="submitted")
        assert record.tool == "run_workflow"
        assert record.action == "submitted"
        assert record.timestamp is not None

    def test_record_serializes_to_json(self):
        record = AuditRecord(
            tool="run_workflow",
            action="submitted",
            prompt_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            nodes_used=["KSampler", "CLIPTextEncode"],
            warnings=["Dangerous node: EvalNode"],
        )
        data = json.loads(record.model_dump_json())
        assert data["tool"] == "run_workflow"
        assert "KSampler" in data["nodes_used"]
        assert len(data["warnings"]) == 1

    def test_record_omits_empty_fields(self):
        record = AuditRecord(tool="get_queue", action="called")
        data = json.loads(record.model_dump_json())
        assert set(data.keys()) == {"timestamp", "tool", "action"}
        assert "prompt_id" not in data
        assert "nodes_used" not in data
        assert "warnings" not in data
        assert "extra" not in data

    def test_record_never_contains_token(self):
        record = AuditRecord(
            tool="generate_image",
            action="submitted",
            extra={"token": "secret", "prompt": "a cat"},
        )
        serialized = record.model_dump_json()
        assert "secret" not in serialized


class TestAuditLogger:
    def test_log_writes_json_line(self, tmp_path):
        log_file = tmp_path / "audit.log"
        logger = AuditLogger(audit_file=log_file)
        logger.log(tool="get_queue", action="called")

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["tool"] == "get_queue"

    def test_log_multiple_entries(self, tmp_path):
        log_file = tmp_path / "audit.log"
        logger = AuditLogger(audit_file=log_file)
        logger.log(tool="tool_a", action="called")
        logger.log(tool="tool_b", action="called")

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_log_creates_parent_directories(self, tmp_path):
        log_file = tmp_path / "nested" / "dir" / "audit.log"
        logger = AuditLogger(audit_file=log_file)
        logger.log(tool="test", action="called")
        assert log_file.exists()

    def test_log_strips_sensitive_keys_from_extra(self, tmp_path):
        log_file = tmp_path / "audit.log"
        logger = AuditLogger(audit_file=log_file)
        logger.log(
            tool="run_workflow",
            action="submitted",
            extra={"token": "secret-value", "prompt": "a cat"},
        )
        content = log_file.read_text()
        assert "secret-value" not in content
        assert "a cat" in content


class TestAuditLoggerSymlinkProtection:
    def test_rejects_symlink_audit_file(self, tmp_path):
        """Audit logger should refuse to write to a symlink target."""
        real_file = tmp_path / "real.log"
        real_file.touch()
        symlink = tmp_path / "audit.log"
        symlink.symlink_to(real_file)

        logger = AuditLogger(audit_file=symlink)
        record = logger.log(tool="test", action="called")
        assert record.tool == "test"
        # Symlink target should NOT have audit content
        assert real_file.read_text() == ""

    def test_rejects_symlink_in_parent_directory(self, tmp_path):
        """Audit logger should refuse if parent path contains a symlink."""
        real_dir = tmp_path / "real_dir"
        real_dir.mkdir()
        symlink_dir = tmp_path / "link_dir"
        symlink_dir.symlink_to(real_dir)
        audit_file = symlink_dir / "audit.log"

        logger = AuditLogger(audit_file=audit_file)
        record = logger.log(tool="test", action="called")
        assert record.tool == "test"
        assert not audit_file.exists()


class TestAuditLoggerAsync:
    async def test_async_log_writes_record(self, tmp_path):
        log_file = tmp_path / "audit.log"
        logger = AuditLogger(audit_file=log_file)
        record = await logger.async_log(tool="test_tool", action="called")
        assert record.tool == "test_tool"
        content = log_file.read_text()
        assert "test_tool" in content

    async def test_async_log_concurrent_writes(self, tmp_path):
        """Multiple concurrent async_log calls should not corrupt the file."""
        log_file = tmp_path / "audit.log"
        logger = AuditLogger(audit_file=log_file)
        tasks = [logger.async_log(tool=f"tool_{i}", action="called") for i in range(10)]
        await asyncio.gather(*tasks)
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 10
