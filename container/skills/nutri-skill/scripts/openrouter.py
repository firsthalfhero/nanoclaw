"""OpenRouter API integration for vision OCR and text estimation."""
import base64
import json
from typing import Any, Dict

import httpx


class OpenRouterError(Exception):
    """Base exception for OpenRouter API errors."""
    pass


def call_vision(
    image_bytes: bytes,
    api_key: str,
    model: str = "google/gemini-3.1-flash-lite",
) -> Dict[str, Any]:
    """
    Call OpenRouter vision model to extract nutrition from label.

    Args:
        image_bytes: Image file bytes
        api_key: OpenRouter API key
        model: Model to use

    Returns:
        Nutrition data dict with kcal, protein_g, etc.

    Raises:
        OpenRouterError on API failure or invalid response
    """
    image_base64 = base64.standard_b64encode(image_bytes).decode()

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": """Extract nutrition information from this Australian food label.
Return ONLY valid JSON (no markdown, no prose) matching this schema:
{
  "product_name": "string",
  "brand": "string or null",
  "serving_type": "per_100g | per_100ml | per_serving",
  "serving_size": "number or null (only for per_serving)",
  "serving_unit": "string or null (e.g. 'scoop', 'slice')",
  "kcal": "number",
  "protein_g": "number",
  "fat_g": "number",
  "saturated_fat_g": "number or null",
  "carbs_g": "number",
  "sugar_g": "number or null",
  "sodium_mg": "number or null",
  "fibre_g": "number or null",
  "confidence": "high | medium | low",
  "kj_was_primary": "boolean (true if only kJ shown, convert using kJ/4.184)"
}

If kJ shown but kcal not shown, set kcal = kJ / 4.184 and kj_was_primary = true.
If uncertain, set confidence = 'low'.""",
                    },
                ],
            }
        ],
        "temperature": 0,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            data = response.json()

            # Extract JSON from response
            if "choices" not in data or not data["choices"]:
                raise OpenRouterError("No response from vision model")

            content = data["choices"][0].get("message", {}).get("content", "")
            if not content:
                raise OpenRouterError("Empty response from vision model")

            # Strip markdown fences if present
            content = content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

            nutrition = json.loads(content)
            return _validate_nutrition_schema(nutrition)

    except json.JSONDecodeError as e:
        raise OpenRouterError(f"Vision model returned invalid JSON: {e}")
    except httpx.HTTPError as e:
        raise OpenRouterError(f"OpenRouter API error: {e}")


def call_text_estimation(
    description: str,
    api_key: str,
    model: str = "google/gemini-3.1-flash-lite",
) -> Dict[str, Any]:
    """
    Call OpenRouter text model to estimate nutrition from description.

    Args:
        description: Free-text meal description
        api_key: OpenRouter API key
        model: Model to use

    Returns:
        Nutrition estimate dict

    Raises:
        OpenRouterError on API failure or invalid response
    """
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a nutrition expert. Estimate nutrition for Australian meals described in plain English.",
            },
            {
                "role": "user",
                "content": f"""Estimate nutrition for this Australian meal: "{description}"

Return ONLY valid JSON (no markdown, no prose) matching this schema:
{{
  "product_name": "string (meal name)",
  "serving_type": "per_serving",
  "kcal": "number",
  "protein_g": "number",
  "fat_g": "number",
  "saturated_fat_g": "number or null",
  "carbs_g": "number",
  "sugar_g": "number or null",
  "sodium_mg": "number or null",
  "fibre_g": "number or null",
  "confidence": "high | medium | low"
}}

Set confidence = 'low' if uncertain about the meal or ingredients.""",
            },
        ],
        "temperature": 0,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            data = response.json()

            if "choices" not in data or not data["choices"]:
                raise OpenRouterError("No response from text model")

            content = data["choices"][0].get("message", {}).get("content", "")
            if not content:
                raise OpenRouterError("Empty response from text model")

            # Strip markdown fences
            content = content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

            nutrition = json.loads(content)
            return _validate_nutrition_schema(nutrition)

    except json.JSONDecodeError as e:
        raise OpenRouterError(f"Text model returned invalid JSON: {e}")
    except httpx.HTTPError as e:
        raise OpenRouterError(f"OpenRouter API error: {e}")


def _validate_nutrition_schema(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and normalize nutrition data from AI response.

    Ensures required fields are present and have correct types.
    """
    required = ["kcal", "protein_g", "fat_g", "carbs_g"]
    for field in required:
        if field not in data:
            raise OpenRouterError(f"Missing required field: {field}")

    # Normalize numeric fields
    for field in ["kcal", "protein_g", "fat_g", "saturated_fat_g", "carbs_g", "sugar_g", "sodium_mg", "fibre_g"]:
        if field in data and data[field] is not None:
            data[field] = float(data[field])

    return data
