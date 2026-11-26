# Phase 1D and 1D.1 interface audit and checklist

## Existing surfaces and proposed destinations

| Surface | Existing organization | Proposed destinations |
| --- | --- | --- |
| Platform administration and owner | Security setup, farmer queue, administrator directory, institution registration and institution decisions share one page. | Administration landing, account security, farmer approval and account directories, administrator creation and directory, institution landing, registration, decision queue, status directories, details and audit history. |
| Farmer and processor registration | Login and registration alternate on the same web and Flutter shells. Pending approval has its own screen. | Preserve pending access restriction. Add stable destinations for registration, recovery and status where useful. |
| Farm owner and farm manager | Farm and unit management have tabs. Registration, facility setup and existing records share workspaces. | Farm and unit directories, dedicated registration and edit pages, scoped management and evidence history. |
| Farm employee | Assigned units and permissions are scoped. Flutter has a dedicated assigned feeding screen. | Assigned work landing, due tasks where scheduled, record entry, and scoped history. Preserve owner-only controls. |
| Production | Activity selector exists. Feeding includes outlook, alerts and entry. Stocking includes readiness and history. Sampling, water quality, mortality and harvesting mix actions with records in places. | Keep production overview. Separate recording, schedules, recommendations, active or completed cycles, and filtered centralized history. Treat unscheduled activities as events. |
| Farmer finance, expenses and reports | Reports have dedicated destinations. Financing mixes lender discovery, requests, decisions and loan details. Expenses combine entry and record management. | Financing landing, request and loan details, expense entry and history, financial activities and analytics. |
| Sales, customers and invoices | Tabs share a workspace with collection, invoice and payment workflows. | Customer directory and creation, sales entry and history, invoice status views, receivables and payment history. |
| Feed inventory | Product and receipt entry share the inventory page with balances. | Product catalogue, registration, receipts, balances, low stock and stock history using the existing ledger. |
| Processing | Workspace tabs cover raw purchases, batches, packaging, inventory, sales, expenses and pricing. Several workflows share forms, selected records and reports. | Separate purchases, batch entry and status views, packaging entry and history, finished inventory, sales and costing reports. |
| Financial institution | Staff management, applications, appraisal, loan servicing and history share the lender workspace. | Separate staff directory and provisioning, application status views, appraisal, disbursement, repayment, borrower details and portfolio analytics. |
| Settings, alerts and evidence | Profile and communication settings share a page. Alerts are operational indicators. Activity history and evidence already have scoped access. | Split settings by task and reuse centralized history. Add notification status views only where persistent notification records support them. |
| Flutter | Farmer login and approval, overview, farms, operations, reports, account utilities and assigned feeding. Operations groups several farm actions. | Dedicated activity entry, stock and history pages for supported capabilities, with authorization and offline sync preserved. Web-only portal features require native implementation before mobile acceptance. |

## Implementation and verification

| Stage | Local implementation | Local verification | Hosted or device verification |
| --- | --- | --- | --- |
| Source audit and shared standard | Initial web and Flutter inventory documented | Source reviewed | Acceptance pending |
| Platform administration | Initial institution and farmer queue separation | Three frontend render tests passed. Full SQLite backend suite passed (73 tests). Browser workflow acceptance pending. | Pending |
| Farmer, staff, lending and processing | Pending | Pending | Pending |
| Flutter navigation parity | Pending | Pending | Pending |
| Regression, accessibility, route protection and viewport checks | Pending comprehensive acceptance | Pending | Pending |

## Initial acceptance scenario

Sign in as a platform administrator. Open the farmer approval queue from the administration landing. Open institution registration and verify only the registration form is displayed. Submit a test institution on an isolated database, verify it appears in the pending queue, and approve it from its review page. Check the approved directory and counts. Reload a dedicated destination, use browser Back, and repeat navigation at phone width. As a non-administrator, confirm that the administrator destination and protected API remain unavailable.

Run later portal acceptance against isolated records. Verify real Android behavior separately from responsive browser checks. Publish only after approval. Roll back the interface by redeploying the previous verified commit if needed.

## First implementation routes

The single Platform Administration screen now links to `#admin/farmers`, `#admin/administrators`, `#admin/security` and `#admin/institutions`. Institution routes add `/register`, `/pending`, `/verified`, `/rejected`, `/suspended`, `/all`, `/review/{id}` and `/details/{id}` under that destination. The pending destination includes under-review and more-information-required records. Suspension and reactivation controls retain the existing owner restriction.

The institution list uses client-side search, sorting and pagination over the existing administrator API. Institution approval history is available at `#admin/institutions/history` and `#admin/institutions/history/{id}`. Institution editing, date filters and server-side directory filtering remain pending. Farmer management links to separate pending and approved account directories. Other farmer statuses, account details, administrator creation and activity separation remain pending. The existing statuses are authoritative and this slice requires no migration.

## Phase 1D extension — field loan collections

| Deliverable | Acceptance criteria |
| --- | --- |
| Collections workspace and access | Financial institution staff with collection permissions can open Collections on web and Flutter. Search the institution's authorized borrowers by name or account reference, choose the customer and select an eligible loan before entering a payment. Identify the correct loan when a borrower has several. Keep institution and staff scopes enforced at every API. |
| Record a collection | In the customer view, select Collect loan repayment, enter the amount in GHS and confirm the customer, loan account number and amount. Capture a short video with consent in which the collector states the amount received and the customer acknowledges it. Support an authorized alternative evidence workflow where consent is declined. Keep consent and evidence access auditable. |
| Offline Flutter collection | With an authorized customer list previously loaded, capture the payment and video offline. Securely queue them under the signed-in collector and institution. Show pending items and a manual Sync button. Preserve pending evidence across app restarts and show individual failures with retry. Revalidate access and loan eligibility at sync. |
| Posting and reconciliation | Post through the existing repayment ledger, using a unique client collection reference to make retries safe. Track captured time and posted time separately. Show unsynced entries as pending on the collecting device. Handle conflicts and changed loan balances without duplicate posting. Provide a receipt reference after confirmation. |
| Daily collections | Collections opens a day view showing amount, customer name, loan account number and protected video access. Use Ghana business dates for grouping. Show posted totals and permit authorized review by collector and date. Keep video streaming on demand. |
| Monthly borrower payment reminders | Send one reminder per eligible borrower per month using the existing notification preferences and provider controls. Use the current repayment schedule and suppress reminders for paid or closed loans. Keep the delivery schedule and channel configurable and test duplicate prevention before enabling live delivery. |
| Release checks | Test role and institution isolation, offline capture and restart, manual sync, repeated sync after a network timeout, concurrent repayments, exact ledger totals, video authorization and daily/monthly rollover. Test native capture and sync on an Android device before production rollout. |

Use the existing loan repayment ledger and collections permissions. The Flutter evidence recorder and offline queue provide patterns to adapt. This extension is scoped to repayments on disbursed loans. Deposit-taking would require a separate product and ledger. Initial online web implementation provides an institution-scoped active-loan directory, daily posted repayment history, and an entry point to evidence-backed repayment recording. Two servicing tests and the frontend production build passed. Offline Flutter capture and sync, retry acknowledgement, alternate evidence, monthly borrower notifications, and end-to-end acceptance remain pending. No migration is needed for the online changes.

### Disbursements and recovery

The web lender dashboard opens a dedicated Disbursements page. It lists borrowers with posted disbursements, including partially disbursed loans. Staff with disbursement permission can select an eligible loan and record the payout with the existing evidence workflow. The page shows per-loan and institution-wide disbursement and recovery totals. Collections shows daily posted repayments separately from cumulative portfolio recovery.

Total recovered includes principal, interest and fees. The principal recovery rate divides principal repaid by principal disbursed and is unavailable before a disbursement. Reports aggregate the existing ledgers without duplicating transactions. The frontend production build and two loan servicing tests passed locally. The tests cover institution access, multiple disbursements and repayments, and the distinction between cash recovered and principal recovery. Hosted and Flutter acceptance remain pending.

Field repayment retry support is implemented locally. The authenticated endpoint uses a client-generated collection ID scoped to the loan and matches the original collector, amount, payment date and evidence before acknowledging a replay. A replay can return the original receipt after the loan is fully repaid. The online Collections form uses this endpoint and retries identical video uploads within the existing capture window. No schema change is needed. Native offline queue integration is implemented. Extended offline evidence handling remains pending. Concurrent same-collection replay passed on disposable PostgreSQL and SQLite.

### Monthly borrower SMS

Monthly mode checks daily at the existing Ghana-time SMS scheduler hour. It sends at most one monthly reminder to each opted-in borrower with a verified phone and an unpaid active-loan installment due by month-end. The message directs the borrower to their repayment schedule. Existing installment-based delivery remains the default. Select monthly delivery with `AQUAFARM_LOAN_REMINDER_MODE=monthly` when `AQUAFARM_LOAN_REMINDERS_ENABLED` and the existing Hubtel configuration are enabled. Tests use a fake SMS sender. Hosted activation and delivery verification are tracked separately.

### Flutter institution workspace

Flutter now supports the institution login endpoint, SMS sign-in verification and initial password replacement. Verified institution memberships with collection access can open today's posted collections and search active borrower loan accounts. Flutter collection entry now captures a consented 15-second video with audio, queues repayments in app-private storage, and manually syncs by backend, staff account and institution. Android can open protected videos from the daily list. Customer results are cached in memory for the current screen. Queued payments persist across restarts and can be retried after reconnecting and signing in. New evidence uploads still use the existing 24-hour window. Native camera, video playback and restart acceptance with an isolated institution remain pending before release.

### Field collections acceptance evidence

Two simultaneous submissions of the same collection returned the same receipt and created exactly one daily ledger item. The authorized collector retrieved the attached fixture bytes, and an unrelated account was denied. Both loan-servicing tests passed against SQLite and disposable loopback PostgreSQL after migrating from an empty schema. The emulator has the Android test build installed. Real camera and audio, offline restart and Android playback still require device acceptance with an isolated loan.

### Collection types and customer balances

- [ ] Add a distinct deposit workflow for authorized institutions and a customer balance view for farmers. Record deposits as customer funds in a separate ledger with a receipt, institution and customer scope, audit trail, and reconciliation status.
- [ ] Apply a loan collection up to its outstanding balance and record any excess as a separate deposit only when a supported deposit account is selected and the institution and customer confirm the split. Save both entries atomically and retry using one stable collection reference. Smaller repayments continue using the existing ledger.
- [ ] Add separate offline queue support and test deposits, overpayments, refunds or reversals, permission checks, balance accuracy, and duplicate retries. Do not count deposits in loan principal recovery.

Local implementation now atomically splits an active-loan field collection into repayment and recorded excess deposit. Daily collections show the split and farmers can view their recorded excess by institution. Revision 0040 is required before releasing the backend. Standalone deposits, withdrawals/reversals, reconciled account balances, and production acceptance remain open.

Standalone deposits are implemented for existing institution customers discoverable through active or repaid loans. Flutter offers separate Loans and Deposits views. Standalone deposits use the same consent, private video evidence and offline retry workflow, affect the recorded customer deposit total, and leave loan recovery unchanged. Backend revision 0041 and Android queue schema version 3 are required. Customer enrollment without a prior loan, reconciliation and reversals remain open.
