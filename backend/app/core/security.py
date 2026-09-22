"""Security and API key authentication dependencies for internal operations."""

import secrets

from fastapi import Header

from app.core.config import settings
from app.core.exceptions import UnauthorizedError


def verify_internal_api_key(authorization: str | None = Header(None)) -> str:
    """Verify Bearer token against internal secret key using constant-time comparison."""
    if not authorization:
        raise UnauthorizedError("Encabezado de autorización ausente.")

    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise UnauthorizedError(
            "Formato de encabezado de autorización inválido. Debe ser 'Bearer <token>'."
        )

    token = parts[1]
    expected_token = settings.INTERNAL_API_KEY.get_secret_value()
    if not secrets.compare_digest(token, expected_token):
        raise UnauthorizedError("Token de autorización no válido.")

    return token
