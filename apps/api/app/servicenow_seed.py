"""Create the reference data the connector maps to in a ServiceNow instance: the ten assignment
groups, the six sites, and the four demo employees. Idempotent: records that already exist
(matched by name) are reused, never changed.

cd apps/api && uv run python -m app.servicenow_seed

Reads SERVICENOW_INSTANCE / SERVICENOW_USER / SERVICENOW_PASSWORD from .env. The user needs
rights to create groups, locations and users (for a personal developer instance, the
integration user's `admin` role, or run this once as admin).
"""

from app.agent.prompt import GROUPS
from app.config import get_settings
from app.services.servicenow import ServiceNowClient

SITES = {
    "Chicago HQ": {"city": "Chicago", "state": "IL", "country": "USA"},
    "Dallas DC": {"city": "Dallas", "state": "TX", "country": "USA"},
    "Atlanta DC": {"city": "Atlanta", "state": "GA", "country": "USA"},
    "Memphis DC": {"city": "Memphis", "state": "TN", "country": "USA"},
    "Toronto Office": {"city": "Toronto", "state": "ON", "country": "Canada"},
    "Remote": {},
}

# The Get help tab's demo personas (fictional).
PERSONAS = [
    ("Jordan", "Lee", "Memphis DC", "Receiving supervisor"),
    ("Priya", "Shah", "Remote", "Finance analyst"),
    ("Marcus", "Chen", "Chicago HQ", "Customer service lead"),
    ("Ana", "Torres", "Dallas DC", "Shipping clerk"),
]

DESCRIPTION = "Created by Incident Copilot for the Meridian Logistics demo."


def main() -> None:
    settings = get_settings()
    password = (
        settings.servicenow_password.get_secret_value() if settings.servicenow_password else ""
    )
    if not (settings.servicenow_instance and settings.servicenow_user and password):
        raise SystemExit(
            "Set SERVICENOW_INSTANCE, SERVICENOW_USER and SERVICENOW_PASSWORD in .env first."
        )
    sn = ServiceNowClient(settings.servicenow_instance, settings.servicenow_user, password)

    def ensure(table: str, name: str, fields: dict[str, str], match: str = "name") -> str:
        existing = sn.find(table, name, match)
        if existing:
            print(f"  exists   {table}: {name}")
            return existing
        created = sn.create(table, fields)
        print(f"  created  {table}: {name}")
        return str(created["sys_id"])

    print(f"Seeding {sn.instance}")
    for group in GROUPS:
        ensure("sys_user_group", group, {"name": group, "description": DESCRIPTION})
    locations = {
        site: ensure("cmn_location", site, {"name": site, **extra}) for site, extra in SITES.items()
    }
    for first, last, site, title in PERSONAS:
        name = f"{first} {last}"
        user_name = f"{first}.{last}".lower()
        ensure(
            "sys_user",
            name,
            {
                "user_name": user_name,
                "first_name": first,
                "last_name": last,
                "title": title,
                "email": f"{user_name}@meridian-logistics.example",
                "location": locations[site],
            },
        )
    print("Done.")


if __name__ == "__main__":
    main()
