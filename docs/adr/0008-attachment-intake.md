# 0008: Read ticket attachments into reviewable facts, not straight into the ticket

**Status:** Accepted, 2026-09-30

## Context
Callers often describe a problem badly and attach the evidence: a screenshot of an error dialog, a photo of a handheld's screen, a customer's email saved as a PDF. The text a dispatcher types rarely carries the exact error code, device tag or start time that routing and search need. This is the intake stage of the lifecycle, and "document understanding" in the role description.

## Decision
- **`POST /api/triage/attachments`** takes a multipart form with 1-3 files of up to 5 MB each, plus whatever ticket text exists so far. It makes one structured Claude Opus 5.5 call (low effort) with the files as image or PDF content blocks placed before the text. The call returns error text verbatim, device or asset, application, site (from a fixed list, or blank), scope, start time, a suggested title and a description addition.
- **The dispatcher decides.** The facts appear on a review card. **Add to ticket & triage** keeps any title the dispatcher typed, appends the addition to the description, and runs the existing routing, search and agent on the enriched text. Nothing downstream needed to change.
- **Don't guess.** The prompt forbids inferring a site, device or cause that isn't visible. In testing, the model left the site blank for a Memphis-looking asset tag instead of guessing.
- **Sensitive data is named, not copied.** The model lists the kinds it saw (email address, phone number, person name). Those values stay out of every field, and the UI warns the dispatcher not to paste them.
- **Upload handling:**
  - The type is decided by the file's leading bytes: PNG, JPEG, GIF, WebP or PDF. A renamed executable is refused, and the declared content type is ignored.
  - `Content-Length` is checked before the body is parsed, so oversized uploads are never spooled.
  - Files live in memory for the request only. They are not stored or logged; telemetry records counts, types and sizes.
  - Reads are rate-limited like the other AI calls.
- Three fictional sample attachments (`tools/samples/make_samples.py`) make the feature demoable in one click. The customer email carries a fake email address and 555 number on purpose.

## Consequences
- Measured on the samples: 6-9 s and 1.3-2¢ per read. The enriched text routed all three to the right team, with the right top KB article.
- Attachment text is untrusted input. The model is told to treat it as data. Its output is constrained to a schema and only reaches the ticket after a person accepts it, but a crafted image could still steer the suggested wording, which is one more reason the dispatcher reviews it.
- Attachments aren't kept, so a ticket page can't show them later. A real deployment would store them with the ticket, in ServiceNow for instance, and pass references instead.
