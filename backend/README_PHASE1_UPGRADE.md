# AquaFarm Manager Ghana — Phase 1 foundation upgrade

## Scope
Preserves the original authentication and farm API. Adds farm GPS, production
units, owner-scoped audit history, soft-archiving, production cycles, daily
operations, feed inventory and reconciliation, private video evidence, loan
applications, and manual loan servicing. This remains a development system, not a
production-certified aquaculture or lending platform.

## Windows PowerShell installation
From the `backend` directory, stop Uvicorn and **back up your existing `aquafarm.db`**.
Do not replace an existing database with the ZIP (none is included).

```powershell
cd "C:\Users\02433\Desktop\AquaFarmManagement System\AquaFarm_Manager_Ghana_Phase1_Foundation_Upgrade\aquafarm-manager\backend"
Copy-Item .\aquafarm.db .\aquafarm.db.backup -ErrorAction SilentlyContinue
& "C:\Users\02433\Desktop\AquaFarmManagement System\AquaFarm_Manager_Ghana_Phase1_Foundation_Upgrade\.venv\Scripts\python.exe" -m pip install -r requirements.txt
$env:SECRET_KEY = "your-existing-secret-key-at-least-32-characters"
& "C:\Users\02433\Desktop\AquaFarmManagement System\AquaFarm_Manager_Ghana_Phase1_Foundation_Upgrade\.venv\Scripts\python.exe" -m alembic upgrade head
& "C:\Users\02433\Desktop\AquaFarmManagement System\AquaFarm_Manager_Ghana_Phase1_Foundation_Upgrade\.venv\Scripts\python.exe" -m pytest -q
& "C:\Users\02433\Desktop\AquaFarmManagement System\AquaFarm_Manager_Ghana_Phase1_Foundation_Upgrade\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload
```

If `.venv` lives elsewhere, use your working Python interpreter instead.
Keep your **existing** SECRET_KEY, or previously issued tokens will be invalid.
The migration uses DATABASE_URL if set, otherwise `sqlite:///./aquafarm.db`.
Run commands in the `backend` folder so SQLite resolves the expected path.
Revision `0012_daily_record_sms_reminders` adds optional farmer phone numbers and
SMS opt-in preferences plus a deduplicated reminder log. Revision
`0013_phase_one_completion` adds evidence metadata and challenges, stocking
supplier/harvest details, fish transfers, supervisor assignments, corrections,
inventory reconciliation, treatments/inspections, and feeding recommendation
history. Revision `0014_lending_evidence_and_fees` adds private loan video
evidence, commitment/processing/insurance fee balances, a separate loan-reminder
SMS preference, and deduplicated loan reminder delivery records. Back up the
database before applying migrations. Revision `0015_plan_pricing_comparison`
stores the farmer-entered market price for production-plan comparisons.

## New API routes
- POST/GET `/farms/{farm_id}/units`
- PUT/DELETE `/farms/{farm_id}/units/{unit_id}`
- GET `/farms/{farm_id}/audit`
- POST `/finance/institutions/{institution_id}/loans` opens an approved loan account.
- POST `/finance/loans/{loan_id}/disbursements` records a verified manual disbursement.
- POST `/finance/loans/{loan_id}/repayments` records a verified manual repayment.
- POST `/farms/{farm_id}/loan-evidence` uploads a loan-application video;
  POST `/finance/loans/{loan_id}/evidence` uploads a disbursement or repayment
  video. Each transaction must use a fresh, uploader-owned video.
- GET `/finance/loan-evidence/{evidence_id}/video` downloads evidence for the
  farm owner or an authorized member of the lender.
- GET `/finance/loans/{loan_id}/schedule` and `/transactions` return the schedule and ledger.
- GET `/farms/{farm_id}/loan-reminders` returns overdue and next-30-day instalments.
- GET `/finance/institutions/{institution_id}/portfolio` returns institution portfolio totals.
- GET `/farms/{farm_id}/dashboard/analytics` returns production-unit comparisons,
  growth and water-quality histories, indicative FCR, feed forecasts, financial
  indicators, and harvest estimates.
- GET `/farms/{farm_id}/production-plans/{plan_id}/automated-costing` returns
  recorded and projected production costs, break-even price, recommended price,
  projected revenue/profit, and any saved farmer-entered market-price comparison.
- PATCH `/farms/{farm_id}/production-plans/{plan_id}/pricing` saves the desired
  profit percentage, markup/margin method, and optional market price, then
  recalculates the cost and revenue projections.
- POST `/farms/{farm_id}/production-plans/{plan_id}/pricing-scenario` previews
  pricing assumptions without saving them.
- GET `/farms/{farm_id}/reports/bank-ready.csv` exports record-derived production,
  costs, sales, receivables, and cash-flow indicators for the farm owner.
- GET `/farms/{farm_id}/reports/{summary|production|sales|inventory|financial|bank-ready}.xlsx`
  exports one or more analysis sheets in Excel format.
- GET `/farms/{farm_id}/reports/analytics/{production|sales|inventory|financial}.csv`
  exports searchable CSV report data.
- GET `/farms/{farm_id}/daily-record-status` reports feeding records for active cycles.
- PATCH `/auth/me` updates the farmer's phone number and separate daily-record
  and loan-reminder SMS opt-ins.
- POST `/farms/{farm_id}/units/{unit_id}/cycles?evidence_id=...` records stocking
  with required linked evidence.
- POST `/farms/{farm_id}/evidence-challenges` issues one-time codes for configured
  high-risk activities.
- POST `/farms/{farm_id}/evidence` accepts a raw WebM/MP4 body with unit tag,
  capture/device timestamps, GPS coordinates/accuracy, optional active-cycle ID,
  and required challenge parameters.
- POST `/farms/{farm_id}/feeds/{feed_id}/receipts?unit_id=...&evidence_id=...`
  records evidenced feed delivery and cost.
- POST `/farms/{farm_id}/units/{unit_id}/cycles/{cycle_id}/feeding-estimate`
  creates a versioned tilapia/catfish advisory recommendation after owner profile
  confirmation; missing verified sampling or safe recent water readings suspend
  approval.
- POST `/farms/{farm_id}/feeding-recommendations/{id}/approve` approves a safe
  recommendation. Actual feeding uses its `recommendation_id` and session number
  to preserve recommended-versus-actual history and deduct inventory.
- POST/GET `/farms/{farm_id}/feeds/{feed_id}/reconciliations` records evidenced
  physical feed counts and adjusts the inventory ledger.
- GET `/farms/{farm_id}/feed-forecast` projects usage from approved daily rations.
- POST `/farms/{farm_id}/fish-transfers?evidence_id=...` records transfers
  between active production cycles on the same farm.
- POST `/farms/{farm_id}/units/{unit_id}/cycles/{cycle_id}/treatments?evidence_id=...`
  and POST `/farms/{farm_id}/units/{unit_id}/inspections?evidence_id=...`
  record evidenced treatments and inspection checklists.
- POST/GET `/farms/{farm_id}/supervisors` assigns existing accounts to review
  farm evidence. Supervisors can use GET `/farms/{farm_id}/evidence-review`,
  POST `/farms/{farm_id}/evidence/{id}/verification`, and
  POST `/farms/{farm_id}/evidence/{id}/correction-requests`; they cannot edit
  operational records or attach/delete evidence.
- POST `/farms/{farm_id}/sales/harvests?evidence_id=...` and
  POST `/farms/{farm_id}/sales/transactions?evidence_id=...` require linked
  harvest and dispatch evidence.

Loan terms support monthly, quarterly, harvest-based, and lender-defined custom
instalments. Custom principal and interest totals must match the approved principal
and flat-interest calculation. Daily feeding entries are expected for every active
cycle. Missing entries turn red after 08:00 Africa/Accra and trigger at most one
SMS per opted-in farmer each day. Configure `AQUAFARM_DAILY_RECORD_REMINDERS_ENABLED=true`,
`AQUAFARM_DAILY_RECORD_REMINDER_TIME=08:00`, `HUBTEL_CLIENT_ID`,
`HUBTEL_CLIENT_SECRET`, and `HUBTEL_SMS_SENDER_ID` in the backend environment.
Farmers must save an international-format number and explicitly opt in on the
overview page. SMS is disabled until the operator supplies valid Hubtel settings.
The backend reads these settings from its process environment; `.env.example` is
reference-only and is not automatically loaded. In PowerShell, set the variables
in the same terminal before starting Uvicorn (for example,
`$env:AQUAFARM_DAILY_RECORD_REMINDERS_ENABLED = "true"`). Loan SMS reminders
are separately disabled by default; enable them with
`AQUAFARM_LOAN_REMINDERS_ENABLED=true`. Farmers must explicitly enable loan
reminders in their profile. Upcoming instalments are messaged once seven days
before the due date and overdue instalments once per day. Keep credentials out
of source control and logs.

Lenders enter fixed GH₵ commitment and processing fees when opening an account.
Agricultural-loan insurance is calculated as 1% of approved principal. Fees are
distributed across installments (or explicitly allocated in a custom schedule)
and included in outstanding balances and arrears. Repayments are allocated to
interest, then fees, then principal. Interest uses the existing flat-simple
formula; this is a manually recorded ledger and does not initiate money movement.

Loan application, disbursement, and repayment submissions require a new
15-second camera recording. The server checks declared duration, timestamp
freshness, video container header, size, and SHA-256 duplicates; it does not
independently decode videos to verify duration. Do not record PINs, passwords, or
full account numbers. The bank-ready CSV is a record-derived export, not a
certified financial statement or credit decision.

Loan applications capture a farmer-authorized appraisal snapshot for the selected
institution. It includes applicant/farm identity, per-cycle production and
sampling history, harvest history, production-plan harvest estimates, recorded feed and operating
costs, invoiced sales versus collected payments and customer credit, a 12-month
recorded cash-flow history, a 12-month indicative projection, and tracked system-loan balances and scheduled obligations across
the applicant's owned farms. Optional monthly other income,
household expenses, and debts outside AquaFarm are farmer-declared; blanks remain
unreported rather than being treated as zero. Repayment capacity is withheld when
there is no recent recorded farm cash-flow activity or a required declaration is
missing. Harvest plans currently have no expected harvest date, so their
projected proceeds are disclosed separately and excluded from dated cash-flow
projections. GPS coordinates and customer identities are excluded from lender
snapshots. All disclosed metrics remain self-reported or record-derived and are
not independently verified or a credit decision.

`DELETE /farms/{farm_id}` now archives the farm instead of destroying it.
Farm GPS coordinates are needed before evidence can be uploaded. Evidence uploads
require an in-app camera flow, a matching unit tag, client-reported GPS and
timestamps, and a 15-second duration value. The backend checks the video container
header and SHA-256 duplicates, but duration and client metadata are not independently
attested; supervisor playback and verification remain necessary. GPS data is
user-reported, not independently certified.

The starter tilapia/catfish feeding rates are advisory, require farm-owner
confirmation, and are not certified local husbandry guidance. Forecasts assume
approved daily rations remain constant. Feed reconciliation writes a ledger
adjustment rather than rewriting historic transactions.
Harvest dates are projected linearly from the two latest recorded weight samples
and a linked production-plan target; they are unavailable when those inputs are
missing or show no positive growth. FCR and costs are indicative, not verified
production or accounting statements. Excel exports require the `openpyxl`
dependency installed from `requirements.txt`.
Selling-price break-even and profit projections use planned costs plus recorded
cycle expenses, allocated shared expenses, priced feed consumption, estimated
live population and the latest recorded sample where available. Unpriced feed
consumption falls back to the plan's configured feed price and is flagged. The
farmer-entered market price is not independently verified; cost projections,
harvest weights, revenue and profit are estimates.

## Security notes
The audit log captures who performed CRUD actions, not every read or old/new
field value. It is not yet an immutable, independently stored compliance ledger.
This version is a development milestone, not production-ready lending software.
