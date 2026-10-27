from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.schemas.nutrition import FoodLogCreate, NutritionGoalUpdate
from app.services.food_catalog import parse_product, get_catalog_product, search_catalog, scale_nutrients, _get


def _food(**changes):
    values = dict(
        log_date=date(2026, 10, 25), meal_type="breakfast", food_name="Test food",
        amount_g=Decimal("125"), calories_per_100g=Decimal("100"),
        carbs_per_100g=Decimal("10"), fat_per_100g=Decimal("2"),
        protein_per_100g=Decimal("4"),
    )
    values.update(changes)
    return FoodLogCreate(**values)


def test_food_entry_requires_real_nutrition_values_and_measured_amount():
    assert _food().amount_g == Decimal("125")
    assert _food(source="open_food_facts", source_id="1234567890123",
                 calories_per_100g=None, carbs_per_100g=None,
                 fat_per_100g=None, protein_per_100g=None).source_id == "1234567890123"
    for changes in (
        {"meal_type": "other"}, {"amount_g": 0}, {"amount_g": 5001},
        {"calories_per_100g": -1}, {"carbs_per_100g": 101},
        {"fat_per_100g": None}, {"protein_per_100g": None},
        {"source": "open_food_facts", "source_id": "not-a-barcode"},
    ):
        with pytest.raises(ValidationError):
            _food(**changes)


def test_goal_is_explicit_and_bounded():
    assert NutritionGoalUpdate(calories_kcal=2200).calories_kcal == 2200
    for value in (0, 499, 6001):
        with pytest.raises(ValidationError):
            NutritionGoalUpdate(calories_kcal=value)


def _catalog_item():
    return {
        "code": "1234567890123", "product_name": "Test food", "brands": "Example",
        "nutriments": {
            "energy-kcal_100g": 125, "carbohydrates_100g": 12,
            "fat_100g": 3, "proteins_100g": 5,
        },
    }


def test_catalog_parser_requires_complete_plausible_values():
    product = parse_product(_catalog_item())
    assert product.calories_per_100g == Decimal(125)
    assert product.protein_per_100g == Decimal(5)
    missing = _catalog_item()
    del missing["nutriments"]["fat_100g"]
    assert parse_product(missing) is None
    invalid = _catalog_item()
    invalid["nutriments"]["carbohydrates_100g"] = 140
    assert parse_product(invalid) is None


def test_nutrition_values_scale_to_measured_amount():
    assert scale_nutrients((Decimal("100"), Decimal("10"), Decimal("2"),
                            Decimal("4")), Decimal("125")) == (
        Decimal("125.00"), Decimal("12.50"), Decimal("2.50"), Decimal("5.00"))


def test_catalog_search_and_selected_product_are_checked_again():
    with patch("app.services.food_catalog.httpx.post") as search, patch("app.services.food_catalog._get") as fetch:
        search.return_value.json.return_value = {"hits": [_catalog_item()]}
        assert len(search_catalog("test")) == 1
        assert search.call_args.kwargs["json"] == {"q": "test", "page_size": 30}
        assert search.call_args.kwargs["follow_redirects"] is False
        fetch.return_value = {"product": _catalog_item()}
        assert get_catalog_product("1234567890123").name == "Test food"
        assert fetch.call_args.args[0].endswith("1234567890123.json")


def test_catalog_request_sends_only_app_identification():
    with patch("app.services.food_catalog.httpx.get") as request:
        request.return_value.json.return_value = {"products": []}
        assert _get("/cgi/search.pl", {"search_terms": "oats"}) == {"products": []}
        assert request.call_args.kwargs["headers"].keys() == {"User-Agent"}
        assert request.call_args.kwargs["follow_redirects"] is False
