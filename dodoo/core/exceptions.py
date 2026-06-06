class DodooError(Exception):
    """Base exception for all dodoo errors."""


class SchemaConflictError(DodooError):
    """Raised when a destructive schema change is detected during migration."""


class ModuleLoadError(DodooError):
    """Raised when a module cannot be discovered, parsed, or loaded."""


class CycleError(DodooError):
    """Raised when a circular dependency is detected in the module graph."""


class AuthenticationError(DodooError):
    """Raised when credentials are invalid or a session token is expired/missing."""


class AccessError(DodooError):
    """Raised when an operation is denied by an ir.rule access control rule."""


class RouteConflictError(DodooError):
    """Raised when two modules attempt to register the same (method, path) route."""


class DomainError(DodooError):
    """Raised when a domain filter contains an unknown field or unsupported operator."""
