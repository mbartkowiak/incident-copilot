# 0005: Show SLA risk as a historical lookup and a routing check, not a trained classifier

**Status:** Accepted, 2026-09-30

## Context
The Incidents page shows each ticket's lifecycle and should warn when a ticket is likely to miss its SLA. The plan was a breach-risk classifier trained on intake fields (text, priority, category, site, channel, hour), registered in Unity Catalog like the routing model.

`ml/sla/evaluate.py` compared three estimators on the held-out months (tickets opened from 2026-07-01, cutoff as for routing). Report: `ml/reports/sla_risk_eval.json`.

| Estimator | ROC AUC, all tickets | ROC AUC, P1/P2 only | Brier, P1/P2 |
|---|---|---|---|
| Priority's historical breach rate | 0.946 | 0.486 | 0.213 |
| Subcategory × priority breach rate, smoothed | **0.967** | **0.688** | **0.188** |
| Logistic regression on intake fields | 0.960 | 0.616 | 0.208 |

Breaches are 4% of tickets and almost all P1/P2 (their targets are 4 h and 8 h; P3-P5 targets are days). Priority alone ranks the full population well, so the question that matters is which urgent tickets will breach. There the classifier did worse than a two-column lookup, and it was overconfident at the top of its range.

The data also shows why: **P1/P2 tickets sent to the wrong team first breached 70% of the time, against 11% when routed right** (1,161 resolved tickets). Misrouting is decided after intake, so no intake-time model can see it.

## Decision
- No SLA classifier ships. The ticket page shows the SLA clock (target, due time, elapsed) and the smoothed subcategory × priority breach rate, computed live by a parameterized query over `gold_incident_facts` (pseudo-count 5 toward the priority's rate, same formula as the evaluation).
- A **routing check** runs the routing model on the ticket text and compares it with the team the ticket went to first and the team that owns it now. For an open ticket, disagreement is the strongest breach signal available; for a resolved one it shows whether the model would have avoided the misroute.
- The evaluation script stays in `ml/sla/` so the comparison can be rerun when the data changes.

## Consequences
- Nothing new to train, register, load or monitor. The risk figure explains itself ("laptop tickets at P2 breached 59% of the time").
- Tickets opened before the routing model's training cutoff were in its training data; the UI says so next to the routing check.
- Revisit if real data adds signals available at intake (caller VIP status, CI criticality, queue depth), or to build a live model that updates as a ticket ages and changes hands.
