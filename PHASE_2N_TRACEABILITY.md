# Phase 2N — Supplementary financial operations

This supplement extends the existing master checklist and Phase 2A plan. Keep farmer loan origination active until the approved external-loan cutover. Keep existing servicing, production and financial history intact. The supplied Phase 2N attachment ends after the financing-cost bullets in §51. Coverage below follows the supplied sections.

## Requirements traceability

Paths in the evidence column identify existing source and tests. Existing endpoints and destinations are listed where relevant. Absence of a platform destination means that surface is pending.

| Requirements | Existing evidence and coverage | Remaining work and acceptance gate | Priority and dependencies |
|---|---|---|---|
| 2N §§1–5 · Audit, scope and navigation | Master checklist, Phase 2A audit. Web institution dashboard, approval/status, loan, staff, branches, collection and security views in frontend/src/main.tsx. Flutter institution selection and collections in mobile/lib/institution_workspace.dart. | Finish dedicated records and task pages, role-based visibility, responsive and installed Android acceptance. Route back, refresh and failed-save retention must pass. | Foundation and every workstream |
| §§6–9 · Posting, accounts, journals, ledger | Existing loan and deposit subledgers in backend/app/loan_servicing.py. New internal accounting primitives in backend/app/institution_accounting.py with migration 0044 and a focused backend test. | Configure tenant chart policy and account classifications, then add authorized posting integration, accounts and ledger, exports, reports and trial balance. Validate every posting map with independently calculated fixtures. No production source events post into this new ledger yet. | First accounting dependency, after policy and permissions |
| §§10–13 · Opening balances, journals, reversals and periods | Existing loan balances and source reference checks. No accounting opening-balance or period workflow wired. | Add guarded preview/import, verified reconciliation, maker-checker, immutable reversal references and period close/reopen with actor history. Opening entries stay separate from current cash. | Before rollout of accounting posting; coordinate with Phase 2C and 2G |
| §§14–18 · Teller, balancing, EOD, treasury and transfers | Daily collections and institution cash/recovery views. Existing mobile queue can capture offsite collections. | Add shift and custody accounting, expected versus counted cash, shortages, independent sign-off, lodgements, treasury accounts and transfer settlement. Reconcile cash and in-transit movement without counting income twice. | After posting and authorization controls |
| §§19–22, 27 · Savings, withdrawals, fees and excess amounts | Local excess and standalone deposit records in loan_servicing.py through 0041. Android Collections → Deposits and Settings → Recorded deposits. Backend and mobile tests cover scoping and retries. | Introduce authorized savings customer/product lifecycle, policy-based excess allocation, verified balance/holds, withdrawal and limits, interest/fees, reconciliation and reversals. Preserve existing deposit provenance. Customer liabilities stay separate from income. | After customer scope, accounting and payment verification |
| §§23–26, 28–30 · Loan product and risk controls | LoanAccount, schedules, appraisal and repayment fees in loan_servicing.py and lending.py. Loan servicing tests and Phase 2B branch restrictions. | Loan product versions, refinancing, early settlement, penalties/waivers, collateral and guarantors, credit history and provisioning. Model effective dates and verify distinct principal/interest/fee allocations and maker-checker actions. | Phase 2C–2H and approved accounting rules |
| §§31–36 · Statements, financial operations and budgets | Farmer expense, sales and reports modules. Institution portfolio totals exist; no institutional general-ledger statements published. | Add reconciled trial balance, balance sheet, income and cash-flow statements. Add AP/AR, assets and depreciation, budget, commitments and liquidity forecasts. Test as-of cutoffs and opening/closing balances. | After trusted ledger, periods and reconciliation |
| §§37–41 · Role dashboards, hierarchy, analytics, flags and limits | Institution/branch-scoped backend views, mobile drawer, portfolio and collection totals. Tests for roles, branch scope and concurrency. | Granular capabilities, limit chains, summaries from the authorized ledger, branch and officer data, alerts with review workflow, explainable drill-down and audit. Security flags must not authorize financial decisions. | Phase 2B, 2F, 2G and 2J |
| §§42–44 · Disputes, statements, receipts | Field receipts return a stable reference. Protected evidence and repayment history are available. | Add dispute lifecycle, authenticated statements, verified digital receipt status, reissuance and controlled reversals. Prevent exposure of borrower or balance data by searching public reference numbers. | After customer scope and verified posting |
| §§45–47 · Notifications and scheduled automation | daily_reminders.py has scheduled opted-in SMS and monthly mode. password_recovery.py has provider-dependent email. Tests use simulated senders. | Add persistent job and delivery status, idempotent scheduling and retries, secure links, reminders and authorization gates. Verify actual delivery and hosting persistence separately. Automation never approves or executes financial actions on its own. | After posted events and configured providers |
| §§48–49 · Offline operations and evidence | Flutter SQLite pending queue, scoped sync, camera preview, lens/torch controls and retry-safe repayment API. Private download authorization and camera tests/build checks. | Encrypt persisted customer/evidence data as appropriate, enforce device and staff revocation, save stale-balance timestamp, handle eligible recovery after access changes, and verify offline restart and playback on device. Add institution-approved alternate evidence, durable hosted storage and video retention. | After borrower assignments and approved storage |
| §§50–51 · Farmer finance and cost allocation | Farm expense, reporting, processing cost, sales and pricing modules. Farmer loan history and local recorded deposits view. Backend tests cover production and processing accounting. | Separate farmer finance pages and validate institutional events appear once. Reconcile loans, savings, finances received and inventory to source postings; extend allocation and costing acceptance across farm, unit, cycle, species, processing, packaging and distribution. | Joint 1C/1D, Phase 2 financed inputs and accounting rollout |

## Combined release order

1. Complete Phase 2B permission and borrower assignment work; stabilize the separate lending destinations.
2. Complete Phase 2C external intake and preserve the old application history; retire public loan creation at the cutover.
3. Complete authorized disbursement, servicing and recovery, with explicit transaction boundaries and deterministic financial tests.
4. Use approved chart-of-accounts mappings to connect verified source events to accounting. Complete period control, reconciliation, treasury, savings and adjustments before reporting balances as institutional books.
5. Complete loan product and risk workflows, evidence durability, farmer finance, reporting, scheduled automation and Flutter acceptance.
6. Verify all prior phases alongside 2N. Rehearse the full migration chain on populated isolated SQLite and PostgreSQL, review backups, and verify prior version rollback without dropping new financial data. After acceptance, apply the hosted migration and deploy the combined release once. Verify operational readiness and signed-in flows without creating real financial events solely for testing.

The requested week is a target. Track tested functionality separately from provider-dependent, browser/device and production acceptance. Phase 2N work adds migration 0044 but makes no hosted changes. No paid services or live payment processing are enabled.

## Local implementation evidence

Migration 0044 and the internal balanced-journal service passed three targeted tests on each isolated engine. Tests cover tenant-scoped accounts, balanced amounts, repeat and conflicting references, caller rollback, and existing loan servicing. No UI, public endpoint, live accounting activation or production migration was introduced. Account policy, posting mappings, reversals, immutable storage controls and authorized balances remain release gates.

### Chart of accounts

Verified institution owners can open #institution/accounting, list accounts, create accounts with tenant-unique codes and categories, and rename, deactivate or reactivate accounts. Add and edit forms replace the list while open. Changes are audited. GET and POST are available on /finance/institutions/{institution_id}/accounting/accounts, with PATCH on the account resource. The UI uses the existing 0044 schema. Account codes and categories stay stable after creation. Parent accounts, templates, delegated accountant roles, balances, journal views, approved posting maps and production activation remain open.

### Read-only accounting views

Verified institution owners can open Posted journals and Trial balance from the web institution dashboard. Journal list and detail APIs constrain results to the selected institution. The list API supports effective-date filters and pagination. Trial balance calculates net debit and credit per account from posted journals through the selected date, includes inactive accounts with historical activity, and reports an imbalance explicitly. Money is returned as fixed-precision GHS strings. The focused SQLite test checked dated totals, details, and cross-tenant denial. No migration beyond 0044 is required. Posting integrations, controlled reversals, financial periods, exports and hosted acceptance remain open.

The Trial balance page now downloads its loaded snapshot as CSV, including the effective cutoff, account codes and names, and debit and credit totals in GHS. The export uses the institution owner's existing authorized report data.

Posted journal details also export their loaded lines as CSV, including the journal ID, effective date, source reference and GHS debit and credit amounts.

The operator confirmed local signed-in browser checks for the Trial balance and Posted journals CSV downloads on 27 November 2026.

Posted journals supports inclusive effective-date filters. Changing either date returns to the first page, and returning from journal details preserves the filtered page.

Owners can select the last 7, 14, 30, 60 or 90 days through today in Ghana or enter both dates to download all matching journal lines across pages. A SQLite regression verified both date boundaries, exports larger than one page and cross-institution denial.

Source reference search matches partial references without regard to letter case. It applies to both the paginated list and the date-range CSV. SQLite tests verified matching journal IDs and literal wildcard characters.

The operator confirmed that Last 30 days downloaded a CSV with the expected column headers in a signed-in local browser on 27 November 2026. The selected range returned zero posted journal lines. The operator then confirmed a populated CSV for the fictional Local Test Bank journal CSV-CHECK-001. It included the GHS 125.00 debit to TEST-CASH and the matching credit to TEST-DEPOSITS under the same journal ID. The authenticated local API also confirmed that the combined date, source-reference and account-code filters returned that journal and both lines.

The account-code filter finds journals that posted to the specified account. The date-range CSV includes every line of each matching journal, preserving both sides of the entry. SQLite tests verified the combined filters, complete matching entries and empty results.

Account rows in Trial balance link to Posted journals filtered by account code and the report cutoff. Back to trial balance restores the cutoff. Frontend route checks verified the filters, cutoff restoration and institution matching. The operator confirmed that clicking TEST-CASH in the signed-in Local Test Bank portal showed journal CSV-CHECK-001.

### Monthly accounting period controls

Migration 0045 adds monthly institution period states. Owners can close/reopen from #institution/periods with an audited reason. Posting and month changes share a database lock. New journals effective in a closed month are rejected, while exact retries return their original journal. Reopened months accept new journals. Three focused SQLite accounting and servicing tests passed, and the web build succeeded. PostgreSQL acceptance, independent reopening authorization, financial close reconciliation and legacy-event posting integration remain release gates.
