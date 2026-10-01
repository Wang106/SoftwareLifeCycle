"""Provider-neutral role names used by the authorization model and policy review."""

GLOBAL_ROLES = frozenset({"PLATFORM_ADMIN", "AUDITOR"})

SOFTWARE_ROLES = frozenset({"SOFTWARE_VIEWER", "SOFTWARE_MAINTAINER"})

PROJECT_ROLES = frozenset(
    {
        "PROJECT_VIEWER",
        "CONTRIBUTOR",
        "REVIEWER",
        "RELEASE_AUTHORITY",
        "DISTRIBUTION_AUTHORITY",
        "PRODUCTION_AUTHORITY",
        "PRODUCTION_OPERATOR",
    }
)

ALL_ROLES = GLOBAL_ROLES | SOFTWARE_ROLES | PROJECT_ROLES
