# 0007: Detect major incidents and problem candidates in the lakehouse, draft the write-ups with Claude

**Status:** Accepted, 2026-09-30

## Context
The last two lifecycle stages look across tickets rather than at one. An outage arrives as dozens of tickets that should be managed as one major incident with one review. A recurring cause, like a bad client release, arrives as weeks of elevated volume that problem management should find and fix at the source. The overview's hotspot chart shows spikes, but it doesn't group tickets, rank problems or produce the documents these processes run on.

## Decision
**Detection is deterministic SQL in the refresh job** (`pipelines/src/lifecycle.sql`, rebuilt in full after the medallion pipeline):
- **Major incident:** a subcategory whose daily volume reaches at least 10 tickets and 5× its trailing 28-day average. When 80% or more of that day's tickets come from one site, the incident and its members are scoped to that site. Against the generator's ground truth it finds exactly the four planted outages, with member precision 0.99-1.00 and recall 1.00. It is stable across thresholds from 8/4× to 12/6×.
- **Problem candidate:** a subcategory whose 4-week volume reaches 2.5× its prior 12-week baseline (at least 15 tickets). The surge is the run of consecutive weeks at 2× baseline or more. Raw frequency was rejected as a signal: in this data every routine fix recurs every week (a password reset 369 times a year), and that is service work, not a problem. Repeat-CI was rejected too, because most CIs are shared services such as "Active Directory".
- **Evidence grade:** fixes are normalized (asset tags, numbers and KB references removed) and grouped. The candidate records the top fix's share of the surge against its share of the subcategory at other times. The API grades that lift as strong (≥2× and ≥50% of the surge), moderate (≥1.3×) or weak. Weak candidates are shown and labeled, not hidden.
- Candidates link to a major incident that falls inside their surge, and ticket pages link to both.

**Write-ups are one structured Claude call each**, cached per record: a post-incident review (impact, timeline from hourly arrivals, root cause, resolution, follow-ups) and a problem record (statement, root-cause hypothesis with stated confidence, evidence citing numbers, workaround, permanent fix, next steps). The prompts carry only lakehouse figures and an evenly spaced sample of tickets.

## Consequences
- Six candidates on the current data: the four outages, the planted GlobalProtect regression (6 weeks, 100 tickets above baseline, top fix 100% of the surge against 34% usually), and a weak WAN rise. For the WAN rise, the drafted record said confidence was low and pointed out a second cause visible in the samples (business-hours backup jobs).
- Detection is explainable and needs no model to train or monitor. Its thresholds are constants in one SQL file.
- Daily granularity would merge two unrelated outages in the same subcategory on the same day, and would split an outage that crosses midnight at a new site mix. Neither occurs in this data. Hourly detection is the next step if they do.
- Records are read-only. Accepting a problem record into a tracked state (known error, change raised) needs a writable table, like `kb_drafts`.
