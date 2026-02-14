"""JWT authentication helpers and decorators."""

import os
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import request

_jwt_secret_cache = None

def _get_jwt_secret():
    """Get JWT_SECRET from environment (cached), raising an error if not set."""
    global _jwt_secret_cache
    if _jwt_secret_cache is None:
        secret = os.getenv("JWT_SECRET")
        if not secret:
            raise RuntimeError("JWT_SECRET environment variable must be set")
        _jwt_secret_cache = secret
    return _jwt_secret_cache

JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24


class ApiError(Exception):
    """Application-level error mapped to an HTTP status code."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def generate_token(user_id, email):
    """Create a signed JWT for the given user."""
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)


def verify_token(token):
    """Decode and validate a JWT. Raises *ApiError* on failure."""
    try:
        return jwt.decode(token, _get_jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ApiError("Token has expired", 401)
    except jwt.InvalidTokenError:
        raise ApiError("Invalid token", 401)


def generate_password_reset_token(email):
    """Create a short-lived token for password reset."""
    payload = {
        "email": email,
        "purpose": "password_reset",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)


def verify_password_reset_token(token):
    """Decode and validate a password reset token. Raises *ApiError* on failure."""
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("purpose") != "password_reset":
            raise ApiError("Invalid token purpose", 401)
        return payload
    except jwt.ExpiredSignatureError:
        raise ApiError("Reset token has expired", 401)
    except jwt.InvalidTokenError:
        raise ApiError("Invalid reset token", 401)


def require_auth(f):
    """Flask route decorator that enforces Bearer-token authentication."""

    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise ApiError("Missing or invalid authorization header", 401)

        token = auth_header.replace("Bearer ", "", 1).strip()
        payload = verify_token(token)
        request.user_id = payload["user_id"]
        request.user_email = payload["email"]
        return f(*args, **kwargs)

    return decorated
