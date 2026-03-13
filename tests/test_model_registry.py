"""Tests for the canonical model loader registry."""

from comfyui_mcp.model_registry import MODEL_LOADER_FIELDS, get_single_field_loaders


class TestModelLoaderFields:
    def test_has_all_known_loaders(self):
        """Registry should include all 18 known model loader types."""
        expected = {
            "CheckpointLoaderSimple",
            "CheckpointLoader",
            "unCLIPCheckpointLoader",
            "LoraLoader",
            "LoraLoaderModelOnly",
            "VAELoader",
            "ControlNetLoader",
            "UpscaleModelLoader",
            "CLIPLoader",
            "CLIPVisionLoader",
            "StyleModelLoader",
            "GLIGENLoader",
            "DiffusersLoader",
            "UNETLoader",
            "DualCLIPLoader",
            "TripleCLIPLoader",
            "PhotoMakerLoader",
            "IPAdapterModelLoader",
        }
        assert set(MODEL_LOADER_FIELDS.keys()) == expected

    def test_each_entry_has_field_folder_pairs(self):
        """Every entry must be a non-empty list of (field_name, folder) tuples."""
        for class_type, fields in MODEL_LOADER_FIELDS.items():
            assert len(fields) > 0, f"{class_type} has no fields"
            for field_name, folder in fields:
                assert isinstance(field_name, str) and field_name
                assert isinstance(folder, str) and folder

    def test_multi_field_loaders(self):
        """DualCLIPLoader should have 2 fields, TripleCLIPLoader 3."""
        assert len(MODEL_LOADER_FIELDS["DualCLIPLoader"]) == 2
        assert len(MODEL_LOADER_FIELDS["TripleCLIPLoader"]) == 3


class TestGetSingleFieldLoaders:
    def test_returns_only_single_field_entries(self):
        """Multi-field loaders (DualCLIP, TripleCLIP) should be excluded."""
        result = get_single_field_loaders()
        assert "DualCLIPLoader" not in result
        assert "TripleCLIPLoader" not in result

    def test_maps_to_field_and_folder(self):
        """Each value should be a (field_name, folder) tuple."""
        result = get_single_field_loaders()
        field, folder = result["CheckpointLoaderSimple"]
        assert field == "ckpt_name"
        assert folder == "checkpoints"

    def test_includes_all_single_field_loaders(self):
        """Should include all loaders that have exactly one field."""
        result = get_single_field_loaders()
        assert "LoraLoader" in result
        assert "VAELoader" in result
        assert "UNETLoader" in result
