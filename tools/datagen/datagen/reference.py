"""Static reference data for the fictional company "Meridian Logistics"."""

from dataclasses import dataclass
from datetime import date, datetime

COMPANY_DOMAIN = "meridian-logistics.example"

GROUPS: tuple[str, ...] = (
    "Service Desk",
    "Identity & Access Management",
    "Network Operations",
    "End User Computing",
    "Messaging & Collaboration",
    "Security Operations",
    "ERP Applications",
    "Database Administration",
    "Cloud Platform",
    "Warehouse Systems",
)

SITES: dict[str, float] = {
    "Chicago HQ": 0.35,
    "Dallas DC": 0.15,
    "Atlanta DC": 0.12,
    "Memphis DC": 0.10,
    "Toronto Office": 0.10,
    "Remote": 0.18,
}

# ServiceNow OOB priority lookup: (impact, urgency) -> priority
PRIORITY_MATRIX: dict[tuple[int, int], int] = {
    (1, 1): 1, (1, 2): 2, (1, 3): 3,
    (2, 1): 2, (2, 2): 3, (2, 3): 4,
    (3, 1): 3, (3, 2): 4, (3, 3): 5,
}  # fmt: skip

SLA_HOURS: dict[int, float] = {1: 4, 2: 8, 3: 72, 4: 120, 5: 240}

# Higher-priority work gets picked up faster.
PRIORITY_TIME_FACTOR: dict[int, float] = {1: 0.4, 2: 0.6, 3: 1.0, 4: 1.3, 5: 1.6}

SEVERITY_IMPACT: dict[str, dict[int, float]] = {
    "low": {3: 0.8, 2: 0.2},
    "medium": {3: 0.4, 2: 0.5, 1: 0.1},
    "high": {2: 0.5, 1: 0.5},
}
SEVERITY_URGENCY: dict[str, dict[int, float]] = {
    "low": {3: 0.6, 2: 0.35, 1: 0.05},
    "medium": {3: 0.3, 2: 0.5, 1: 0.2},
    "high": {2: 0.4, 1: 0.6},
}

CONTACT_TYPES: dict[str, float] = {
    "self-service": 0.42,
    "email": 0.23,
    "phone": 0.25,
    "walk-in": 0.05,
    "virtual_agent": 0.05,
}

CLOSE_CODES: dict[str, float] = {
    "Solved (Permanently)": 0.35,
    "Solved Remotely (Permanently)": 0.35,
    "Solved (Work Around)": 0.12,
    "Solved Remotely (Work Around)": 0.10,
    "Not Solved (Not Reproducible)": 0.04,
    "Closed/Resolved by Caller": 0.04,
}

# Mon..Sun
WEEKDAY_FACTOR: tuple[float, ...] = (1.25, 1.1, 1.05, 1.0, 0.9, 0.3, 0.25)

OFFICE_HOURS: tuple[float, ...] = (
    0.2, 0.1, 0.1, 0.1, 0.2, 0.5, 1.5, 4, 8, 9, 8, 7,
    5, 7, 8, 7, 6, 4, 2, 1, 0.8, 0.6, 0.4, 0.3,
)  # fmt: skip
WAREHOUSE_HOURS: tuple[float, ...] = (
    3, 3, 3, 2, 2, 4, 6, 6, 5, 5, 5, 4,
    4, 5, 6, 6, 5, 4, 4, 4, 4, 3, 3, 3,
)  # fmt: skip
TWENTY_FOUR_SEVEN_GROUPS = frozenset({"Warehouse Systems"})

FIRST_NAMES: tuple[str, ...] = (
    "Aaliyah", "Adrian", "Aisha", "Alejandro", "Amara", "Andre", "Anika", "Ben", "Bianca",
    "Carlos", "Chen", "Chloe", "Darius", "Deepa", "Diego", "Elena", "Emeka", "Farah",
    "Gabriel", "Grace", "Hana", "Hector", "Imani", "Isaac", "Jamal", "Jasmine", "Jin",
    "Jordan", "Julia", "Kai", "Keisha", "Kenji", "Laila", "Liam", "Lucia", "Malik",
    "Maya", "Mateo", "Mei", "Nadia", "Noah", "Olivia", "Omar", "Priya", "Quinn", "Rafael",
    "Rania", "Ravi", "Rosa", "Samuel", "Sana", "Sofia", "Tariq", "Tessa", "Tomas",
    "Uma", "Victor", "Wei", "Yara", "Zane",
)  # fmt: skip
LAST_NAMES: tuple[str, ...] = (
    "Abbott", "Adeyemi", "Alvarez", "Bauer", "Bennett", "Brooks", "Castillo", "Chen",
    "Cohen", "Diaz", "Dubois", "Edwards", "Evans", "Fischer", "Flores", "Garcia", "Gupta",
    "Hansen", "Hughes", "Ibrahim", "Jackson", "Johansson", "Kaur", "Kim", "Kowalski",
    "Lee", "Lopez", "Martin", "Mensah", "Moreau", "Murphy", "Nakamura", "Nguyen", "Novak",
    "Okafor", "Olsen", "Patel", "Perez", "Price", "Quinn", "Ramirez", "Reyes", "Rossi",
    "Sato", "Schmidt", "Shah", "Singh", "Sullivan", "Tanaka", "Thompson", "Torres",
    "Usman", "Vargas", "Walker", "Watson", "Weber", "Williams", "Wong", "Young", "Zhang",
)  # fmt: skip


@dataclass(frozen=True)
class Burst:
    """A planted cluster of related incidents (an outage) for analytics to discover."""

    name: str
    description: str
    archetype_id: str
    start: datetime
    duration_minutes: int
    count: int
    impact: int
    urgency: int
    resolution_index: int
    site: str | None = None


@dataclass(frozen=True)
class WeightWindow:
    """A period where one archetype becomes more frequent (e.g. after a bad rollout)."""

    name: str
    description: str
    archetype_id: str
    start: date
    end: date
    multiplier: float
    resolution_index: int


BURSTS: tuple[Burst, ...] = (
    Burst(
        name="email-outage-2026-01-20",
        description="Exchange Online service incident: company-wide mail flow disruption.",
        archetype_id="msg-outlook-sync",
        start=datetime(2026, 1, 20, 7, 10),
        duration_minutes=300,
        count=140,
        impact=2,
        urgency=2,
        resolution_index=1,
    ),
    Burst(
        name="chicago-core-switch-2026-03-10",
        description="Core switch supervisor failure at Chicago HQ.",
        archetype_id="net-site-outage",
        start=datetime(2026, 3, 10, 8, 40),
        duration_minutes=260,
        count=85,
        impact=2,
        urgency=1,
        resolution_index=0,
        site="Chicago HQ",
    ),
    Burst(
        name="cert-expiry-2026-07-15",
        description="Customer-facing TLS certificate expired after auto-renewal failed.",
        archetype_id="cloud-cert-expired",
        start=datetime(2026, 7, 15, 6, 5),
        duration_minutes=180,
        count=35,
        impact=2,
        urgency=1,
        resolution_index=0,
    ),
    Burst(
        name="memphis-scanner-certs-2026-08-18",
        description="Handheld scanner Wi-Fi certificates expired at Memphis DC.",
        archetype_id="whs-scanner-sync",
        start=datetime(2026, 8, 18, 5, 30),
        duration_minutes=1500,
        count=60,
        impact=2,
        urgency=2,
        resolution_index=1,
        site="Memphis DC",
    ),
)

WEIGHT_WINDOWS: tuple[WeightWindow, ...] = (
    WeightWindow(
        name="vpn-client-upgrade-2026-05",
        description="GlobalProtect client auto-upgrade caused recurring VPN failures for ~6 weeks.",
        archetype_id="net-vpn-connect",
        start=date(2026, 5, 4),
        end=date(2026, 6, 15),
        multiplier=4.0,
        resolution_index=0,
    ),
)

MONTH_END_ARCHETYPE = "erp-month-end-slow"
MONTH_END_MULTIPLIER = 6.0
OFF_MONTH_END_MULTIPLIER = 0.25
