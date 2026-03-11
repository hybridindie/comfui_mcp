import pytest

from comfyui_mcp.security.download_validator import DownloadValidationError, DownloadValidator


@pytest.fixture
def validator():
    return DownloadValidator(
        allowed_domains=["huggingface.co", "civitai.com"],
        allowed_extensions=[".safetensors", ".ckpt", ".pt", ".pth", ".bin"],
    )


class TestDomainValidation:
    def test_huggingface_resolve_url(self, validator):
        url = "https://huggingface.co/stabilityai/sdxl/resolve/main/model.safetensors"
        validator.validate_url(url)  # Should not raise

    def test_civitai_download_url(self, validator):
        url = "https://civitai.com/api/download/models/12345"
        validator.validate_url(url)  # Should not raise

    def test_blocked_domain(self, validator):
        url = "https://evil.com/model.safetensors"
        with pytest.raises(DownloadValidationError, match="not in allowed domains"):
            validator.validate_url(url)

    def test_no_scheme(self, validator):
        with pytest.raises(DownloadValidationError, match="must use https"):
            validator.validate_url("ftp://huggingface.co/model.safetensors")

    def test_http_rejected(self, validator):
        with pytest.raises(DownloadValidationError, match="must use https"):
            validator.validate_url("http://huggingface.co/model.safetensors")

    def test_custom_domain(self):
        v = DownloadValidator(
            allowed_domains=["models.example.com"],
            allowed_extensions=[".safetensors"],
        )
        v.validate_url("https://models.example.com/my-model.safetensors")


class TestExtensionValidation:
    def test_safetensors(self, validator):
        validator.validate_extension("model.safetensors")

    def test_ckpt(self, validator):
        validator.validate_extension("model.ckpt")

    def test_invalid_extension(self, validator):
        with pytest.raises(DownloadValidationError, match="extension"):
            validator.validate_extension("model.exe")

    def test_no_extension(self, validator):
        with pytest.raises(DownloadValidationError, match="extension"):
            validator.validate_extension("model")


class TestUrlPathValidation:
    def test_hf_resolve_path(self, validator):
        url = "https://huggingface.co/org/repo/resolve/main/model.safetensors"
        validator.validate_url(url)

    def test_civitai_api_path(self, validator):
        url = "https://civitai.com/api/download/models/12345"
        validator.validate_url(url)

    def test_hf_non_resolve_path_rejected(self, validator):
        url = "https://huggingface.co/some/random/path"
        with pytest.raises(DownloadValidationError, match="URL path"):
            validator.validate_url(url)

    def test_civitai_non_api_path_rejected(self, validator):
        url = "https://civitai.com/models/12345"
        with pytest.raises(DownloadValidationError, match="URL path"):
            validator.validate_url(url)

    def test_custom_domain_no_path_validation(self):
        """Custom domains beyond HF/CivitAI don't have path pattern checks."""
        v = DownloadValidator(
            allowed_domains=["models.example.com"],
            allowed_extensions=[".safetensors"],
        )
        v.validate_url("https://models.example.com/any/path/model.safetensors")
