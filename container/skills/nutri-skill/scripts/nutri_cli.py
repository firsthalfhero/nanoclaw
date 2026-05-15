#!/usr/bin/env python3
"""
Nutrition Tracker CLI

Main interface for logging meals, managing recipes/foods, and viewing reports.
All output is JSON to stdout; errors go to stderr.
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional

import httpx
import pytz

# Configuration
NUTRI_API_URL = os.getenv("NUTRI_API_URL", "http://localhost:8000")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_VISION_MODEL = os.getenv("OPENROUTER_VISION_MODEL", "google/gemini-3.1-flash-lite")
OPENROUTER_TEXT_MODEL = os.getenv("OPENROUTER_TEXT_MODEL", "google/gemini-3.1-flash-lite")
TZ = pytz.timezone("Australia/Sydney")

# Exit codes
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_MISSING_PREREQ = 2
EXIT_AI_FAILURE = 3


def get_today_sydney() -> date:
    """Get today's date in Sydney timezone."""
    return datetime.now(TZ).date()


def api_call(method: str, path: str, json_data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Make an API call to the nutrition backend.

    Args:
        method: HTTP method (GET, POST, PATCH, DELETE)
        path: API path (e.g., "/foods", "/meals/42")
        json_data: Request body (for POST/PATCH)
        params: Query parameters

    Returns:
        Response JSON as dict

    Raises:
        httpx.HTTPError on connection failure
        json.JSONDecodeError on invalid response
    """
    url = f"{NUTRI_API_URL}{path}"
    timeout = httpx.Timeout(60.0 if json_data or "estimate" in path else 10.0)

    with httpx.Client(timeout=timeout) as client:
        response = client.request(method, url, json=json_data, params=params)
        response.raise_for_status()
        return response.json() if response.content else {}


def output_json(data: Dict[str, Any], exit_code: int = EXIT_SUCCESS):
    """Output JSON to stdout and exit."""
    print(json.dumps(data, default=str))
    sys.exit(exit_code)


def error_json(message: str, code: int = "ERROR", exit_code: int = EXIT_ERROR):
    """Output error JSON to stderr and exit."""
    error_data = {"error": message, "code": code}
    print(json.dumps(error_data), file=sys.stderr)
    sys.exit(exit_code)


# ============================================================================
# Subcommand Handlers
# ============================================================================

def cmd_help(args) -> None:
    """Show help information for all commands."""
    help_text = {
        "status": "ok",
        "commands": [
            {"category": "Reports", "items": [
                {"command": "nutri_summary", "description": "Today's totals (kcal, macros, water)"},
                {"command": "nutri_today", "description": "Detailed breakdown of today's meals"},
                {"command": "nutri_week", "description": "Last 7 days daily totals"},
            ]},
            {"category": "Logging", "items": [
                {"command": "nutri_log", "description": "Log a meal", "usage": "<meal_type> <food> [qty] [unit]"},
                {"command": "nutri_photo", "description": "OCR a nutrition label photo", "usage": "<meal_type>"},
                {"command": "nutri_water", "description": "Log water intake", "usage": "<volume_ml>"},
            ]},
            {"category": "Lookup", "items": [
                {"command": "nutri_check_meal", "description": "View a specific meal", "usage": "<meal_id>"},
            ]},
            {"category": "Management", "items": [
                {"command": "nutri_edit", "description": "Edit meal macros", "usage": "<meal_id> <field> <value>"},
                {"command": "nutri_delete", "description": "Delete a meal", "usage": "<meal_id>"},
                {"command": "nutri_recipe", "description": "Manage recipes", "usage": "[list|show|save|delete]"},
                {"command": "nutri_food", "description": "Manage foods", "usage": "[list|show|add-manual|delete]"},
                {"command": "nutri_target", "description": "View or set daily targets", "usage": "[show|set]"},
            ]},
            {"category": "Help", "items": [
                {"command": "nutri_help", "description": "Show this help message"},
            ]},
        ]
    }
    output_json(help_text)

def cmd_log(args) -> None:
    """Log a meal (recipe, food, or free-text estimate)."""
    try:
        # Determine source and collect data
        if args.recipe:
            # Log from recipe
            foods = api_call("GET", "/foods", params={"search": args.recipe})
            if not foods:
                error_json(f"Recipe not found: {args.recipe}", "RECIPE_NOT_FOUND", EXIT_MISSING_PREREQ)

            recipe = api_call("GET", f"/recipes/{foods[0]['id']}")
            payload = {
                "meal_category": args.meal,
                "source": "recipe",
                "recipe_id": recipe["id"],
                "servings": float(args.servings or 1),
            }

        elif args.food:
            # Log from food
            foods = api_call("GET", "/foods", params={"search": args.food})
            if not foods:
                error_json(f"Food not found: {args.food}", "FOOD_NOT_FOUND", EXIT_MISSING_PREREQ)

            food = foods[0]
            payload = {
                "meal_category": args.meal,
                "source": "food",
                "food_id": food["id"],
                "quantity": float(args.quantity or 1),
                "unit": args.unit or "serving",
            }

        elif args.estimate:
            # AI estimation (calls OpenRouter)
            from openrouter import call_text_estimation
            try:
                estimate = call_text_estimation(args.estimate, OPENROUTER_TEXT_MODEL)
            except Exception as e:
                error_json(f"AI estimation failed: {e}", "AI_FAILURE", EXIT_AI_FAILURE)

            payload = {
                "meal_category": args.meal,
                "source": "ai_estimate",
                "free_text_description": args.estimate,
                **estimate,
            }
        else:
            error_json("Must provide --recipe, --food, or --estimate", "MISSING_SOURCE")

        # Create meal log
        meal = api_call("POST", "/meals", payload)
        output_json(meal)

    except Exception as e:
        error_json(str(e), "LOG_ERROR")


def cmd_water(args) -> None:
    """Log water intake."""
    try:
        water = api_call("POST", "/water", {"volume_ml": args.ml})
        output_json(water)
    except Exception as e:
        error_json(str(e), "WATER_ERROR")


def cmd_today(args) -> None:
    """Show today's meals and water."""
    try:
        report = api_call("GET", "/reports/today")
        output_json(report)
    except Exception as e:
        error_json(str(e), "TODAY_ERROR")


def cmd_summary(args) -> None:
    """Show today's summary vs target."""
    try:
        query_date = args.date or get_today_sydney().isoformat()
        report = api_call("GET", "/reports/summary", params={"date": query_date})
        output_json(report)
    except Exception as e:
        error_json(str(e), "SUMMARY_ERROR")


def cmd_week(args) -> None:
    """Show rolling 7-day summary."""
    try:
        report = api_call("GET", "/reports/week")
        output_json(report)
    except Exception as e:
        error_json(str(e), "WEEK_ERROR")


def cmd_recipe_list(args) -> None:
    """List recipes."""
    try:
        recipes = api_call("GET", "/recipes")
        output_json({"recipes": recipes})
    except Exception as e:
        error_json(str(e), "RECIPE_LIST_ERROR")


def cmd_recipe_show(args) -> None:
    """Show recipe details."""
    try:
        recipes = api_call("GET", "/recipes", params={"search": args.name})
        if not recipes:
            error_json(f"Recipe not found: {args.name}", "RECIPE_NOT_FOUND")
        output_json(recipes[0])
    except Exception as e:
        error_json(str(e), "RECIPE_SHOW_ERROR")


def cmd_recipe_save(args) -> None:
    """Save a new recipe."""
    try:
        # Parse ingredients
        ingredients = []
        if args.ingredients:
            for ingredient_str in args.ingredients.split(","):
                parts = ingredient_str.strip().split(":")
                if len(parts) != 2:
                    error_json(f"Invalid ingredient format: {ingredient_str}", "INVALID_FORMAT")
                food_name, qty_unit = parts
                # Parse quantity and unit
                qty_parts = qty_unit.rsplit(maxsplit=1)
                if len(qty_parts) != 2:
                    error_json(f"Invalid quantity format: {qty_unit}", "INVALID_FORMAT")
                quantity, unit = qty_parts

                # Resolve food by name
                foods = api_call("GET", "/foods", params={"search": food_name})
                if not foods:
                    error_json(f"Food not found: {food_name}", "FOOD_NOT_FOUND", EXIT_MISSING_PREREQ)

                ingredients.append({
                    "food_id": foods[0]["id"],
                    "quantity": float(quantity),
                    "unit": unit,
                })

        payload = {
            "name": args.name,
            "ingredients": ingredients,
        }
        if args.meal:
            payload["default_meal_category"] = args.meal

        recipe = api_call("POST", "/recipes", payload)
        output_json(recipe)

    except Exception as e:
        error_json(str(e), "RECIPE_SAVE_ERROR")


def cmd_recipe_delete(args) -> None:
    """Delete a recipe."""
    try:
        # Try parsing as ID first
        try:
            recipe_id = int(args.name_or_id)
        except ValueError:
            # Search by name
            recipes = api_call("GET", "/recipes", params={"search": args.name_or_id})
            if not recipes:
                error_json(f"Recipe not found: {args.name_or_id}", "RECIPE_NOT_FOUND")
            recipe_id = recipes[0]["id"]

        api_call("DELETE", f"/recipes/{recipe_id}")
        output_json({"status": "deleted", "recipe_id": recipe_id})

    except Exception as e:
        error_json(str(e), "RECIPE_DELETE_ERROR")


def cmd_food_list(args) -> None:
    """List foods with optional search."""
    try:
        params = {}
        if args.search:
            params["search"] = args.search
        foods = api_call("GET", "/foods", params=params)
        output_json({"foods": foods})
    except Exception as e:
        error_json(str(e), "FOOD_LIST_ERROR")


def cmd_food_show(args) -> None:
    """Show food details."""
    try:
        # Try parsing as ID first
        try:
            food_id = int(args.name_or_id)
            food = api_call("GET", f"/foods/{food_id}")
        except ValueError:
            # Search by name
            foods = api_call("GET", "/foods", params={"search": args.name_or_id})
            if not foods:
                error_json(f"Food not found: {args.name_or_id}", "FOOD_NOT_FOUND")
            food = foods[0]

        output_json(food)

    except Exception as e:
        error_json(str(e), "FOOD_SHOW_ERROR")


def cmd_food_add_manual(args) -> None:
    """Add food manually."""
    try:
        payload = {
            "name": args.name,
            "source": "manual",
            "serving_type": args.serving_type,
            "kcal": float(args.kcal),
            "protein_g": float(args.protein),
            "fat_g": float(args.fat),
            "carbs_g": float(args.carbs),
        }

        if args.serving_type == "per_serving":
            if not args.serving_size or not args.serving_unit:
                error_json("per_serving foods require --serving-size and --serving-unit", "MISSING_SERVING_INFO")
            payload["serving_size"] = float(args.serving_size)
            payload["serving_unit"] = args.serving_unit

        if args.saturated_fat:
            payload["saturated_fat_g"] = float(args.saturated_fat)
        if args.sugar:
            payload["sugar_g"] = float(args.sugar)
        if args.sodium_mg:
            payload["sodium_mg"] = float(args.sodium_mg)
        if args.fibre:
            payload["fibre_g"] = float(args.fibre)

        payload["entry_type"] = args.entry_type or "food"

        food = api_call("POST", "/foods", payload)
        output_json(food)

    except Exception as e:
        error_json(str(e), "FOOD_ADD_ERROR")


def cmd_food_delete(args) -> None:
    """Delete a food."""
    try:
        # Try parsing as ID first
        try:
            food_id = int(args.name_or_id)
        except ValueError:
            # Search by name
            foods = api_call("GET", "/foods", params={"search": args.name_or_id})
            if not foods:
                error_json(f"Food not found: {args.name_or_id}", "FOOD_NOT_FOUND")
            food_id = foods[0]["id"]

        api_call("DELETE", f"/foods/{food_id}")
        output_json({"status": "deleted", "food_id": food_id})

    except Exception as e:
        error_json(str(e), "FOOD_DELETE_ERROR")


def cmd_target_show(args) -> None:
    """Show active daily target."""
    try:
        target = api_call("GET", "/targets/active")
        output_json(target)
    except Exception as e:
        error_json(str(e), "TARGET_SHOW_ERROR")


def cmd_target_set(args) -> None:
    """Set daily calorie target."""
    try:
        payload = {"kcal_target": float(args.kcal)}
        if args.protein:
            payload["protein_g_target"] = float(args.protein)
        if args.fat:
            payload["fat_g_target"] = float(args.fat)
        if args.carbs:
            payload["carbs_g_target"] = float(args.carbs)

        target = api_call("POST", "/targets", payload)
        output_json(target)

    except Exception as e:
        error_json(str(e), "TARGET_SET_ERROR")


def cmd_edit(args) -> None:
    """Edit a meal log entry."""
    try:
        payload = {}
        if args.servings:
            payload["servings"] = float(args.servings)
        if args.meal:
            payload["meal_category"] = args.meal
        if args.kcal:
            payload["kcal"] = float(args.kcal)
        if args.protein:
            payload["protein_g"] = float(args.protein)
        if args.fat:
            payload["fat_g"] = float(args.fat)
        if args.carbs:
            payload["carbs_g"] = float(args.carbs)
        if args.notes:
            payload["notes"] = args.notes

        meal = api_call("PATCH", f"/meals/{args.log_id}", payload)
        output_json(meal)

    except Exception as e:
        error_json(str(e), "EDIT_ERROR")


def cmd_delete(args) -> None:
    """Delete a meal log entry."""
    try:
        api_call("DELETE", f"/meals/{args.log_id}")
        output_json({"status": "deleted", "log_id": args.log_id})
    except Exception as e:
        error_json(str(e), "DELETE_ERROR")


def cmd_check_meal(args) -> None:
    """Check if a meal is logged today (used by cron)."""
    try:
        today = get_today_sydney().isoformat()
        status = api_call("GET", "/reports/meal-status", params={
            "meal_category": args.meal,
            "date": today,
        })

        if status["logged"]:
            output_json({"status": "logged", "kcal_subtotal": status["kcal_subtotal"], "entry_count": status["entry_count"]})
        else:
            output_json({"status": "missing", "meal": args.meal})

    except Exception as e:
        error_json(str(e), "CHECK_MEAL_ERROR")


# ============================================================================
# Main CLI
# ============================================================================

def main():
    """Parse arguments and dispatch to handlers."""
    parser = argparse.ArgumentParser(
        description="Nutrition Tracker CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # log command
    log_parser = subparsers.add_parser("log", help="Log a meal")
    log_parser.add_argument("--meal", required=True, choices=["breakfast", "lunch", "dinner", "snack"])
    log_group = log_parser.add_mutually_exclusive_group(required=True)
    log_group.add_argument("--recipe", help="Recipe name")
    log_group.add_argument("--food", help="Food name")
    log_group.add_argument("--estimate", help="Free-text meal description")
    log_parser.add_argument("--servings", help="Number of servings")
    log_parser.add_argument("--quantity", help="Food quantity")
    log_parser.add_argument("--unit", help="Food unit")
    log_parser.set_defaults(func=cmd_log)

    # water command
    water_parser = subparsers.add_parser("water", help="Log water")
    water_parser.add_argument("--ml", type=int, required=True, help="Volume in ml")
    water_parser.set_defaults(func=cmd_water)

    # today command
    today_parser = subparsers.add_parser("today", help="Show today's meals")
    today_parser.set_defaults(func=cmd_today)

    # summary command
    summary_parser = subparsers.add_parser("summary", help="Show daily summary")
    summary_parser.add_argument("--date", help="Date (YYYY-MM-DD)")
    summary_parser.set_defaults(func=cmd_summary)

    # week command
    week_parser = subparsers.add_parser("week", help="Show 7-day summary")
    week_parser.set_defaults(func=cmd_week)

    # recipe commands
    recipe_parser = subparsers.add_parser("recipe", help="Manage recipes")
    recipe_subparsers = recipe_parser.add_subparsers(dest="recipe_cmd", required=True)

    recipe_list = recipe_subparsers.add_parser("list", help="List recipes")
    recipe_list.set_defaults(func=cmd_recipe_list)

    recipe_show = recipe_subparsers.add_parser("show", help="Show recipe")
    recipe_show.add_argument("name", help="Recipe name")
    recipe_show.set_defaults(func=cmd_recipe_show)

    recipe_save = recipe_subparsers.add_parser("save", help="Save recipe")
    recipe_save.add_argument("name", help="Recipe name")
    recipe_save.add_argument("--ingredients", required=True, help="Ingredients (comma-separated: name:qty+unit)")
    recipe_save.add_argument("--meal", help="Default meal category")
    recipe_save.set_defaults(func=cmd_recipe_save)

    recipe_delete = recipe_subparsers.add_parser("delete", help="Delete recipe")
    recipe_delete.add_argument("name_or_id", help="Recipe name or ID")
    recipe_delete.set_defaults(func=cmd_recipe_delete)

    # food commands
    food_parser = subparsers.add_parser("food", help="Manage foods")
    food_subparsers = food_parser.add_subparsers(dest="food_cmd", required=True)

    food_list = food_subparsers.add_parser("list", help="List foods")
    food_list.add_argument("--search", help="Search term")
    food_list.set_defaults(func=cmd_food_list)

    food_show = food_subparsers.add_parser("show", help="Show food")
    food_show.add_argument("name_or_id", help="Food name or ID")
    food_show.set_defaults(func=cmd_food_show)

    food_add = food_subparsers.add_parser("add-manual", help="Add food manually")
    food_add.add_argument("--name", required=True)
    food_add.add_argument("--serving-type", required=True, choices=["per_100g", "per_100ml", "per_serving"])
    food_add.add_argument("--serving-size", help="For per_serving")
    food_add.add_argument("--serving-unit", help="For per_serving")
    food_add.add_argument("--kcal", required=True, type=float)
    food_add.add_argument("--protein", required=True, type=float)
    food_add.add_argument("--fat", required=True, type=float)
    food_add.add_argument("--carbs", required=True, type=float)
    food_add.add_argument("--saturated-fat", type=float)
    food_add.add_argument("--sugar", type=float)
    food_add.add_argument("--sodium-mg", type=float)
    food_add.add_argument("--fibre", type=float)
    food_add.add_argument("--entry-type", choices=["food", "drink"])
    food_add.set_defaults(func=cmd_food_add_manual)

    food_delete = food_subparsers.add_parser("delete", help="Delete food")
    food_delete.add_argument("name_or_id", help="Food name or ID")
    food_delete.set_defaults(func=cmd_food_delete)

    # target commands
    target_parser = subparsers.add_parser("target", help="Manage daily targets")
    target_subparsers = target_parser.add_subparsers(dest="target_cmd", required=True)

    target_show = target_subparsers.add_parser("show", help="Show target")
    target_show.set_defaults(func=cmd_target_show)

    target_set = target_subparsers.add_parser("set", help="Set target")
    target_set.add_argument("--kcal", required=True, type=float)
    target_set.add_argument("--protein", type=float)
    target_set.add_argument("--fat", type=float)
    target_set.add_argument("--carbs", type=float)
    target_set.set_defaults(func=cmd_target_set)

    # edit command
    edit_parser = subparsers.add_parser("edit", help="Edit meal log")
    edit_parser.add_argument("log_id", type=int)
    edit_parser.add_argument("--servings", type=float)
    edit_parser.add_argument("--meal", choices=["breakfast", "lunch", "dinner", "snack"])
    edit_parser.add_argument("--kcal", type=float)
    edit_parser.add_argument("--protein", type=float)
    edit_parser.add_argument("--fat", type=float)
    edit_parser.add_argument("--carbs", type=float)
    edit_parser.add_argument("--notes")
    edit_parser.set_defaults(func=cmd_edit)

    # delete command
    delete_parser = subparsers.add_parser("delete", help="Delete meal log")
    delete_parser.add_argument("log_id", type=int)
    delete_parser.set_defaults(func=cmd_delete)

    # check-meal command
    check_parser = subparsers.add_parser("check-meal", help="Check if meal is logged")
    check_parser.add_argument("--meal", required=True, choices=["breakfast", "lunch", "dinner", "snack"])
    check_parser.set_defaults(func=cmd_check_meal)

    # help command
    help_parser = subparsers.add_parser("help", help="Show help information")
    help_parser.set_defaults(func=cmd_help)

    # Parse and dispatch
    args = parser.parse_args()
    if hasattr(args, "func"):
        try:
            args.func(args)
        except Exception as e:
            error_json(str(e), "UNHANDLED_ERROR")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
