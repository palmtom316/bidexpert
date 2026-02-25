"""Tests for app.services.path_safety — path identifier validation."""
from __future__ import annotations

import pytest

from app.services.path_safety import validate_path_identifier


class TestValidatePathIdentifier:
    def test_valid_simple(self):
        assert validate_path_identifier("id", "abc123") == "abc123"

    def test_valid_with_dots_dashes_underscores(self):
        assert validate_path_identifier("id", "my-file_v2.0") == "my-file_v2.0"

    def test_strips_whitespace(self):
        assert validate_path_identifier("id", "  hello  ") == "hello"

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="invalid"):
            validate_path_identifier("id", "")

    def test_rejects_none_coerced(self):
        with pytest.raises(ValueError, match="invalid"):
            validate_path_identifier("id", "")

    def test_rejects_whitespace_only(self):
        with pytest.raises(ValueError, match="invalid"):
            validate_path_identifier("id", "   ")

    def test_rejects_path_traversal(self):
        with pytest.raises(ValueError, match="invalid"):
            validate_path_identifier("id", "../etc/passwd")

    def test_rejects_slash(self):
        with pytest.raises(ValueError, match="invalid"):
            validate_path_identifier("id", "foo/bar")

    def test_rejects_starting_with_dot(self):
        with pytest.raises(ValueError, match="invalid"):
            validate_path_identifier("id", ".hidden")

    def test_rejects_starting_with_dash(self):
        with pytest.raises(ValueError, match="invalid"):
            validate_path_identifier("id", "-flag")

    def test_rejects_too_long(self):
        with pytest.raises(ValueError, match="invalid"):
            validate_path_identifier("id", "a" * 129)

    def test_max_length_accepted(self):
        token = "a" * 128
        assert validate_path_identifier("id", token) == token

    def test_rejects_special_chars(self):
        for char in ["@", "#", "$", "%", "^", "&", "*", "(", ")", " ", "!", "~"]:
            with pytest.raises(ValueError, match="invalid"):
                validate_path_identifier("id", f"foo{char}bar")

    def test_error_message_includes_name(self):
        with pytest.raises(ValueError, match="invalid project_id"):
            validate_path_identifier("project_id", "")
