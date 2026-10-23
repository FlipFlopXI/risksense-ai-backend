import json
import pytest
from pydantic import ValidationError
from fastapi.exceptions import RequestValidationError

from app.schemas.auth import UserRegisterRequest
from app.main import registration_error_details


def registration(password: str) -> UserRegisterRequest:
    return UserRegisterRequest(email="example@example.com", password=password,
                               first_name="Example", last_name="Patient")


def test_six_character_password_with_required_character_classes_is_accepted():
    assert registration("Ab1!xy").password == "Ab1!xy"


@pytest.mark.parametrize("password", ["Ab1!x", "abc1!x", "Abc!xy", "Abc1xy"])
def test_registration_rejects_short_or_missing_character_class(password):
    with pytest.raises(ValidationError):
        registration(password)


def test_registration_error_response_never_echoes_password():
    error = RequestValidationError([{"loc": ("body", "password"),
                                     "msg": "Password is too short", "type": "value_error",
                                     "input": "bad"}])
    detail = registration_error_details(error)
    serialized = json.dumps(detail)
    assert '"input"' not in serialized
    assert '"bad"' not in serialized
