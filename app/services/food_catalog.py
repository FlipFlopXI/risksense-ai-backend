"""Read community-contributed product nutrition from Open Food Facts."""
from decimal import Decimal

import httpx
from fastapi import HTTPException

from app.schemas.nutrition import FoodSearchResult

OFF_BASE = "https://world.openfoodfacts.org"
OFF_SEARCH = "https://search.openfoodfacts.org/search"
OFF_HEADERS = {"User-Agent": "RiskSenseAI/1.0 (https://github.com/FlipFlopXI/risksense-ai-backend)"}
PRODUCT_FIELDS = "code,product_name,product_name_en,brands,nutriments"


def scale_nutrients(per_100g: tuple[Decimal, Decimal, Decimal, Decimal],
                    amount_g: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    multiplier = amount_g / Decimal(100)
    return tuple((value * multiplier).quantize(Decimal("0.01"))
                 for value in per_100g)


def _nutrient(value, limit: int) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return None
    if not result.is_finite() or result < 0 or result > limit:
        return None
    return result


def parse_product(raw: dict) -> FoodSearchResult | None:
    if not isinstance(raw, dict):
        return None
    nutrition = raw.get("nutriments") or {}
    if not isinstance(nutrition, dict):
        return None
    name = str(raw.get("product_name_en") or raw.get("product_name") or "").strip()
    code = str(raw.get("code") or "").strip()
    if len(name) < 2 or not code.isdigit():
        return None
    values = [
        _nutrient(nutrition.get("energy-kcal_100g"), 1000),
        _nutrient(nutrition.get("carbohydrates_100g"), 100),
        _nutrient(nutrition.get("fat_100g"), 100),
        _nutrient(nutrition.get("proteins_100g"), 100),
    ]
    if any(value is None for value in values):
        return None
    return FoodSearchResult(
        code=code, name=name[:200], brand=str(raw.get("brands") or "")[:100] or None,
        calories_per_100g=values[0], carbs_per_100g=values[1],
        fat_per_100g=values[2], protein_per_100g=values[3],
    )


def _get(path: str, params: dict | None = None) -> dict:
    try:
        response = httpx.get(f"{OFF_BASE}{path}", params=params, headers=OFF_HEADERS,
                             timeout=8, follow_redirects=False)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Invalid catalogue response")
        return data
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Food search is temporarily unavailable. Enter label values manually.") from None


def search_catalog(query: str) -> list[FoodSearchResult]:
    try:
        response = httpx.post(OFF_SEARCH, json={"q": query.strip(), "page_size": 30},
                              headers=OFF_HEADERS, timeout=8, follow_redirects=False)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Invalid catalogue response")
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Food search is temporarily unavailable. Enter label values manually.") from None
    found: dict[str, FoodSearchResult] = {}
    products = data.get("hits")
    for raw in products if isinstance(products, list) else []:
        if isinstance(raw, dict) and (product := parse_product(raw)) is not None:
            found[product.code] = product
    return list(found.values())


def get_catalog_product(barcode: str) -> FoodSearchResult:
    if not barcode.isdigit() or len(barcode) > 100:
        raise HTTPException(422, "Invalid product barcode.")
    data = _get(f"/api/v2/product/{barcode}.json", {"fields": PRODUCT_FIELDS})
    product = parse_product(data.get("product") or {})
    if product is None or product.code != barcode:
        raise HTTPException(422, "Complete nutrition information is unavailable for this product.")
    return product
