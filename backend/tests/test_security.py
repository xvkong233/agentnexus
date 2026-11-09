"""安全模块单测：密码哈希、JWT、API Key、HMAC。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.security import (  # noqa: E402
    create_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    hmac_sign,
    verify_password,
)


def test_password_hash_roundtrip():
    h = hash_password("s3cret-pass")
    assert h.startswith("scrypt$")
    assert verify_password("s3cret-pass", h)
    assert not verify_password("wrong", h)
    # 相同密码两次哈希不同（随机盐）
    assert h != hash_password("s3cret-pass")


def test_jwt_roundtrip():
    token = create_token("tenant", "user-1", tenant_id="t-1", name="u")
    payload = decode_token(token)
    assert payload["role"] == "tenant"
    assert payload["sub"] == "user-1"
    assert payload["tenant_id"] == "t-1"


def test_api_key_generation():
    full, prefix, key_hash = generate_api_key("ak")
    assert full.startswith("ak-")
    assert prefix == full[:12]
    assert hash_api_key(full) == key_hash
    full2, _, hash2 = generate_api_key("ak")
    assert hash2 != key_hash


def test_hmac_sign_stable():
    sig1 = hmac_sign("secret", b"body", "123")
    sig2 = hmac_sign("secret", b"body", "123")
    sig3 = hmac_sign("secret", b"body", "456")
    assert sig1 == sig2
    assert sig1 != sig3
