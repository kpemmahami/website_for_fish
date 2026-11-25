# Phase 1B authentication and account management

## Super Admin registration hotfix

The previous public redemption route created an administrator for anyone presenting a valid, matching invitation token. Issuing a token required Platform Owner access. Both routes are removed. Existing administrator accounts, invitation history and institution staff activation remain in place.

After an authorized release, open the Super Admin sign-in portal and confirm there is no registration or invitation redemption link. Verify that an unauthenticated POST with a fictional payload to each of `/auth/admin/invitations`, `/auth/admin/accept-invitation` and `/auth/admin/register` returns 404. Confirm an existing authorized administrator can still sign in. The hotfix requires no Alembic migration or new environment variables.

## Controlled financial institution registration

1. In a local test environment, open the financial institution portal and confirm it offers sign-in. Confirm the former public registration and staff invitation routes return 404.
2. Sign in as a platform administrator. Open **Stakeholder Approvals → Financial institutions → Register institution**. Enter a fictional institution and its initial administrator. Submit and confirm the institution appears as pending.
3. Sign in through the institution portal with the initial account. Confirm lending operations remain unavailable while the institution is pending. Return to Stakeholder Approvals to review it.

The replacement `POST /finance/admin/institutions` requires platform administrator access and creates the initial account, pending institution, owner membership and audit entries in one transaction. The former institution-side creation POST is removed. This change uses the existing schema and adds no environment variables. Mobile phone capture, additional institutional profile fields and first-login activation are pending.

### Institution staff

1. Sign in as the owner of a verified institution. Open **Institution Management → Staff Management → Add Staff**.
2. Enter an unused work email, name, mobile phone in international format, initial password and staff role. Share sign-in details privately.
3. Sign in through the regular institution portal using the new account. Confirm that the employee sees the institution workspace and has only the permissions of the assigned role.

The institution owner creates the account and scoped membership through `POST /finance/institutions/{institution_id}/staff`. Invitation issuance, preview, redemption and acceptance are removed. Historical invitations and existing active memberships are preserved. Outstanding invitation links no longer work. This change requires no database migration.

## Password recovery and sign-in controls

The Farmer, Financial Institution and Super Admin sign-in screens have an eye icon inside the password field and a **Forgot password?** action. Recovery uses the account's email address. The latest link expires after 15 minutes and can succeed once. A successful reset signs the account out of existing sessions.

For a recovery release, apply Alembic revision `0031_password_recovery` to the intended database first. From the Windows workspace root:

```powershell
Push-Location .\aquafarm-manager\backend
try {
    & ..\..\.venv\Scripts\python.exe -m tools.migrate_password_recovery
} finally {
    Pop-Location
}
```

Paste the Neon URL at the hidden prompt. Compare the displayed host and database with the production Render configuration before confirming. The helper accepts revisions `0030` and `0031`, applies only `0031`, and verifies both new columns. Configure these private environment settings in the Render backend:

| Setting | Value |
| --- | --- |
| `AQUAFARM_RECOVERY_ORIGIN` | `https://aquafarm-ghana-frontend.onrender.com` |
| `AQUAFARM_RECOVERY_FROM` | Sender email on a domain verified in Resend |
| `AQUAFARM_RECOVERY_RESEND_API_KEY` | Private Resend sending API key |

After an authorized deployment, use a designated test account in each portal to request a link, confirm delivery, reset the password and verify old sessions are rejected. Repeat with an unregistered email and confirm the same on-screen message. Before mail is configured, recovery requests return an unavailable message. Email delivery is mocked in automated tests.

If a release is rolled back, keep the additive columns in place. Avoid rolling back to an older backend after users have reset passwords without addressing session revocation, since older code does not enforce the new revocation checks.

## Read-only privileged account review

The Platform Owner can open **Super Admin → Manage administrators** to search and page through administrators. The directory lists role, contact details, creation date, and access status. The server denies access to ordinary Super Admins. On the development branch, **Add Super Admin** prepares a pending account from a name, email, and mobile number. Pending accounts cannot sign in or be reactivated through the access controls. They activate through the contact and authenticator setup flow.

### Pending administrator contact verification

Revision `0033_admin_contact_proof` adds the verification challenge and authenticator state table. The owner selects **Send verification** for a pending account. The recipient opens the link sent to their email and enters the six-digit code sent to their phone. Challenges expire in ten minutes, allow five attempts, and require a two-minute wait before another send. A new send replaces the old challenge.

After verifying both contacts, the recipient adds the displayed key to a time-based authenticator app, chooses a private password, and submits an authenticator code. On sign-in, enter the email or phone and password, then supply a fresh code when prompted. Codes used for activation or sign-in cannot be reused. Existing administrators retain their current sign-in flow. Their MFA enrollment and an audited lost-authenticator recovery process are pending.

Live testing requires the existing Resend configuration and the backend secrets `HUBTEL_CLIENT_ID`, `HUBTEL_CLIENT_SECRET`, `HUBTEL_SMS_SENDER_ID`, and `AQUAFARM_ADMIN_AUTHENTICATOR_KEY`. Generate the authenticator key from at least 32 random bytes and keep it in Render's backend settings and secure backup. Changing it invalidates enrolled authenticators. Use fictional accounts and mocked delivery for automated tests.

### Administrator access controls

Revision `0032_administrator_access` adds an active-by-default suspension flag and a nullable session generation. Apply it to the intended database before releasing the updated backend. Existing sessions remain valid until a password reset, suspension, explicit revocation, or normal expiry.

1. In an isolated test environment, sign in as the Platform Owner and as a second Super Admin in separate browser sessions.
2. In **Manage administrators**, choose **Sign out all sessions** for the second account. Enter a reason and confirm the existing session is rejected while a fresh sign-in succeeds.
3. Choose **Suspend** and confirm the second account cannot sign in or use existing sessions. Choose **Reactivate** and confirm the account needs to sign in again. The owner row has no access actions.
4. Use the administrative audit query below to check the acting owner, target administrator, and actions. Preserve the migration columns on rollback because older releases do not enforce these restrictions.

For a new local Platform Owner, run `..\..\.venv\Scripts\python.exe -m tools.setup_admin` from `aquafarm-manager\backend` after migrating the intended local database. The command requests name, email, mobile number and hidden password confirmation. With `DATABASE_URL` unset, it uses the local backend SQLite database. For a hosted bootstrap, verify the target and obtain explicit authorization first. The command preserves an existing owner and does not promote an account.

In the Neon SQL Editor, verify that the selected branch and database are the ones used by Render. Run the following as an authorized database operator. Keep the output private.

```sql
BEGIN READ ONLY;

SELECT u.id, u.full_name, u.email, u.created_at,
       CASE WHEN s.admin_user_id IS NULL THEN 'Super Admin'
            ELSE 'Platform Owner' END AS role
FROM users AS u
LEFT JOIN platform_admin_setup AS s ON s.id = 1 AND s.admin_user_id = u.id
WHERE u.account_type = 'admin'
ORDER BY u.created_at, u.id;

SELECT a.created_at, a.actor_id, a.action, a.entity_type, a.entity_id
FROM audit_logs AS a
WHERE a.entity_type = 'platform_admin'
   OR a.actor_id IN (SELECT id FROM users WHERE account_type = 'admin')
ORDER BY a.created_at DESC, a.id DESC
LIMIT 200;

ROLLBACK;
```

Compare account IDs, creation dates and audit events against the owner’s records. The existing invitation acceptance event identifies the new account. The issuance event does not reliably link an inviter to an individual acceptance. Preserve audit history. Owner-reviewed suspension and session revocation require the next account-management changes.

## Implementation checklist

| Feature | Status |
| --- | --- |
| Farmer registration and existing email login | Already implemented and verified |
| Farmer, processor and integrated account approval | Newly implemented and locally verified |
| Granular administrative approval permissions | Partially implemented |
| Bootstrap administrator and owner designation | Partially implemented |
| Owner-only administrator directory | Newly implemented and locally verified |
| Administrator suspension, reactivation and session revocation | Newly implemented and locally verified |
| Public Super Admin provisioning blocked | Verified on the hosted website |
| Internal administrator creation and recovery | Partially implemented |
| Pending administrator email and phone verification | Newly implemented and locally verified |
| Internal financial institution registration | Partially implemented |
| Email or registered phone sign-in across all three portals | Newly implemented and locally verified |
| Compulsory normalized numbers for farmer, processor, integrated, institution administrator, institution staff and platform administrator creation | Newly implemented and locally verified |
| Required phone enrollment for farm staff and legacy profile completion | Partially implemented |
| Phone conflict review and database-level identity uniqueness | Not implemented |
| Authenticator enrollment and login MFA for newly provisioned administrators | Newly implemented and locally verified |
| Existing administrator MFA enrollment and authenticator recovery | Not implemented |
| General phone verification and trusted devices | Not implemented |
| Password recovery by email | Newly implemented and locally verified |
| Real recovery email delivery | Blocked by external configuration |
| Authentication SMS integration | Not implemented |
| Farm staff creation, permissions, farm and unit assignments | Partially implemented |
| Direct institution staff creation and role enforcement | Newly implemented and locally verified |
| Audit history and session revocation | Partially implemented |
| Phase 1B mobile responsiveness | Partially implemented |
| Hosted verification of the Super Admin hotfix | Verified on the hosted website |

## Remaining implementation order

New farmer and processor signup requires a phone number. The web form and Flutter source send it, so release a compatible Flutter build alongside the backend if users register through the mobile app. Existing accounts keep email sign-in. Ghanaian local, country-code, and international input are normalized by the same service as phone sign-in. This change validates formatting. Ownership verification and conflict handling have separate rollout steps.

New farmer and processor accounts can sign in and check their status. Operational API requests are denied while approval is pending. A platform administrator can approve the account from **Super Admin → Farmer and processor approvals**. The decision is audited, and the user can refresh the status screen to open the dashboard. This uses the existing account type and audit tables and requires no new migration.

1. Add staged identity migrations for normalized phone numbers, verification state, password-change requirements and revocable sessions. Review conflicts before enforcing uniqueness.
2. Extend owner bootstrap and add owner-only administrator management. Extend institution provisioning with contact details and secure first-login activation.
3. Add shared login verification, password recovery, delivery configuration and phone changes. Test with an isolated provider mock before testing delivery.
4. Extend farm and institution staff management, enforce membership and unit scope in the API and verify activity attribution.
5. Test SQLite and isolated PostgreSQL migrations, run regression and acceptance checks, then prepare the rollout and rollback instructions for approval.
