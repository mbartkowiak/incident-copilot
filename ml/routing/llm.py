"""Zero-shot routing with Claude, as a comparison point for the trained model."""

import time
from dataclasses import dataclass
from typing import Literal

import anthropic
from pydantic import BaseModel

Group = Literal[
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
]

# Written the way a service desk lead would brief a new dispatcher.
SYSTEM = """You route IT incidents for Meridian Logistics to the team that will resolve them.

Teams:
- Service Desk: password resets, account unlocks, simple how-to questions resolvable on first contact.
- Identity & Access Management: MFA registration, SSO/SaaS login failures, shared drive and application access grants.
- Network Operations: VPN, Wi-Fi, site-wide network outages, WAN/internet slowness.
- End User Computing: laptops, docks, monitors, office printers, software installs, mobile device enrollment.
- Messaging & Collaboration: Outlook/Exchange mail flow, Teams audio, shared mailboxes.
- Security Operations: phishing reports, malware/EDR alerts, lost or stolen devices.
- ERP Applications: SAP performance, purchase order workflows, invoice posting.
- Database Administration: slow or timing-out report queries, replication lag, stale reporting data.
- Cloud Platform: customer-facing web apps and APIs returning errors, TLS certificate problems.
- Warehouse Systems: RF handheld scanners, shipping label printers, WMS wave release.

Pick the single team most likely to resolve the incident."""


class Routing(BaseModel):
    assignment_group: Group


@dataclass
class LlmPrediction:
    label: str
    latency_s: float
    input_tokens: int
    output_tokens: int


# $ per 1M tokens (input, output)
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def classify(client: anthropic.Anthropic, model: str, text: str) -> LlmPrediction:
    start = time.perf_counter()
    response = client.messages.parse(
        model=model,
        max_tokens=1024,
        system=SYSTEM,
        messages=[{"role": "user", "content": f"Incident:\n{text}"}],
        output_format=Routing,
    )
    latency = time.perf_counter() - start
    if response.stop_reason == "refusal" or response.parsed_output is None:
        label = "UNPARSEABLE"
    else:
        label = response.parsed_output.assignment_group
    return LlmPrediction(
        label=label,
        latency_s=latency,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )


def cost_per_1k(model: str, preds: list[LlmPrediction]) -> float:
    price_in, price_out = PRICES[model]
    total = sum(p.input_tokens * price_in + p.output_tokens * price_out for p in preds) / 1e6
    return total / len(preds) * 1000
