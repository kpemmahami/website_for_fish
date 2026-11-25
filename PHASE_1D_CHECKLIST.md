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
