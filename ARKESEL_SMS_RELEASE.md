# Arkesel SMS V2 implementation and release

## Implementation

The verification and reminder services previously called the Hubtel adapter directly and expected `HUBTEL_*` variables. Supplying only Arkesel credentials could not configure that code path. The frontend's verification error is also used for several provider failures. There is no evidence of the exact cause of a previous hosted failure.

- `backend/app/sms_gateway.py` selects the provider, normalizes recipients, validates Arkesel responses, and protects request secrets and message contents. It uses TLS verification and a bounded timeout with redirects disabled. An accepted live send requires provider success and a matching recipient UUID. Unknown outcomes are recorded separately from rejections.
- `backend/app/phone_verification.py`, `main.py`, and `administrator_verification.py` route existing verification, two-phone changes, institution MFA and initial setup, and administrator enrollment contact messages through the selected gateway. Ordinary phone challenges expire in five minutes by default, enforce a 60-second resend delay, retain keyed digests and single-use confirmation, and limit sends per account, phone and client address. The administrator authenticator and enrollment rules retain their existing stronger controls.
- `backend/app/sms_outbox.py`, `lending.py`, `loan_servicing.py`, and `daily_reminders.py` provide alerts for posted approval, rejection, disbursement, repayment, deposit and settlement events, alongside the existing missed-feeding and repayment reminders. The farmer settings page has a separate opt-in for confirmations, off for existing accounts. Outbox rows commit with the source transaction. The existing scheduler claims them after commit. A definitive provider rate limit allows one retry after two minutes. Ambiguous sends are held as unknown. No phone number or message body is stored in the queue. Templates use only approved wording and optional first-party names when explicitly enabled.
- `backend/app/sms_management.py` and `frontend/src/smsManagement.tsx` provide Platform Owner access to the dashboard, gateway, balances, a sandbox-only test form, templates, scheduled queue counts, history, delivery reports, audit history and settings. The history stores metadata only. Its date filters use Ghana dates. The audit view includes the initiating platform operator for sandbox tests.
- `backend/migrations/versions/0047_sms_deliveries.py` adds the SMS delivery metadata, OTP quota, and financial notification outbox tables and a user consent flag. It makes no changes to existing transaction or production tables.

### API routes

All routes under `/admin/sms` require the Platform Owner. GET routes are `/summary`, `/gateway`, `/balance`, `/history`, `/usage`, `/templates`, `/scheduled`, and `/settings`. POST routes are `/sandbox-test` and `/delivery-reports`. The latter polls only UUIDs already in the application's delivery history. The OpenAPI path entry for single-message details omits the parameter, but the official request examples use `GET /api/v2/sms/{message_id}`. Batch polling uses `POST /api/v2/sms/message-reports`. No callback is configured because the published callback examples do not establish a verifiable signature contract. [Arkesel SMS V2 specification](https://developers.arkesel.com/spec/api_spec.v2.4.0.yaml)

## Staging environment

Rotate the exposed API key. Use the replacement only through the backend environment or a secret manager. The sender displayed on the handset is the registered sender ID. The supplied mobile number is a test recipient, and belongs in the test form rather than in the environment configuration.

```dotenv
SMS_PROVIDER=arkesel
SMS_ENABLED=true
ARKESEL_API_KEY=
ARKESEL_SENDER_ID=AquaFarmGH
ARKESEL_BASE_URL=https://sms.arkesel.com
ARKESEL_SANDBOX=true
OTP_MODE=local
ARKESEL_ALLOW_INTERNATIONAL=false
ARKESEL_LOW_BALANCE_THRESHOLD=10
OTP_EXPIRY_SECONDS=300
OTP_MAX_ATTEMPTS=5
OTP_SENDS_PER_ACCOUNT_HOUR=8
OTP_SENDS_PER_PHONE_HOUR=8
OTP_SENDS_PER_IP_HOUR=60
AQUAFARM_FINANCIAL_SMS_ENABLED=false
AQUAFARM_SMS_PERSONALIZE_NAMES=false
AQUAFARM_DAILY_RECORD_REMINDERS_ENABLED=false
AQUAFARM_LOAN_REMINDERS_ENABLED=false
```

The blank key above is a placeholder. The backend reads process environment variables. The example file is not loaded automatically. Keep the staging database, signing key, and allowed origin separate from production. Use the existing application database URL and signing key when eventually updating production. Leave `AQUAFARM_LOCAL_TEST_SMS` unset for Arkesel tests.

### Sandbox acceptance

1. Migrate an isolated staging database from the existing revision with `python -m alembic current`, `python -m alembic upgrade 0047_sms_deliveries`, and `python -m alembic current`, run from `backend` with the staging environment loaded. Start the backend and the matching web build.
2. Sign in as the staging Platform Owner. In **SMS Management → Gateway status**, confirm Arkesel and Sandbox. In **SMS balance**, compare the two returned values with the Arkesel dashboard.
3. Open **Send test SMS**, enter the approved test recipient, and submit once. Acceptance is a provider UUID shown as **sandbox** in **SMS history**. A real text should not arrive. A sandbox acknowledgement does not verify a phone.
4. With an isolated account, request a real verification challenge while the gateway is in sandbox mode. Expect HTTP 503, no text, and no verified phone or session from the code-confirmation step. The gateway keeps OTP enforcement active. Do not run this test against the production OTP service.
5. Confirm a farmer or institution staff account cannot access `/admin/sms` endpoints. Confirm history omits phone numbers, message text and codes.

### Live acceptance after authorization

1. Confirm `AquaFarmGH` is approved for Ghana and the replacement key and SMS credits are valid. In isolated staging set `ARKESEL_SANDBOX=false`, keep ordinary reminder and financial switches off, and restart.
2. With the approved test handset, request a real verification SMS once using an isolated account. Confirm the handset receives the text, the history starts at **accepted**, and delivery polling eventually reports **delivered** if the gateway confirms it. A provider report alone cannot verify the account.
3. Confirm the code before five minutes. Verify replay fails and that institution login still requires its existing second factor. Verify the provider's credentials, sender ID and country coverage if the request fails. Do not treat an unknown timeout as permission to resend automatically.
4. Enable opted-in notifications one workflow at a time after signed-in checks. Use only fictional staging transactions for financial notification tests.

## Render deployment after approval

1. In the **backend service → Environment**, enter the approved values as individual environment variables. Put the replacement key in `ARKESEL_API_KEY`. Use **Save only** while staging and approval are pending. Keep the database URL, signing secret, allowed origins, and frontend API URL in their existing locations. The frontend needs no Arkesel environment variables. [Render environment configuration](https://render.com/docs/configure-environment-variables)
2. Confirm the current hosted revision, recoverable backup and a populated PostgreSQL rehearsal. For a release starting at `0046_disbursement_reviews`, apply `python -m alembic upgrade 0047_sms_deliveries` from the backend directory against the existing database. Use Render's existing migration mechanism or the authorized external migration procedure. The Render pre-deploy command is available on paid services. Do not provision a worker for this feature. [Render deploys](https://render.com/docs/deploys)
3. Deploy the reviewed backend and frontend revisions. The backend build remains `pip install -r requirements.txt` from the configured backend root. Start with `uvicorn app.main:app --host 0.0.0.0 --port "$PORT"` and use the existing `/health` check. Verify the proxy handling of client addresses before relying on IP quotas. Keep sandbox settings on staging and select the approved live configuration for the production OTP sender.
4. Verify health, revision, owner balance and the signed-in acceptance flow. Review sanitized logs only. Keep new financial and personalization settings off until their use and consent are approved.

### Rollback

Restore the last known working provider settings and reviewed backend/frontend revisions using the existing deployment process. For Hubtel use `SMS_PROVIDER=hubtel`, `SMS_ENABLED=true` and the existing secure `HUBTEL_CLIENT_ID`, `HUBTEL_CLIENT_SECRET` and `HUBTEL_SMS_SENDER_ID`. Pause the new financial outbox with `AQUAFARM_FINANCIAL_SMS_ENABLED=false`. Keep the additive schema and delivery history in place. Do not downgrade the database for an application rollback.

## Verification and remaining acceptance

The full SQLite regression passed 93 tests. The targeted disposable PostgreSQL run passed 19 tests covering the gateway, phone verification and loan servicing. A populated PostgreSQL rehearsal upgraded 0046 to 0047 and preserved the fictional user, farm and expense. All five frontend tests and the production build passed. Tests used mocked provider calls. The SQLite and PostgreSQL runs reported the existing Starlette TestClient deprecation, and Vite reported a bundle-size warning.

A subsequent 36-test gateway and account regression included the complete institution sign-in flow through the Arkesel transport. Sandbox returned 503 without sending a code. The mocked live response allowed the user to submit the correct code and receive a session. The challenge token could not open the account, and replaying the code failed.

Sandbox connectivity, carrier delivery and signed-in browser acceptance remain pending. Standalone OTP login and recovery for farmer, processor and farm staff accounts are outside the existing verification flow and have not been switched on. Password recovery retains its email route, and privileged login retains the authenticator. Unimplemented notification triggers include account approval alerts, promise-to-pay, reversals, and the broader farm event catalogue. Institution-level SMS reporting, provider-side scheduled sends and editable templates are also pending. The SMS management screens currently show owner-only platform summaries, date-filtered usage and history, and read-only template and settings views.
