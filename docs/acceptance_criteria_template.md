# Acceptance Criteria Template

Fill one of these per story **before** generating tests. Generation quality tracks
AC quality — a good AC in gives a good `.feature` out. Keep it concrete and
testable; avoid vague words ("works", "correctly", "properly").

Feed the completed block straight into `TestGeneratorAgent.gherkin(...)`.

---

## Story: <ID> — <one-line title>

**As a** <role>
**I want** <capability>
**So that** <business value>

### Priority (risk-based tiering — pick one)
- [ ] **P1** — automate this sprint (deterministic, high-value/high-risk flow)
- [ ] **P2** — smoke + manual this sprint, automate next
- [ ] **P3** — manual / backlog

### Type (pick one — drives which fixtures the steps use)
- [ ] API   → `api` + `api_ai`
- [ ] UI    → `ai_page`
- [ ] Email → `email` + `email_ai`

### Preconditions / test data
- <e.g. a registered user exists; base url; seed data>

### Acceptance criteria (Given/When/Then — one row per rule)
| # | Given (state) | When (action) | Then (expected result) |
|---|---------------|---------------|------------------------|
| 1 |               |               |                        |
| 2 |               |               |                        |

### Must cover
- [ ] Happy path
- [ ] At least one negative case (bad input / unauthorized / not found)
- [ ] One boundary case (empty, max length, limits)

### Out of scope / do NOT test
- <keeps the AI from inventing scenarios you don't want>

---

## Example (filled in)

## Story: OMNI-142 — Create user via API

**As a** new user
**I want** to register with name + email
**So that** I can access the app

### Priority: **P1**   ### Type: **API**

### Preconditions / test data
- Fresh email not already registered; `POST /users` available.

### Acceptance criteria
| # | Given | When | Then |
|---|-------|------|------|
| 1 | valid name + unique email | POST /users | 201 + body has `id`, `email` echoes input |
| 2 | email already registered | POST /users | 409 with a clear error message |
| 3 | empty name | POST /users | 422 validation error |

### Must cover: happy (row 1), negative (rows 2–3), boundary (empty name).
### Out of scope: password reset, email delivery (separate story).
