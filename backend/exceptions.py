from typing import Any


class AppException(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class MovieNotFoundError(AppException):
    def __init__(self, movie_id: int | str | None = None) -> None:
        super().__init__(
            code="MOVIE_NOT_FOUND",
            message="Movie not found",
            status_code=404,
            details={"movie_id": movie_id} if movie_id is not None else None,
        )


class UserNotFoundError(AppException):
    def __init__(self) -> None:
        super().__init__("USER_NOT_FOUND", "User not found", 404)


class InvalidCredentialsError(AppException):
    def __init__(self) -> None:
        super().__init__("INVALID_CREDENTIALS", "Invalid email or password", 401)


class TokenExpiredError(AppException):
    def __init__(self) -> None:
        super().__init__("TOKEN_EXPIRED", "Authentication token has expired", 401)


class TokenRevokedError(AppException):
    def __init__(self) -> None:
        super().__init__("TOKEN_REVOKED", "Authentication token was revoked", 401)


class AccountDisabledError(AppException):
    def __init__(self) -> None:
        super().__init__("ACCOUNT_DISABLED", "This account has been disabled", 403)


class EmailAlreadyTakenError(AppException):
    def __init__(self) -> None:
        super().__init__("EMAIL_TAKEN", "This email is already registered", 409)


class FaceNotDetectedError(AppException):
    def __init__(self) -> None:
        super().__init__(
            "FACE_NOT_DETECTED",
            "No face detected in the uploaded image",
            422,
        )


class InvalidImageError(AppException):
    def __init__(self, reason: str) -> None:
        super().__init__(
            code="INVALID_IMAGE",
            message=f"Invalid image: {reason}",
            status_code=422,
            details={"reason": reason},
        )


class MLServiceUnavailableError(AppException):
    def __init__(self, service: str) -> None:
        super().__init__(
            code="ML_SERVICE_UNAVAILABLE",
            message=f"ML service '{service}' is currently unavailable",
            status_code=503,
            details={"service": service},
        )


class RatingNotFoundError(AppException):
    def __init__(self) -> None:
        super().__init__("RATING_NOT_FOUND", "Rating not found", 404)
