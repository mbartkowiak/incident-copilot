"""Deterministic generator for ServiceNow-shaped incident and knowledge data.

Output mirrors the ServiceNow incident / kb_knowledge tables closely enough that the
Databricks pipeline treats it like a real Table API extract, including realistic
defects (duplicates, missing fields, bad timestamps, PII) for the silver layer to handle.
"""

from __future__ import annotations

import calendar
import json
import random
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from importlib import resources
from typing import Any

from datagen import reference as ref

TS_FORMAT = "%Y-%m-%d %H:%M:%S"
SLOT_RE = re.compile(r"\{(\w+)\}")
AUTO_CLOSE = timedelta(days=7)

DUPLICATE_RATE = 0.008
MISSING_SHORT_DESC_RATE = 0.004
BAD_RESOLVED_RATE = 0.002
PII_RATE = 0.06
KB_REFERENCE_RATE = 0.55
REOPEN_RATE = 0.03


@dataclass(frozen=True)
class KbSpec:
    title: str
    symptoms: str
    cause: str
    steps: tuple[str, ...]


@dataclass(frozen=True)
class Archetype:
    id: str
    group: str
    category: str
    subcategory: str
    severity: str
    base_hours: float
    weight: float
    misroute_to: tuple[str, ...]
    misroute_rate: float
    sites: tuple[str, ...] | None
    ci: tuple[str, ...]
    slots: dict[str, tuple[str, ...]]
    short: tuple[str, ...]
    description: tuple[str, ...]
    resolution: tuple[str, ...]
    kb: KbSpec


@dataclass(frozen=True)
class Person:
    name: str
    user_name: str
    email: str
    phone: str


@dataclass
class Dataset:
    incidents: list[dict[str, Any]]
    kb_articles: list[dict[str, Any]]
    ground_truth: list[dict[str, Any]]
    manifest: dict[str, Any]


@dataclass
class _Draft:
    """An incident before numbering and defect injection."""

    record: dict[str, Any]
    archetype_id: str
    initial_group: str
    event: str | None
    has_pii: bool
    is_vague: bool
    defects: list[str] = field(default_factory=list)


def load_archetypes() -> list[Archetype]:
    text = resources.files("datagen").joinpath("archetypes.json").read_text(encoding="utf-8")
    archetypes = [_parse_archetype(raw) for raw in json.loads(text)]
    ids = [a.id for a in archetypes]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate archetype ids")
    return archetypes


def _parse_archetype(raw: dict[str, Any]) -> Archetype:
    kb = raw["kb"]
    arch = Archetype(
        id=raw["id"],
        group=raw["group"],
        category=raw["category"],
        subcategory=raw["subcategory"],
        severity=raw["severity"],
        base_hours=float(raw["base_hours"]),
        weight=float(raw["weight"]),
        misroute_to=tuple(raw["misroute_to"]),
        misroute_rate=float(raw["misroute_rate"]),
        sites=tuple(raw["sites"]) if "sites" in raw else None,
        ci=tuple(raw["ci"]),
        slots={k: tuple(v) for k, v in raw.get("slots", {}).items()},
        short=tuple(raw["short"]),
        description=tuple(raw["description"]),
        resolution=tuple(raw["resolution"]),
        kb=KbSpec(kb["title"], kb["symptoms"], kb["cause"], tuple(kb["steps"])),
    )
    _validate(arch)
    return arch


def _validate(a: Archetype) -> None:
    problems: list[str] = []
    if a.group not in ref.GROUPS:
        problems.append(f"unknown group {a.group!r}")
    if a.severity not in ref.SEVERITY_IMPACT:
        problems.append(f"unknown severity {a.severity!r}")
    for g in a.misroute_to:
        if g not in ref.GROUPS or g == a.group:
            problems.append(f"bad misroute group {g!r}")
    for s in a.sites or ():
        if s not in ref.SITES:
            problems.append(f"unknown site {s!r}")
    known_slots = set(a.slots) | {"site"}
    for template in (*a.ci, *a.short, *a.description, *a.resolution):
        for slot in SLOT_RE.findall(template):
            if slot not in known_slots:
                problems.append(f"unresolvable slot {{{slot}}} in {template!r}")
    if problems:
        raise ValueError(f"archetype {a.id}: " + "; ".join(problems))


def generate(
    count: int = 8000,
    seed: int = 42,
    start: date = date(2025, 10, 1),
    end: date = date(2026, 9, 27),
) -> Dataset:
    """Generate `count` baseline incidents plus planted event bursts between start and end."""
    if end <= start:
        raise ValueError("end must be after start")
    rng = random.Random(seed)
    archetypes = load_archetypes()
    by_id = {a.id: a for a in archetypes}
    as_of = datetime.combine(end, datetime.max.time()).replace(microsecond=0)

    callers, agents = _people(rng)
    kb_articles, kb_by_archetype = _kb_articles(rng, archetypes, agents, start)
    ctx = _Context(rng, callers, agents, kb_by_archetype, as_of, _vague_by_archetype(by_id))

    drafts = _baseline(ctx, archetypes, count, start, end)
    bursts_used: list[dict[str, Any]] = []
    for burst in ref.BURSTS:
        if not (start <= burst.start.date() <= end):
            continue
        drafts.extend(_burst(ctx, by_id[burst.archetype_id], burst))
        bursts_used.append(
            {
                "name": burst.name,
                "description": burst.description,
                "archetype_id": burst.archetype_id,
                "start": burst.start.strftime(TS_FORMAT),
                "count": burst.count,
                "site": burst.site,
            }
        )

    drafts.sort(key=lambda d: d.record["opened_at"])
    for i, d in enumerate(drafts):
        d.record["number"] = f"INC{10001 + i:07d}"

    incidents = _inject_defects(rng, drafts)
    ground_truth = [
        {
            "number": d.record["number"],
            "archetype_id": d.archetype_id,
            "true_assignment_group": by_id[d.archetype_id].group,
            "initial_assignment_group": d.initial_group,
            "event": d.event,
            "has_pii": d.has_pii,
            "is_vague": d.is_vague,
            "defects": d.defects,
        }
        for d in drafts
    ]

    manifest = {
        "schema_version": 1,
        "company": "Meridian Logistics (fictional)",
        "seed": seed,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "baseline_count": count,
        "unique_incidents": len(drafts),
        "incident_rows": len(incidents),
        "kb_articles": len(kb_articles),
        "kb_by_archetype": kb_by_archetype,
        "bursts": bursts_used,
        "weight_windows": [
            {
                "name": w.name,
                "description": w.description,
                "archetype_id": w.archetype_id,
                "start": w.start.isoformat(),
                "end": w.end.isoformat(),
                "multiplier": w.multiplier,
            }
            for w in ref.WEIGHT_WINDOWS
        ],
        "month_end": {
            "archetype_id": ref.MONTH_END_ARCHETYPE,
            "multiplier": ref.MONTH_END_MULTIPLIER,
        },
    }
    return Dataset(incidents, kb_articles, ground_truth, manifest)


@dataclass
class _Context:
    rng: random.Random
    callers: list[Person]
    agents: dict[str, list[Person]]
    kb_by_archetype: dict[str, str]
    as_of: datetime
    vague: dict[str, list[ref.VagueFamily]]


def _vague_by_archetype(by_id: dict[str, Archetype]) -> dict[str, list[ref.VagueFamily]]:
    result: dict[str, list[ref.VagueFamily]] = {}
    for name, family in ref.VAGUE_FAMILIES.items():
        for archetype_id in family.archetype_ids:
            if archetype_id not in by_id:
                raise ValueError(f"vague family {name} references unknown archetype {archetype_id}")
            result.setdefault(archetype_id, []).append(family)
    return result


def _people(rng: random.Random) -> tuple[list[Person], dict[str, list[Person]]]:
    combos = [(f, last) for f in ref.FIRST_NAMES for last in ref.LAST_NAMES]
    rng.shuffle(combos)
    people = [
        Person(
            name=f"{first} {last}",
            user_name=f"{first}.{last}".lower(),
            email=f"{first}.{last}@{ref.COMPANY_DOMAIN}".lower(),
            phone=f"(312) 555-01{rng.randrange(100):02d}",
        )
        for first, last in combos[:850]
    ]
    agents = {g: people[800 + i * 5 : 800 + (i + 1) * 5] for i, g in enumerate(ref.GROUPS)}
    return people[:800], agents


def _kb_articles(
    rng: random.Random, archetypes: list[Archetype], agents: dict[str, list[Person]], start: date
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    articles: list[dict[str, Any]] = []
    kb_by_archetype: dict[str, str] = {}
    for i, a in enumerate(archetypes):
        number = f"KB{10001 + i:07d}"
        kb_by_archetype[a.id] = number
        published = datetime.combine(start, datetime.min.time()) - timedelta(
            days=rng.randint(30, 400), minutes=rng.randint(0, 1439)
        )
        steps = "\n".join(f"{n}. {s}" for n, s in enumerate(a.kb.steps, 1))
        text = (
            f"# {a.kb.title}\n\n## Symptoms\n{a.kb.symptoms}\n\n## Cause\n{a.kb.cause}\n\n"
            f"## Resolution\n{steps}\n"
        )
        articles.append(
            {
                "number": number,
                "short_description": a.kb.title,
                "text": text,
                "kb_category": a.group,
                "category": a.category,
                "subcategory": a.subcategory,
                "workflow_state": "published",
                "author": rng.choice(agents[a.group]).name,
                "published": published.strftime(TS_FORMAT),
                "sys_updated_on": published.strftime(TS_FORMAT),
            }
        )
    return articles, kb_by_archetype


def _baseline(
    ctx: _Context, archetypes: list[Archetype], count: int, start: date, end: date
) -> list[_Draft]:
    rng = ctx.rng
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    growth = 0.15
    day_weights = [
        ref.WEEKDAY_FACTOR[d.weekday()] * (1 + growth * i / len(days)) for i, d in enumerate(days)
    ]
    chosen_days = sorted(rng.choices(days, weights=day_weights, k=count))

    drafts: list[_Draft] = []
    weight_cache: dict[date, list[float]] = {}
    for day in chosen_days:
        if day not in weight_cache:
            weight_cache[day] = [_archetype_weight(a, day) for a in archetypes]
        arch = rng.choices(archetypes, weights=weight_cache[day])[0]
        hours = (
            ref.WAREHOUSE_HOURS if arch.group in ref.TWENTY_FOUR_SEVEN_GROUPS else ref.OFFICE_HOURS
        )
        hour = rng.choices(range(24), weights=hours)[0]
        opened = datetime.combine(day, datetime.min.time()) + timedelta(
            hours=hour, minutes=rng.randrange(60), seconds=rng.randrange(60)
        )
        window = _active_window(arch.id, day)
        drafts.append(
            _make_incident(
                ctx,
                arch,
                opened,
                event=window.name if window else None,
                resolution_index=window.resolution_index if window else None,
            )
        )
    return drafts


def _archetype_weight(a: Archetype, day: date) -> float:
    weight = a.weight
    if a.id == ref.MONTH_END_ARCHETYPE:
        last = calendar.monthrange(day.year, day.month)[1]
        near_close = day.day >= last - 2 or day.day == 1
        weight *= ref.MONTH_END_MULTIPLIER if near_close else ref.OFF_MONTH_END_MULTIPLIER
    window = _active_window(a.id, day)
    if window:
        weight *= window.multiplier
    return weight


def _active_window(archetype_id: str, day: date) -> ref.WeightWindow | None:
    for w in ref.WEIGHT_WINDOWS:
        if w.archetype_id == archetype_id and w.start <= day <= w.end:
            return w
    return None


def _burst(ctx: _Context, arch: Archetype, burst: ref.Burst) -> list[_Draft]:
    rng = ctx.rng
    restored = burst.start + timedelta(minutes=burst.duration_minutes)
    drafts = []
    for _ in range(burst.count):
        opened = burst.start + timedelta(
            minutes=rng.uniform(0, burst.duration_minutes * 0.7), seconds=rng.randrange(60)
        )
        resolved = restored + timedelta(minutes=rng.uniform(5, 90))
        drafts.append(
            _make_incident(
                ctx,
                arch,
                opened.replace(microsecond=0),
                event=burst.name,
                site=burst.site,
                impact_urgency=(burst.impact, burst.urgency),
                resolution_index=burst.resolution_index,
                resolved_at=resolved.replace(microsecond=0),
            )
        )
    return drafts


def _weighted(rng: random.Random, dist: dict[Any, float]) -> Any:
    return rng.choices(list(dist), weights=list(dist.values()))[0]


def _make_incident(
    ctx: _Context,
    arch: Archetype,
    opened: datetime,
    *,
    event: str | None = None,
    site: str | None = None,
    impact_urgency: tuple[int, int] | None = None,
    resolution_index: int | None = None,
    resolved_at: datetime | None = None,
) -> _Draft:
    rng = ctx.rng
    if site is None:
        site = rng.choice(arch.sites) if arch.sites else _weighted(rng, ref.SITES)
    slot_values: dict[str, str] = {"site": site}

    def fill(template: str) -> str:
        def sub(m: re.Match[str]) -> str:
            name = m.group(1)
            if name not in slot_values:
                slot_values[name] = rng.choice(arch.slots[name])
            return slot_values[name]

        return SLOT_RE.sub(sub, template)

    short = fill(rng.choice(arch.short))
    description = fill(rng.choice(arch.description))
    ci = fill(rng.choice(arch.ci))
    families = ctx.vague.get(arch.id)
    is_vague = bool(families) and rng.random() < ref.VAGUE_RATE
    if families and is_vague:
        family = rng.choice(families)
        short = rng.choice(family.short)
        description = rng.choice(family.description)

    if impact_urgency:
        impact, urgency = impact_urgency
    else:
        impact = _weighted(rng, ref.SEVERITY_IMPACT[arch.severity])
        urgency = _weighted(rng, ref.SEVERITY_URGENCY[arch.severity])
    priority = ref.PRIORITY_MATRIX[(impact, urgency)]

    route = [arch.group]
    if arch.misroute_to and rng.random() < arch.misroute_rate:
        wrong = list(arch.misroute_to)
        rng.shuffle(wrong)
        hops = 2 if len(wrong) > 1 and rng.random() < 0.15 else 1
        route = [*wrong[:hops], arch.group]
    initial_group = route[0]

    if resolved_at is None:
        hours = arch.base_hours * ref.PRIORITY_TIME_FACTOR[priority] * rng.lognormvariate(
            0, 0.6
        ) + (len(route) - 1) * rng.uniform(2, 10)
        resolved_at = opened + timedelta(hours=max(hours, 0.1))
        resolved_at = resolved_at.replace(microsecond=0)

    caller = rng.choice(ctx.callers)
    has_pii = rng.random() < PII_RATE
    if has_pii:
        description += rng.choice(
            [
                f" You can reach me at {caller.phone}.",
                f" Please email me at {caller.email} if you need anything.",
                f" Call my cell {caller.phone} - I'm away from my desk.",
            ]
        )
    if rng.random() < 0.08:
        short = short.lower()
    elif priority <= 3 and rng.random() < 0.05:
        short = f"URGENT - {short}"

    record: dict[str, Any] = {
        "number": None,
        "sys_id": f"{rng.getrandbits(128):032x}",
        "opened_at": opened.strftime(TS_FORMAT),
        "sys_created_on": opened.strftime(TS_FORMAT),
        "short_description": short,
        "description": description,
        "caller_id": caller.name,
        "contact_type": _weighted(rng, ref.CONTACT_TYPES),
        "location": site,
        "category": arch.category,
        "subcategory": arch.subcategory,
        "cmdb_ci": ci,
        "impact": impact,
        "urgency": urgency,
        "priority": priority,
    }

    if resolved_at > ctx.as_of:
        _fill_open(ctx, record, opened, initial_group, priority)
    else:
        _fill_resolved(
            ctx, record, arch, opened, resolved_at, route, priority, fill, resolution_index
        )

    return _Draft(record, arch.id, initial_group, event, has_pii, is_vague)


def _fill_open(
    ctx: _Context, record: dict[str, Any], opened: datetime, group: str, priority: int
) -> None:
    rng = ctx.rng
    age = ctx.as_of - opened
    is_new = age < timedelta(hours=1)
    record.update(
        {
            "state": "New" if is_new else rng.choice(["In Progress", "In Progress", "On Hold"]),
            "assignment_group": group,
            "assigned_to": None if is_new else rng.choice(ctx.agents[group]).name,
            "reassignment_count": 0,
            "reopen_count": 0,
            "resolved_at": None,
            "closed_at": None,
            "close_code": None,
            "close_notes": None,
            "made_sla": age.total_seconds() / 3600 <= ref.SLA_HOURS[priority],
            "work_notes": None,
            "sys_updated_on": (opened + (age * rng.uniform(0.1, 0.9))).strftime(TS_FORMAT),
        }
    )


def _fill_resolved(
    ctx: _Context,
    record: dict[str, Any],
    arch: Archetype,
    opened: datetime,
    resolved_at: datetime,
    route: list[str],
    priority: int,
    fill: Callable[[str], str],
    resolution_index: int | None,
) -> None:
    rng = ctx.rng
    idx = resolution_index if resolution_index is not None else rng.randrange(len(arch.resolution))
    close_notes = fill(arch.resolution[idx])
    if rng.random() < KB_REFERENCE_RATE:
        close_notes += f" Followed {ctx.kb_by_archetype[arch.id]}."

    closed_at = resolved_at + AUTO_CLOSE
    is_closed = closed_at <= ctx.as_of
    resolver = rng.choice(ctx.agents[arch.group])

    notes: list[str] = []
    elapsed = resolved_at - opened
    for hop, (current, nxt) in enumerate(zip(route, route[1:], strict=False)):
        when = opened + elapsed * (hop + 1) / (len(route) + 1)
        who = rng.choice(ctx.agents[current]).name
        notes.append(
            f"{when.strftime(TS_FORMAT)} - {who}: Not a {current} issue. Reassigning to {nxt}."
        )
    notes.append(f"{resolved_at.strftime(TS_FORMAT)} - {resolver.name}: Resolved. See close notes.")

    mttr_hours = elapsed.total_seconds() / 3600
    record.update(
        {
            "state": "Closed" if is_closed else "Resolved",
            "assignment_group": arch.group,
            "assigned_to": resolver.name,
            "reassignment_count": len(route) - 1,
            "reopen_count": 1 if rng.random() < REOPEN_RATE else 0,
            "resolved_at": resolved_at.strftime(TS_FORMAT),
            "closed_at": closed_at.strftime(TS_FORMAT) if is_closed else None,
            "close_code": _weighted(rng, ref.CLOSE_CODES),
            "close_notes": close_notes,
            "made_sla": mttr_hours <= ref.SLA_HOURS[priority],
            "work_notes": "\n".join(notes),
            "sys_updated_on": (closed_at if is_closed else resolved_at).strftime(TS_FORMAT),
        }
    )


def _inject_defects(rng: random.Random, drafts: list[_Draft]) -> list[dict[str, Any]]:
    """Add realistic extract defects. Returns the incident rows as they would land in bronze."""
    rows: list[dict[str, Any]] = []
    for d in drafts:
        rec = d.record
        if rng.random() < MISSING_SHORT_DESC_RATE:
            rec["short_description"] = None
            d.defects.append("missing_short_description")
        if rec["resolved_at"] and rng.random() < BAD_RESOLVED_RATE:
            opened = datetime.strptime(rec["opened_at"], TS_FORMAT)
            rec["resolved_at"] = (opened - timedelta(hours=rng.uniform(1, 48))).strftime(TS_FORMAT)
            d.defects.append("resolved_before_opened")
        rows.append(rec)
        if rng.random() < DUPLICATE_RATE:
            rows.append(dict(rec))
            d.defects.append("duplicate_row")
    return rows
