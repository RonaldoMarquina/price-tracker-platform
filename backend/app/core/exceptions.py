"""Application domain exceptions."""


class AppException(Exception):
    """Base application exception."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppException):
    """Exception for resources not found."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=404)


class ProductNotFoundError(NotFoundError):
    """Raised when a requested product does not exist."""

    def __init__(self, product_id: str | None = None) -> None:
        message = "El producto solicitado no existe."
        if product_id:
            message = f"El producto con ID '{product_id}' no existe."
        super().__init__(code="PRODUCT_NOT_FOUND", message=message)


class StoreNotFoundError(NotFoundError):
    """Raised when a requested store does not exist."""

    def __init__(self, store_id: str | None = None) -> None:
        message = "La tienda solicitada no existe."
        if store_id:
            message = f"La tienda con ID '{store_id}' no existe."
        super().__init__(code="STORE_NOT_FOUND", message=message)


class UnauthorizedError(AppException):
    """Raised when internal API authorization fails."""

    def __init__(self, message: str = "Credenciales de autorización inválidas o ausentes.") -> None:
        super().__init__(code="UNAUTHORIZED", message=message, status_code=401)
