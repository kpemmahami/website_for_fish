# Phase 1B authentication and account management

## Super Admin registration hotfix

The previous public redemption route created an administrator for anyone presenting a valid, matching invitation token. Issuing a token required Platform Owner access. Both routes are removed. Existing administrator accounts, invitation history and institution staff activation remain in place.

After an authorized release, open the Super Admin sign-in portal and confirm there is no registration or invitation redemption link. Verify that an unauthenticated POST with a fictional payload to each of `/auth/admin/invitations`, `/auth/admin/accept-invitation` and `/auth/admin/register` returns 404. Confirm an existing authorized administrator can still sign in. The hotfix requires no Alembic migration or new environment variables.

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
| Public Super Admin provisioning blocked | Newly implemented and locally verified |
| Internal administrator creation and recovery | Not implemented |
| Internal financial institution registration | Not implemented |
| Compulsory normalized mobile numbers and phone login | Not implemented |
| Phone verification, login MFA, recovery and trusted devices | Not implemented |
| Authentication SMS integration | Not implemented |
| Farm staff creation, permissions, farm and unit assignments | Partially implemented |
| Institution staff creation and activation | Already implemented and verified |
| Audit history and session revocation | Partially implemented |
| Phase 1B mobile responsiveness | Partially implemented |
| Hosted verification of this hotfix | Not implemented |

## Remaining implementation order

1. Add staged identity migrations for normalized phone numbers, verification state, password-change requirements and revocable sessions. Review conflicts before enforcing uniqueness.
2. Extend owner bootstrap and add owner-only administrator management. Move institution registration to an authorized transactional workflow.
3. Add shared login verification, password recovery, delivery configuration and phone changes. Test with an isolated provider mock before testing delivery.
4. Extend farm and institution staff management, enforce membership and unit scope in the API and verify activity attribution.
5. Test SQLite and isolated PostgreSQL migrations, run regression and acceptance checks, then prepare the rollout and rollback instructions for approval.
