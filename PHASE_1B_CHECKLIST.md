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

## Read-only privileged account review

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
| Farmer approval, Super Admin dashboard and permissions | Partially implemented |
| Bootstrap administrator and owner designation | Partially implemented |
| Public Super Admin provisioning blocked | Verified on the hosted website |
| Internal administrator creation and recovery | Not implemented |
| Internal financial institution registration | Partially implemented |
| Email or registered phone sign-in across all three portals | Newly implemented and locally verified |
| Compulsory normalized mobile numbers for all accounts | Partially implemented |
| Phone verification, login MFA, recovery and trusted devices | Not implemented |
| Authentication SMS integration | Not implemented |
| Farm staff creation, permissions, farm and unit assignments | Partially implemented |
| Direct institution staff creation and role enforcement | Newly implemented and locally verified |
| Audit history and session revocation | Partially implemented |
| Phase 1B mobile responsiveness | Partially implemented |
| Hosted verification of the Super Admin hotfix | Verified on the hosted website |

## Remaining implementation order

1. Add staged identity migrations for normalized phone numbers, verification state, password-change requirements and revocable sessions. Review conflicts before enforcing uniqueness.
2. Extend owner bootstrap and add owner-only administrator management. Extend institution provisioning with contact details and secure first-login activation.
3. Add shared login verification, password recovery, delivery configuration and phone changes. Test with an isolated provider mock before testing delivery.
4. Extend farm and institution staff management, enforce membership and unit scope in the API and verify activity attribution.
5. Test SQLite and isolated PostgreSQL migrations, run regression and acceptance checks, then prepare the rollout and rollback instructions for approval.
