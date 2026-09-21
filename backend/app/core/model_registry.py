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
from app.modules.audit_and_notification.models import (
    AuditLog,
    Notification,
)
from app.modules.organization.models import (
    Location,
    Department,
    Position,
    Employee,
)
from app.modules.business_dna.models import (
    BusinessDNA,
    BusinessDNACoreValue,
)
from app.modules.okrs.models import (
    OKR,
    KeyResult,
)

__all__ = [
    "Organization",
    "User",
    "Membership",
    "Invite",
    "RefreshToken",
    "EmailVerificationToken",
    "PasswordResetToken",
    "AuditLog",
    "Notification",
    "Location",
    "Department",
    "Position",
    "Employee",
    "BusinessDNA",
    "BusinessDNACoreValue",
    "OKR",
    "KeyResult",
]
