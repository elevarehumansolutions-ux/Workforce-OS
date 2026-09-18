"""Central registry for all SQLAlchemy ORM models.

This module imports every model class defined in the application. It is
critical for two reasons:
1.  **Alembic Autogenerate**: Alembic needs all models to be imported into
    its environment to correctly detect schema changes.
2.  **SQLAlchemy Mapper**: Models referencing each other via string-based
    class names (e.g., ``relationship("User", ...)``) require the referenced
    models to be loaded into the registry first.

Import order generally follows dependency hierarchy to avoid resolution
issues during initialization.
"""

from app.modules.tenancy_identity.models import (
    Organization,
    User,
    Membership,
    Invite,
)
from app.modules.auth.models import (
    RefreshToken,
    EmailVerificationToken,
    PasswordResetToken,
)

__all__ = [
    "Organization",
    "User",
    "Membership",
    "Invite",
    "RefreshToken",
    "EmailVerificationToken",
    "PasswordResetToken",
]
