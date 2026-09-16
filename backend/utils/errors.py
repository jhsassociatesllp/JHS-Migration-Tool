"""Translates internal exceptions into messages a non-technical user can
act on. Never leak stack traces, SQL, or raw Python exception text to the
API response."""
from __future__ import annotations
from fastapi import HTTPException


class AppError(HTTPException):
    def __init__(self, status_code: int, message: str):
        super().__init__(status_code=status_code, detail={"message": message})


def not_found(entity: str) -> AppError:
    return AppError(404, f"{entity} could not be found. It may have been deleted.")


def bad_request(message: str) -> AppError:
    return AppError(400, message)


def missing_column(column: str, filename: str) -> AppError:
    return AppError(
        422,
        f'Column "{column}" could not be found in {filename}. '
        f"The file may have changed since the mapping was created. Please review the column mapping.",
    )
