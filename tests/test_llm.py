# tests/test_llm.py
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.llm import (
    CircuitBreaker,
    analyze_with_claude,
    parse_recommendations,
)


# --- parse_recommendations tests ---


class TestParseRecommendations:
    """Tests for JSON parsing of LLM responses."""

    def test_valid_json(self):
        """Valid JSON with recommendations parses correctly."""
        response = json.dumps({
            "recommendations": [
                {
                    "type": "add_index",
                    "description": "Add index on email column",
                    "sql": "CREATE INDEX idx_email ON users(email);",
                    "predicted_improvement": "60%",
                }
            ]
        })
        result = parse_recommendations(response)
        assert len(result) == 1
        assert result[0]["type"] == "add_index"
        assert result[0]["predicted_improvement"] == "60%"

    def test_markdown_fenced_json(self):
        """JSON wrapped in markdown code fences still parses."""
        response = '```json\n{"recommendations": [{"type": "rewrite", "description": "Use specific columns", "predicted_improvement": "25%"}]}\n```'
        result = parse_recommendations(response)
        assert len(result) == 1
        assert result[0]["type"] == "rewrite"

    def test_numeric_improvement_coerced_to_string(self):
        """Numeric predicted_improvement is coerced to string with % suffix."""
        response = json.dumps({
            "recommendations": [
                {
                    "type": "add_index",
                    "description": "Add index",
                    "predicted_improvement": 60,
                }
            ]
        })
        result = parse_recommendations(response)
        assert result[0]["predicted_improvement"] == "60%"

    def test_missing_sql_defaults_to_none(self):
        """Missing sql field defaults to None."""
        response = json.dumps({
            "recommendations": [
                {
                    "type": "analysis",
                    "description": "Review plan",
                    "predicted_improvement": "30%",
                }
            ]
        })
        result = parse_recommendations(response)
        assert result[0]["sql"] is None

    def test_no_json_raises_value_error(self):
        """Response with no JSON raises ValueError."""
        with pytest.raises(ValueError, match="No JSON object found"):
            parse_recommendations("This is just plain text with no JSON.")

    def test_invalid_json_raises_value_error(self):
        """Malformed JSON raises ValueError."""
        with pytest.raises(ValueError, match="Failed to parse JSON"):
            parse_recommendations("{recommendations: invalid}")

    def test_missing_required_fields_raises_value_error(self):
        """Recommendation missing type or description raises ValueError."""
        response = json.dumps({
            "recommendations": [{"sql": "SELECT 1"}]
        })
        with pytest.raises(ValueError, match="must have 'type' and 'description'"):
            parse_recommendations(response)


# --- CircuitBreaker tests ---


class TestCircuitBreaker:
    """Tests for the circuit breaker state machine."""

    def test_starts_closed(self):
        """New circuit breaker starts in CLOSED state."""
        cb = CircuitBreaker(failure_threshold=3, reset_timeout=10)
        assert cb.state == "CLOSED"
        assert cb.allow_request() is True

    def test_opens_after_threshold(self):
        """Circuit opens after reaching the failure threshold."""
        cb = CircuitBreaker(failure_threshold=3, reset_timeout=10)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == "OPEN"
        assert cb.allow_request() is False

    def test_half_open_after_timeout(self):
        """Circuit transitions to HALF_OPEN after the reset timeout."""
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=0)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "OPEN"

        # With reset_timeout=0, it should immediately allow a test request
        assert cb.allow_request() is True
        assert cb.state == "HALF_OPEN"

    def test_success_resets_to_closed(self):
        """A successful call resets the breaker to CLOSED."""
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=0)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "OPEN"

        # Allow test request (HALF_OPEN)
        cb.allow_request()
        cb.record_success()
        assert cb.state == "CLOSED"
        assert cb.failure_count == 0

    def test_stays_closed_below_threshold(self):
        """Failures below the threshold keep the breaker CLOSED."""
        cb = CircuitBreaker(failure_threshold=5, reset_timeout=10)
        for _ in range(4):
            cb.record_failure()
        assert cb.state == "CLOSED"
        assert cb.allow_request() is True


# --- analyze_with_claude dispatcher tests ---


class TestAnalyzeWithClaude:
    """Tests for the mock/real dispatcher."""

    @pytest.mark.asyncio
    async def test_uses_mock_when_no_credentials(self):
        """Falls back to mock when AWS_ACCESS_KEY_ID is not set."""
        with patch.dict("os.environ", {"AWS_ACCESS_KEY_ID": ""}, clear=False):
            with patch(
                "src.services.llm.mock_analyze_with_claude",
                new_callable=AsyncMock,
                return_value=[{"type": "test", "description": "mock"}],
            ) as mock_fn:
                result = await analyze_with_claude("SELECT * FROM users")
                mock_fn.assert_called_once()
                assert result[0]["type"] == "test"

    @pytest.mark.asyncio
    async def test_uses_real_when_credentials_set(self):
        """Routes to real analyzer when AWS credentials are present."""
        with patch.dict(
            "os.environ",
            {"AWS_ACCESS_KEY_ID": "AKIATEST123"},
            clear=False,
        ):
            with patch(
                "src.services.llm.real_analyze_with_claude",
                new_callable=AsyncMock,
                return_value=[{"type": "add_index", "description": "real"}],
            ) as real_fn:
                result = await analyze_with_claude("SELECT * FROM users")
                real_fn.assert_called_once()
                assert result[0]["description"] == "real"
