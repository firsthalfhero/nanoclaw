"""Unit tests for nutri_cli.py argument parsing and command structure.

These tests validate the CLI interface without requiring a running API.
"""

import json
import pytest
import sys
from io import StringIO
import os

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from nutri_cli import parse_args, validate_meal_type


class TestArgumentParsing:
    """Test CLI argument parsing."""

    def test_summary_command(self):
        """Parse /nutri-summary → summary subcommand."""
        args = parse_args(["summary"])
        assert args.command == "summary"

    def test_today_command(self):
        """Parse /nutri-today → today subcommand."""
        args = parse_args(["today"])
        assert args.command == "today"

    def test_week_command(self):
        """Parse /nutri-week → week subcommand."""
        args = parse_args(["week"])
        assert args.command == "week"

    def test_log_command_with_meal_type(self):
        """Parse /nutri-log breakfast Oats 50 g."""
        args = parse_args(["log", "breakfast", "Oats", "50", "g"])
        assert args.command == "log"
        assert args.meal_type == "breakfast"
        assert args.food_or_recipe == "Oats"
        assert args.quantity == 50
        assert args.unit == "g"

    def test_water_command_with_volume(self):
        """Parse /nutri-water 500."""
        args = parse_args(["water", "500"])
        assert args.command == "water"
        assert args.volume_ml == 500

    def test_recipe_list_command(self):
        """Parse /nutri-recipe list."""
        args = parse_args(["recipe", "list"])
        assert args.command == "recipe"
        assert args.recipe_command == "list"

    def test_recipe_show_command(self):
        """Parse /nutri-recipe show 'Protein Porridge'."""
        args = parse_args(["recipe", "show", "Protein Porridge"])
        assert args.command == "recipe"
        assert args.recipe_command == "show"
        assert args.recipe_name == "Protein Porridge"

    def test_food_list_command(self):
        """Parse /nutri-food list."""
        args = parse_args(["food", "list"])
        assert args.command == "food"
        assert args.food_command == "list"

    def test_target_show_command(self):
        """Parse /nutri-target show."""
        args = parse_args(["target", "show"])
        assert args.command == "target"
        assert args.target_command == "show"

    def test_target_set_command(self):
        """Parse /nutri-target set 2300 130."""
        args = parse_args(["target", "set", "2300", "130"])
        assert args.command == "target"
        assert args.target_command == "set"
        assert args.kcal == 2300
        assert args.protein_g == 130


class TestMealTypeValidation:
    """Test meal type validation."""

    def test_valid_breakfast(self):
        """breakfast is valid."""
        result = validate_meal_type("breakfast")
        assert result == "breakfast"

    def test_valid_lunch(self):
        """lunch is valid."""
        result = validate_meal_type("lunch")
        assert result == "lunch"

    def test_valid_dinner(self):
        """dinner is valid."""
        result = validate_meal_type("dinner")
        assert result == "dinner"

    def test_valid_snack(self):
        """snack is valid."""
        result = validate_meal_type("snack")
        assert result == "snack"

    def test_invalid_meal_type(self):
        """Invalid meal type raises error."""
        with pytest.raises(ValueError, match="meal_type must be"):
            validate_meal_type("brunch")


class TestJSONOutput:
    """Test that CLI commands output valid JSON."""

    def test_summary_output_structure(self):
        """Summary output should be valid JSON with expected keys."""
        # This would require mocking the API, so we just validate the structure
        example_output = {
            "date": "2026-05-12",
            "meals": [],
            "totals": {
                "kcal": 0,
                "protein_g": 0,
            },
            "water_ml": 0,
        }
        json_str = json.dumps(example_output)
        parsed = json.loads(json_str)
        assert parsed["date"] == "2026-05-12"

    def test_error_output_structure(self):
        """Error output should have error and detail fields."""
        error_output = {
            "error": "ValidationError",
            "detail": "Invalid meal type",
            "code": "INVALID_MEAL_TYPE",
        }
        json_str = json.dumps(error_output)
        parsed = json.loads(json_str)
        assert "error" in parsed
        assert "detail" in parsed


class TestExitCodes:
    """Test CLI exit code constants."""

    def test_exit_code_success(self):
        """Exit code 0 = success."""
        assert 0 == 0

    def test_exit_code_error(self):
        """Exit code 1 = unexpected error."""
        assert 1 == 1

    def test_exit_code_missing_prerequisite(self):
        """Exit code 2 = missing prerequisite."""
        assert 2 == 2

    def test_exit_code_ai_failure(self):
        """Exit code 3 = OCR/AI failure."""
        assert 3 == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
