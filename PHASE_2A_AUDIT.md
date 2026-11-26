# Phase 2A — Financial institution audit and implementation plan

## Scope and baseline

Phase 2 replaces public loan origination with institution-controlled external loan intake. Keep existing applications, consent snapshots, PDFs, offers, schedules, evidence and transactions accessible to authorized users. Once external intake is available, retire the farmer request UI and disable the corresponding write routes on the server. Continue to support existing offers and servicing. Confirm the in-flight application policy at cutover.

The repository uses FastAPI, SQLAlchemy and Alembic, React/Vite for web, and Flutter for Android. SQLite remains a development target. The project has used Neon PostgreSQL behind Render, despite the specification naming Supabase. Confirm the intended hosted database and storage provider before any production change. The local Alembic head is 0041_standalone_deposits. The last confirmed hosted revision from prior release evidence is 0039_staff_feeding_access. No hosted database inspection or migration was performed in this audit.

The current development working tree already contains test, ledger, camera and deposit changes, including migrations 0040 and 0041. Preserve those changes. Before Phase 2B, capture the approved baseline and create a dedicated Phase 2 branch. Keep its changes separate from unfinished Phase 1 work.

## Gap analysis

| Specification | Existing components | Open work and acceptance criteria |
| --- | --- | --- |
| §§3, 10–11 · External intake and approval | Farmer application, authorized institution appraisal, consent snapshot, approved offer and PDF. LoanAccount requires an application. | Institution-controlled intake and authorized farmer/business linkage, manual and validated batch import, institution-scoped unique external references, preview, provenance, approval history and in-flight cutover. Preserve historical GETs and PDFs. Imported active balances require audited opening entries distinct from period cash disbursements. |
| §§5–9 · Portal, branches and permissions | Responsive workspace, staff creation/access controls, verified institution membership and role checks. | Dedicated task/list/detail routes, branch management, configurable roles, branch and borrower scope, maker-checker, dashboard period and dimensions. Backend enforces every branch and borrower filter, including export and evidence. |
| §§12–16 · Disbursements and financed inputs | Manual full/partial disbursements, references, cap, video evidence, and audit. Farm inventory, stocking, processing and finance exist. | Add preparation, reservations, independent authorization, confirmed external settlement, failure and reversal. Add funding versus physical delivery, milestones, partial delivery, supplier invoices, borrower acknowledgment and idempotent links to inventory/assets. |
| §§17–18, 29–30, 41–42 · Schedules, balances and risk | Flat interest, monthly/quarterly/harvest/custom schedules, principal/interest/fees, overdue computation and posted recovery totals. | Version terms and schedules, support additional frequencies and approved interest methods, use effective-date allocations, arrears aging and PAR. Add controlled adjustment, reversals, restructuring, write-off and settlement. Specify rules for partially funded facilities, rounding and early settlement before implementation. |
| §§19–28 · Recovery, borrower profiles and evidence | Institution portfolio, active customer search, daily collections, retry-safe field collection, protected video, repayment history, Flutter queue. | Dedicated recovery dashboard and due/overdue/harvest queues, borrower profiles and statements, verification before posting where required, assignments, visits, promises, officer targets and roles, and alternative evidence. Separate recording and receipt, approval, posting and reconciliation. |
| §§31–38 · Farm intelligence, harvest and groups | Production cycle, stocking, sampling, mortality, feed, water quality, forecast, sales and processing data. Existing loan appraisal uses a snapshot. | Granular and revocable production sharing, financed farm/cycle allocations, certainty and data-age labels, forecast scenarios, affordability and risks. Add lender-authorized harvest and sale-linked recovery and group liability/allocations without double counting. A delayed harvest alone does not create delinquency. |
| §§39–40, 43–45, 48–49 · Reconciliation, cross-portal entries and alerts | Ledger entries, audit, farmer loan transactions, reminders, and local excess and standalone deposit records. | Cash custody and lodgements, matching and exception queues, approval and reversals, immutable audit, status transitions, verified receipt notifications and unified history with drill-down. Keep cash events distinct from loan liability, income, inventory and borrower deposits. |
| §§46–47 · Reports and charts | Portfolio totals, daily collections, transaction history and existing report/PDF infrastructure. | Date- and dimension-filtered reports, PDF/Excel access controls, trend series, drill-down and reconciliation to source entries. Carry historical opening balances forward separately. |
| §§50–55 · Security, storage and integrity | Tenant-scoped queries, administrator safeguards, role checks, private file download endpoints, PostgreSQL/SQLite and idempotent collections. | Maker-checker and reauthentication, durable private storage, retention and access audits, institution/branch/borrower-scoped access, policy-based posting and reversal. Initial release records externally completed events. Any live provider integration is a later approved release. |
| §§56–57 · Mobile and testing | Flutter institution login, customer search, capture and manual sync. Automated loan, security and Flutter coverage. | Dedicated field assignment, visits, promises, borrower histories and alerts. Exercise offline capture, restarting, failure/retry, duplicate prevention and protected playback on Android, separately from mobile web. |

## Prioritized release risks

1. **Over-disbursement under concurrency.** The current disbursement endpoint reads loan totals before inserting and does not take the repayment path's write lock. Concurrent requests with different references can both pass the cap check. Lock or reserve against the same facility within the posting transaction, handle duplicate references consistently, and test competing PostgreSQL writes.
2. **External cutover integrity.** The current facility constructor expects an approved internal application. Add an explicit external source and audited opening-balance path. Avoid fabricated legacy applications or disbursement rows. Reconcile imported principal, interest, fees and historical dates against source statements before committing.
3. **Authorization granularity.** Institution membership is broadly scoped, and repayment collectors can view institution-wide eligible borrowers. Add deny-by-default branch and borrower assignment scoping before exposing production intelligence or recovery dashboards. Keep discoverability, exports and evidence access under the same scope rules.
4. **Evidence durability.** Evidence defaults to local files. Verify hosted storage and persistence first. Add an approved private, durable storage adapter with controlled access and checksum verification. Validate retention and clip consent, add alternate acknowledgment, and verify restart persistence.
5. **Financial classification and reconciliation.** Cash received, verification, posting, lodgement, settlement and reconciliation need distinct states. Prior deposits remain separate from repayment and principal recovery. Reconcile opening balances and confirmed payments as of the selected date, keeping late posts and backdated entries auditable.
6. **Reporting conventions.** Document Ghana business dates, rounding, allocation order, DPD, and eligible PAR numerator and denominator. Present period flows separately from balances as of a date. Close approval and repayment ledger workflows on transactional success.
7. **Production and communication dependencies.** Confirm actual email/SMS delivery settings, provider availability, consent and deployment evidence. Review applicable requirements with the institution before enabling related payment operations.

## Implementation sequence and release gates

- [ ] **2B · Portal foundation.** Ship dedicated institution routes, navigation and role-scoped dashboard skeleton. Define branch and assignment ownership and permissions, add compatible schema only as needed, and test cross-scope denial. Prioritize disbursement integrity regression before broader exposure.
- [ ] **2C · External loans.** Add validated draft/import preview, external provenance, approval and import replay protections. Implement opening balance reconciliation separately. Preserve historical loans/PDFs. Disable farmer application entry and POST at the agreed cutover with pending-record rules documented.
- [ ] **2D · Disbursement.** Implement atomic reservations, maker-checker, cash settlement recording, input financing, milestones and deduplicated delivery-to-inventory links.
- [ ] **2E · Servicing.** Implement versioned schedules, allocations and as-of balances, arrears, restructures, settlement and reversal. Validate each financial calculation against independently calculated fixtures.
- [ ] **2F · Recovery.** Implement assignments, borrower pages, due and delinquent queues, visit and promise workflows, evidence-backed collection and officer reporting.
- [ ] **2G · Treasury.** Implement verification, cash custody and lodgements, settlement matching and reconciliation, adjustments, audit and protection against double posting.
- [ ] **2H · Intelligence.** Add funded cycle scope, authorized data access, source freshness, harvest forecast and repayment-capacity analysis.
- [ ] **2I · Harvest and sales-linked recovery.** Add separately authorized contractual schedules and proceeds allocations. Verify no repeated revenue assignment or cash recognition.
- [ ] **2J · Reports.** Add portfolio, disbursement, recovery, arrears/PAR, reconciliation, and farm production reports with authorized exports and ledger tie-outs.
- [ ] **2K · Mobile.** Implement native officer workflows with offline pending status and retry safety, plus responsive web verification.
- [ ] **2L · Acceptance.** Run migration and regression on isolated SQLite/PostgreSQL, signed-in browser checks, Android camera and sync, concurrency and permission adversarial tests. Record hosted verification separately and request release authorization.

## Backup and rollback

Before a hosted change, confirm the database and migration revision, record row counts and reconciliation totals, and confirm a recoverable backup of database and private media. Prefer additive migrations with backfill checks. Verify the upgrade on a disposable PostgreSQL instance. Application rollback should preserve additive tables, imported financial records and evidence. Rehearse rollback with the phased intake cutover and writer compatibility in mind.

Existing relevant settings include DATABASE_URL, SECRET_KEY, CORS_ORIGINS, AQUAFARM_EVIDENCE_DIR, the AQUAFARM_RECOVERY_* settings, HUBTEL_* settings, and the loan reminder mode. No new environment variables are introduced in Phase 2A. No schema, APIs, routes, permissions or financial calculations are changed by this stage.

## Phase 2A verification

SQLite migrations ran through 0041 against an isolated test database and the full backend baseline passed 75 tests with one dependency deprecation warning. No production migration, authenticated hosted acceptance, or Phase 2 application changes were performed.

## Phase 2B progress

Disbursement posting now locks the loan before checking the remaining approval and refreshing its status. A regression starts two competing GHS 4,000 disbursements against GHS 6,000 remaining. One posts, the other is rejected, and the final eligible GHS 2,000 tranche can still post. Both servicing tests passed on isolated SQLite and PostgreSQL after migrating to 0041. This change requires no new schema. Institution routes, branch scoping, granular roles and maker-checker authorization remain open. No production deployment.

### Phase 2B institution workspaces and branch directory

Web navigation now separates pending, approved and rejected applications, the loan portfolio, institution staff, branches and account security. Appraisal details replace the selected status list while open. The staff creation form has a separate view from the staff list. Existing disbursement and collection destinations remain available. Missing portfolio figures show an unavailable state.

Migration 0042 adds the institution branch directory. Verified institution owners can list, create, edit and deactivate their own branches. Codes are unique within each institution and branch changes are audited. Routes use GET and POST on /finance/institutions/{institution_id}/branches and PATCH on that resource with a branch ID. The web destination is #institution/branches. This directory does not assign staff or loans to branches. Granular roles, branch and borrower assignment enforcement, and independent authorization remain open. The farmer loan application remains available during the transition to external intake.

Local web acceptance still needs a signed-in test of browser Back, reload, application status transitions, empty views and branch edits at desktop and phone widths. No production changes.

Branch and servicing checks passed on SQLite and disposable PostgreSQL after migrating through 0042 (four tests each). Three existing web component tests and the production build passed. Vite reported a bundle-size warning. Authenticated browser navigation and device acceptance remain to be verified.

### Phase 2B branch assignments

Migration 0043 adds optional branch assignments for staff and loan applications. An authorized institution owner can set or clear staff assignments from Institution staff and set the processing branch on an existing application. A loan inherits its application's scope. Backend checks constrain branch-assigned staff on appraisal lists, lookup, direct access, reports/evidence, portfolio, disbursement and collection lists and writes. Inactive branches deny assigned staff. Existing unassigned staff retain institution-wide behavior within their existing role, and owners retain institution-wide access. New branch-specific roles and borrower assignments remain open.

Four targeted backend checks passed on each isolated engine, including denial for out-of-branch loan details, evidence and collections, then restoration for a matching assignment and denial after branch deactivation. A populated SQLite copy upgraded to 0043 with unchanged counts and valid foreign keys. The web build passed with the bundle-size warning. Signed-in browser acceptance, maker-checker, and external intake remain open. Batch the hosted migration and deployment with the final approved release.

### Independent disbursement review

Migration 0046 adds the institution policy and review queue. An owner can enable approval from Institution Portal → Disbursement approvals. An authorized non-owner officer prepares the external payout record and its video. Pending amounts reserve approved capacity. A different authorized owner verifies the external payout and approves posting, or rejects it and releases capacity. Direct posting is blocked while the policy is enabled. Existing institutions start with it disabled. Loan, evidence and institution access checks apply before posting, and audit events record both parties and the decision reason.

The workflow records externally settled transactions. The servicing regression passed on SQLite and PostgreSQL with two simultaneous approval submissions returning the same decision and the disbursement total increasing once. Operator authorization limits, delegated checker roles, approved-but-unsettled states, provider integration and signed-in browser acceptance remain open. The [0045–0046 Neon script](neon_0045_to_0046.sql) is available for databases at revision 0045.
