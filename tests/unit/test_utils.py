import pytest
from datetime import datetime
from io import BytesIO

from app.util.redis_utils import (
    encode_file_to_base64,
    decode_base64_to_bytesio,
    normalize_filename,
    is_file_allowed_for_assistant_file_search,
    prepare_files_for_vector_store,
)
from app.util.publication_utils.contract import (
    validate_contract_query_params,
    format_validation_errors,
)


class TestRedisUtils:
    def test_encode_decode_file(self):
        """Test file encoding and decoding."""
        # Create test file
        content = b"Test file content"
        file_obj = BytesIO(content)

        # Encode
        encoded = encode_file_to_base64(file_obj)
        assert isinstance(encoded, str)

        # Decode
        decoded = decode_base64_to_bytesio(encoded, "test.txt")
        assert decoded.read() == content
        assert decoded.name == "test.txt"

    def test_normalize_filename(self):
        """Test filename normalization."""
        file_obj = BytesIO(b"content")

        normalized = normalize_filename(file_obj, "Test.PDF")
        assert normalized.name == "Test.pdf"  # Extension lowercase

    def test_is_file_allowed(self):
        """Test file type validation."""
        assert is_file_allowed_for_assistant_file_search("document.pdf") is True
        assert is_file_allowed_for_assistant_file_search("image.jpg") is False
        assert is_file_allowed_for_assistant_file_search("code.py") is True
        assert is_file_allowed_for_assistant_file_search("video.mp4") is False

    def test_prepare_files_for_vector_store(self):
        """Test preparing files for vector store."""
        files = {
            "doc1.pdf": BytesIO(b"PDF content"),
            "doc2.txt": BytesIO(b"Text content"),
            "image.jpg": BytesIO(b"Image content"),  # Should be filtered
        }

        prepared = prepare_files_for_vector_store(files)

        assert len(prepared) == 2  # Only PDF and TXT
        assert all(hasattr(f, "name") for f in prepared)


class TestContractUtils:
    def test_validate_contract_query_params(self):
        """Test contract query parameter validation."""
        # Valid params
        errors = validate_contract_query_params(
            year=2024, quarter=2, month=6, page=1, size=50
        )
        assert len(errors) == 0

        # Invalid params
        errors = validate_contract_query_params(
            year=1800,  # Too old
            quarter=5,  # Invalid quarter
            month=13,  # Invalid month
            page=0,  # Invalid page
            size=1000,  # Too large
        )
        assert len(errors) == 5
        assert "year" in errors
        assert "quarter" in errors

    def test_format_validation_errors(self):
        """Test error formatting."""
        errors = {"year": "Invalid year", "month": "Invalid month"}

        formatted = format_validation_errors(errors)
        assert "year: Invalid year" in formatted
        assert "month: Invalid month" in formatted
