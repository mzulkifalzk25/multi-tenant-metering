"""Domain-level exception hierarchy.

Every error a use case can raise lives here so the API and Celery layers
can translate a single, closed set of exception types into HTTP responses
or retry decisions without depending on infrastructure details.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain errors."""


class TenantNotFoundError(DomainError):
    pass


class JobNotFoundError(DomainError):
    pass


class ExecutionNotFoundError(DomainError):
    pass


class WorkUnitNotFoundError(DomainError):
    pass


class InvalidJobStatusError(DomainError):
    pass


class TenantScopeViolationError(DomainError):
    """Raised when a request tries to access a resource outside its tenant."""


class DocumentProcessingError(DomainError):
    pass


class UnsupportedFileTypeError(DomainError):
    pass


class IdempotencyError(DomainError):
    """Raised when an idempotent operation detects a conflicting prior result."""


class StuckJobError(DomainError):
    """Raised internally when recovery detects an execution stuck beyond threshold."""
