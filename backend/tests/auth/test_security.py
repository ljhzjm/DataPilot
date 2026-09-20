from app.auth.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)


def test_password_hashing_and_session_tokens() -> None:
    encoded = hash_password("correct horse battery staple")

    assert verify_password("correct horse battery staple", encoded) is True
    assert verify_password("wrong password", encoded) is False
    assert encoded != hash_password("correct horse battery staple")

    token = generate_session_token()
    assert len(token) >= 32
    assert hash_session_token(token) == hash_session_token(token)
    assert hash_session_token(token) != token
