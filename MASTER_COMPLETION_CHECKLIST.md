# AquaFarm Manager Ghana master completion checklist

Audit date: 26 November 2026 (Africa/Accra). This checklist consolidates the available project specifications, their follow-up requests and the Phase 1B–1D checklists. The Render log attachment is diagnostic evidence. The two loan download specifications are tracked together. Existing functionality is identified from repository code, tests and release history. Completion requires evidence for each requested workflow on its applicable platform.

## Prompt and evidence inventory

| Prompt or request | Evidence of existing work | Open work or verification |
| --- | --- | --- |
| Master production specification and live dashboard integrity | Dashboard, operations, production intelligence, forecasting and production alerts modules. Dashboard, operations and forecasting tests. | Verify all stocking capacity, water quality, harvest rescheduling and cross-module updates against the original acceptance scenarios. Confirm critical water-quality SMS coverage and real delivery. |
| Production navigation, dedicated analytics and multi-unit dashboard | Production subviews, dashboard, farm report views and centralized activity routes. | Complete Phase 1D separation of entry, history and analytics. Verify selected units consistently constrain charts, summaries, recommendations and exports on desktop and phones. |
| Daily and session-based feeding, time-window alerts, frequency change and seven-day outlook | Feeding sessions, recommendation approval, schedule and outlook modules. Automated tests and native assigned feeding entry exist. | Finish authorized scheduled feeding for staff and web entry. Test schedule switch from four to three to two sessions, existing plans, inventory changes, missed windows and inactive cycles on a device. |
| Friendly API errors and centralized diagnostics | Shared web API errors and backend request correlation. | Verify common forms across portals, raw-error masking, recovery 503 messaging and consistent mobile feedback. |
| Central farm history and evidence library | Activity history aggregation, filters, details, export and evidence authorization. Automated activity and evidence tests. | Verify coverage, navigation from each operation, multiple detail selection, media retention and isolation, and remove remaining embedded history. |
| Sales, invoices, customers, payments and receipts | Sales API and reporting, invoice generation, customer, payment and inventory integration. | Complete dedicated entry and status views and verify invoice/receipt downloads, balances, partial and canceled transactions, and mobile behavior. |
| Expense ledger, receipt picker, cash analytics and financial reports | Farm expense and report modules with evidence and test coverage. | Check receipt picker and attachment flows on phones, complete separate entry/history pages, and reconcile cash versus accrual, sale receipts and loan financing without duplicate totals. |
| Fish selling price advisor | Pricing advisor, automated costing and tests. | Verify assumptions and available-data states, harvested versus projected costs, report export, and integration with actual sales. |
| Processing, packaging, sales and independent processors | Processing workspace and backend include raw lots, harvest allocations, batches, packaging, shared costs, by-product credits, sales and reports. | Independently replay the 100 kg purchase and 60 kg smoking scenario plus an integrated mixed-source scenario. Verify stock, packaging labels, quality controls, customer payment, central expense recognition, and separate/consolidated profitability coverage. Finish page separation. |
| Institution portal redesign, bank staff registration and loan fees | Controlled institution provisioning, scoped staff creation and institution lending workspace. Independent fee fields and loan servicing tests. | Verify every staff role and staff lifecycle change. Confirm interest, insurance and processing remain separate through quote, offer, PDF, repayment and report. Finish dedicated lifecycle pages. |
| Farmer loan application, assessment, disbursement and repayment | Loan application, appraisal PDF, servicing, offers, evidence, consent, repayment schedule and portfolio reports. | Verify all loan state transitions, history, borrowing consent and tenant access in hosted acceptance. Assess unsupported requested states against actual lifecycle before any schema extension. |
| Professional appraisal preview and loan application PDF download (both download prompts) | Appraisal report component and PDF generator. | Replay authenticated farmer and lender preview/download with a representative long report. Check branding, page breaks, embedded media links and restricted access. |
| Super Admin, delegated permissions, default test accounts, Phase 1B and portal login follow-ups | Platform Owner guard, controlled registration, pending queues, hashed recovery codes, local seed and initial phone verification. Pending dashboard deployed. | Live email recovery setup and delivery, complete privileged recovery and role controls, secure lifecycle notifications, farm staff onboarding and wider operation permissions. Test all sign-in portals with isolated accounts. |
| GitHub/Render deployment, PostgreSQL support, migrations and registration/CORS incident | Neon-backed rollout, Alembic through reported 0039, Render readiness, backend configuration and registration tests. Last approval release ea9f35c verified publicly. | Run current revision and regression against disposable PostgreSQL. Verify signed-in hosted workflows and migration health before release. Track mail settings and release artifacts separately. |
| Phase 1C mobile usability and activities | Mobile web drawer and headless acceptance, centralized history, feeding tools and cash reporting. | Finish catalogue, inventory, finance classification, camera usability and durable private evidence acceptance. Device tests remain open. |
| Phase 1D and 1D.1 interface and status separation | Separate institution registration, status lists, review, approval history, administrator activation and farmer queues. Existing history/report destinations. | Complete remaining administrator and farmer directories, staff, lending, sales, processing, production, inventory and settings pages. Add navigation and failed-save acceptance. |
| Field collections, disbursements, recovery percentage and monthly reminders | Online web release, retry-safe field repayments, Android debug workflow with private video capture, durable pending queue and manual sync. Monthly SMS mode tested with a fake sender. | Test native capture, loss of network, restart, playback and verified ledger posting with isolated accounts. Customer search cache currently lasts for the screen and new evidence uploads have a 24-hour limit. Concurrent same-collection retries passed against disposable PostgreSQL. Verify durable hosted media and live monthly reminder delivery. |
| Temporary test verification code | Local-only six-digit test SMS option in the working tree, with focused guard tests. | Verify on isolated local farmer and institution flows. Shared hosted verification uses actual security checks. |

## Work queue

- [ ] **1. Restore live recovery and verify privileged access.** Configure a verified Resend sender in Render, test delivery and session revocation across portals, verify Hubtel and activation delivery, then complete lost authenticator and lost phone workflows, required privileged MFA rollout, and granular admin roles.
- [ ] **2. Finish Android field collections acceptance.** Run camera/audio, offline capture, restart, retry, sync, exactly-once ledger reconciliation and protected playback on an isolated loan. Verify media survives deployment, and define the offline age and restart behavior before release. Test monthly delivery with an eligible opted-in borrower.
- [ ] **Add customer deposits and excess-loan allocations.** Keep customer funds separate from the repayment ledger. Implement consented allocation, customer balances, receipts, idempotency and reconciliation. See the Phase 1D checklist.
- [ ] **3. Finish farm staff workflows.** Add dedicated onboarding and lifecycle, scheduled and web feeding entry, scoped operational roles and authorization checks. Run attribution and cross-farm denial tests.
- [ ] **4. Complete Phase 1C operational simplification.** Split feed product registration from stock receipts and balances. Verify catalogue references, alerts and feed calculations. Reconcile financial classifications, expand history coverage and verify supported camera controls and device storage.
- [ ] **5. Complete Phase 1D and 1D.1 pages.** Finish owner, farmer, staff, institution, lending, production, sales, finance, inventory, processing and settings status views. Verify deep links, refresh, Back, accessibility, role isolation and unsaved/failed form behavior.
- [ ] **6. Verify earlier business specifications.** Replay the inventory table above with fictional data. Record expected and actual calculations, report artifacts, permissions and remaining defects for each workflow.
- [ ] **7. Prepare staged release.** Verify disposable PostgreSQL, full regression and signed-in browser/device acceptance. Record local implementation, hosted verification, migration requirements and rollback separately for each release.

## Related checks

- [Phase 1B authentication and staff](PHASE_1B_CHECKLIST.md)
- [Phase 1C mobile web and operations](PHASE_1C_CHECKLIST.md)
- [Phase 1D interface and collections](PHASE_1D_CHECKLIST.md)

## Audit verification

- Local SQLite regression passed 74 tests. The backend suite reported one dependency deprecation warning.
- Web passed three component tests and the production build. Vite reported a bundle-size warning.
- Flutter analysis found no issues and all seven tests passed.
- Render readiness returned HTTP 200. A recovery probe using a reserved example address returned HTTP 503, confirming the live sender configuration still blocks the first work item.
- Disposable PostgreSQL, signed-in hosted workflows, provider delivery and physical-device acceptance remain separate verification items.

### Field collections acceptance evidence

Two simultaneous submissions of the same collection returned the same receipt and created exactly one daily ledger item. The authorized collector retrieved the attached fixture bytes, and an unrelated account was denied. Both loan-servicing tests passed against SQLite and disposable loopback PostgreSQL after migrating from an empty schema. The emulator has the Android test build installed. Real camera and audio, offline restart and Android playback still require device acceptance with an isolated loan.

## Phase 2 financial institution servicing

See the [Phase 2A audit and implementation plan](PHASE_2A_AUDIT.md) for the external loan cutover, risk register and stage gates. Phase 2A adds no runtime changes.

Phase 2N is included in the combined program. See the [supplementary traceability matrix](PHASE_2N_TRACEABILITY.md) for dependencies, acceptance gates and accounting progress. Batch the hosted migration and deployment after the combined release passes.

## Combined release checkpoint

- The current branch includes monthly accounting periods (0045), independent review for externally settled disbursements (0046), and a public demo with fictional records. Independent review is opt-in per institution. The broader authorization work remains open.
- All 77 backend tests passed on each of isolated SQLite and disposable loopback PostgreSQL after migrating empty databases through 0046. Coverage includes disbursement reservation, approval and rejection, and the guard on local-only SMS verification. All eight web tests passed. The production build passed with `npm run build -- --configLoader runner` and reported a bundle-size warning.
- The [Neon 0045–0046 script](neon_0045_to_0046.sql) preserved an existing institution, owner and closed accounting period in a disposable PostgreSQL rehearsal. Approval defaulted to disabled, and rerunning the script rejected the unexpected revision without modifying the fixture. The operator confirmed that Neon reports `0046_disbursement_reviews` and contains both schema changes. Reconciliation of the populated hosted database and signed-in acceptance remain open.
- Flutter analysis found no issues and all eight Flutter tests passed on the current branch. Earlier verification includes a populated SQLite upgrade from 0041 to 0044 that preserved account, farm and loan record counts, disbursement and repayment totals, and foreign keys.

Release remains on hold. External loan intake and cutover, broader independent authorization, verified accounting integration, treasury and reconciliation, savings operations and reporting are incomplete. Signed-in browser and device acceptance and production email and evidence verification are pending.
