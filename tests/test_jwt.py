from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token


def test_access_token_has_required_claims():
    payload = decode_access_token(create_access_token("00000000-0000-0000-0000-000000000001", "patient"))
    assert payload["type"] == "access"
    assert "iat" in payload and "exp" in payload


def test_expired_token_is_rejected():
    token = jwt.encode({"sub": "x", "type": "access", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    try:
        decode_access_token(token)
        assert False, "expired token was accepted"
    except jwt.ExpiredSignatureError:
        pass
