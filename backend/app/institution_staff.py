"""Institution-scoped staff invitations and membership lifecycle."""

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import os
import secrets
import smtplib
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import HTTPException
from pydantic import BaseModel, EmailStr, Field, StringConstraints
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from .administration import token_digest
from .development import enabled
from .lending import Institution, InstitutionMember, member
from .main import DATABASE_URL, AuditLog, Base, CurrentUser, Db, Register, User, app, audit, new_user

StaffRole = Literal['loan_officer', 'credit_manager', 'disbursement', 'collections', 'viewer', 'officer', 'reviewer']
TAG = ['Institution staff']
ROOT = '/finance/institutions/{institution_id}/staff'


def utcnow():
    return datetime.now(timezone.utc)


class StaffInvitation(Base):
    __tablename__ = 'institution_staff_invitations'
    __table_args__ = (UniqueConstraint('institution_id', 'email', name='uq_staff_invite_institution_email'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey('finance_institutions.id'))
    email: Mapped[str] = mapped_column(String(255), index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    phone_number: Mapped[str | None] = mapped_column(String(16))
    department: Mapped[str | None] = mapped_column(String(120))
    job_title: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    invited_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    accepted_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InviteStaffIn(BaseModel):
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    email: EmailStr
    phone_number: str | None = Field(default=None, pattern=r'^\+[1-9]\d{7,14}$')
    department: str | None = Field(default=None, max_length=120)
    job_title: str | None = Field(default=None, max_length=120)
    role: StaffRole


class InvitationToken(BaseModel):
    token: str = Field(min_length=43, max_length=43)


class ActivateStaffIn(InvitationToken):
    full_name: str
    password: str


class StaffResponse(BaseModel):
    decision: Literal['accept', 'decline']


class MembershipUpdate(BaseModel):
    role: StaffRole | None = None
    status: Literal['active', 'suspended', 'removed'] | None = None


def invite_view(invitation, institution):
    expires = invitation.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    status = 'expired' if invitation.status == 'pending' and expires <= utcnow() else invitation.status
    return {
        'id': invitation.id, 'institution_id': institution.id, 'institution_name': institution.name,
        'email': invitation.email, 'full_name': invitation.full_name, 'role': invitation.role,
        'status': status, 'expires_at': expires, 'created_at': invitation.created_at,
    }


def delivery(invitation, institution, token):
    result = invite_view(invitation, institution)
    if enabled(DATABASE_URL):
        return {**result, 'delivery': 'local_preview', 'invitation_token': token}

    host = os.getenv('AQUAFARM_STAFF_SMTP_HOST')
    sender = os.getenv('AQUAFARM_STAFF_SMTP_FROM')
    portal = os.getenv('AQUAFARM_STAFF_PORTAL_URL', '').rstrip('/')
    if not host or not sender or urlsplit(portal).scheme != 'https' or not urlsplit(portal).hostname:
        return {**result, 'delivery': 'not_configured'}
    message = EmailMessage()
    message['To'] = invitation.email
    message['From'] = sender
    message['Subject'] = 'AquaFarm institution staff invitation'
    message.set_content(
        f'You have been invited to join {institution.name} as {invitation.role}. '
        'This invitation expires in 24 hours. Open this link to continue:\n'
        f'{portal}/#staff-invitation={token}'
    )
    try:
        with smtplib.SMTP(host, int(os.getenv('AQUAFARM_STAFF_SMTP_PORT', '587')), timeout=10) as smtp:
            import ssl

            smtp.starttls(context=ssl.create_default_context())
            username = os.getenv('AQUAFARM_STAFF_SMTP_USERNAME')
            if username:
                smtp.login(username, os.environ['AQUAFARM_STAFF_SMTP_PASSWORD'])
            smtp.send_message(message)
    except (OSError, ValueError, KeyError, smtplib.SMTPException):
        return {**result, 'delivery': 'failed'}
    return {**result, 'delivery': 'sent'}


def membership_for(db, institution_id, user_id):
    return db.scalar(select(InstitutionMember).where(
        InstitutionMember.institution_id == institution_id, InstitutionMember.user_id == user_id,
    ))


def staff_change(db, actor, action, institution_id, details):
    import json

    audit(db, actor, action, 'institution_staff', institution_id, json.dumps(details))


@app.get(ROOT, tags=TAG)
def list_staff(institution_id: int, user: CurrentUser, db: Db):
    institution = member(db, institution_id, user.id, 'manage_staff')
    staff = db.execute(select(InstitutionMember, User).join(User, User.id == InstitutionMember.user_id).where(
        InstitutionMember.institution_id == institution.id,
    ).order_by(User.full_name, User.id))
    invitations = db.scalars(select(StaffInvitation).where(
        StaffInvitation.institution_id == institution.id,
    ).order_by(StaffInvitation.created_at.desc()))
    activity = db.scalars(select(AuditLog).where(
        AuditLog.entity_type == 'institution_staff', AuditLog.entity_id == institution.id,
    ).order_by(AuditLog.id.desc()).limit(100))
    return {
        'staff': [{'user_id': person.id, 'full_name': person.full_name, 'email': person.email,
                   'phone_number': person.phone_number, 'role': row.role, 'status': row.status,
                   'department': row.department, 'job_title': row.job_title, 'created_at': row.created_at}
                  for row, person in staff],
        'invitations': [invite_view(row, institution) for row in invitations],
        'activity': [{'actor_id': row.actor_id, 'action': row.action, 'details': row.details,
                      'created_at': row.created_at} for row in activity],
    }


@app.post(ROOT + '/invitations', status_code=201, tags=TAG)
def invite_staff(institution_id: int, data: InviteStaffIn, user: CurrentUser, db: Db):
    institution = member(db, institution_id, user.id, 'manage_staff')
    email = str(data.email).lower()
    target = db.scalar(select(User).where(User.email == email))
    if target and target.is_platform_admin:
        raise HTTPException(422, 'Use an ordinary staff account')
    if target and membership_for(db, institution_id, target.id):
        raise HTTPException(409, 'Staff member already belongs to this institution')
    existing = db.scalar(select(StaffInvitation).where(
        StaffInvitation.institution_id == institution_id, StaffInvitation.email == email,
    ))
    if existing and invite_view(existing, institution)['status'] == 'pending':
        raise HTTPException(409, 'Invitation is awaiting acceptance')
    token = secrets.token_urlsafe(32)
    values = data.model_dump(exclude={'email'})
    values.update(token_hash=token_digest(token), status='pending', invited_by=user.id,
                  created_at=utcnow(), expires_at=utcnow() + timedelta(hours=24),
                  accepted_by=None, accepted_at=None)
    if existing:
        result = db.execute(update(StaffInvitation).where(
            StaffInvitation.id == existing.id, StaffInvitation.token_hash == existing.token_hash,
            StaffInvitation.status == existing.status,
        ).values(**values))
        if result.rowcount != 1:
            raise HTTPException(409, 'Invitation changed. Refresh and try again.')
        invitation = existing
    else:
        invitation = StaffInvitation(institution_id=institution_id, email=email, **values)
        db.add(invitation)
    try:
        db.flush()
        staff_change(db, user, 'invite_staff', institution_id, {'invitation_id': invitation.id, 'role': data.role})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'An invitation already exists') from exc
    return delivery(invitation, institution, token)


@app.post(ROOT + '/invitations/{invitation_id}/{action}', tags=TAG)
def manage_invitation(institution_id: int, invitation_id: int, action: Literal['resend', 'cancel'], user: CurrentUser, db: Db):
    institution = member(db, institution_id, user.id, 'manage_staff')
    invitation = db.get(StaffInvitation, invitation_id)
    if invitation is None or invitation.institution_id != institution_id:
        raise HTTPException(404, 'Invitation not found')
    if invitation.status != 'pending':
        raise HTTPException(409, 'Invitation is no longer pending')
    token = secrets.token_urlsafe(32)
    values = {'status': 'cancelled'} if action == 'cancel' else {
        'token_hash': token_digest(token), 'expires_at': utcnow() + timedelta(hours=24),
    }
    result = db.execute(update(StaffInvitation).where(
        StaffInvitation.id == invitation.id, StaffInvitation.status == 'pending',
        StaffInvitation.token_hash == invitation.token_hash,
    ).values(**values))
    if result.rowcount != 1:
        raise HTTPException(409, 'Invitation changed. Refresh and try again.')
    staff_change(db, user, action + '_staff_invitation', institution_id, {'invitation_id': invitation.id})
    db.commit()
    return delivery(invitation, institution, token) if action == 'resend' else invite_view(invitation, institution)


def pending_token(db, token):
    invitation = db.scalar(select(StaffInvitation).where(
        StaffInvitation.token_hash == token_digest(token), StaffInvitation.status == 'pending',
        StaffInvitation.expires_at > utcnow(),
    ))
    if invitation is None:
        raise HTTPException(404, 'Invitation is invalid, expired, or already used')
    institution = db.get(Institution, invitation.institution_id)
    if institution is None or institution.status != 'verified':
        raise HTTPException(404, 'Invitation is unavailable')
    return invitation, institution


@app.post('/auth/institution/staff-invitations/preview', tags=TAG)
def preview_invitation(data: InvitationToken, db: Db):
    invitation, institution = pending_token(db, data.token)
    existing = db.scalar(select(User.id).where(User.email == invitation.email)) is not None
    return {**invite_view(invitation, institution), 'requires_sign_in': existing}


def respond(db, invitation, actor, decision):
    institution = db.get(Institution, invitation.institution_id)
    if institution is None or institution.status != 'verified':
        raise HTTPException(404, 'Invitation is unavailable')
    if actor.email.lower() != invitation.email or actor.is_platform_admin:
        raise HTTPException(404, 'Invitation is unavailable')
    accepted = decision == 'accept'
    if accepted and membership_for(db, institution.id, actor.id):
        raise HTTPException(409, 'Staff member already belongs to this institution')
    changed = db.execute(update(StaffInvitation).where(
        StaffInvitation.id == invitation.id, StaffInvitation.token_hash == invitation.token_hash,
        StaffInvitation.status == 'pending', StaffInvitation.expires_at > utcnow(),
    ).execution_options(synchronize_session=False).values(status='accepted' if accepted else 'declined',
             accepted_by=actor.id if accepted else None, accepted_at=utcnow() if accepted else None))
    if changed.rowcount != 1:
        raise HTTPException(409, 'Invitation is expired or already used')
    if accepted:
        db.add(InstitutionMember(
            institution_id=institution.id, user_id=actor.id, role=invitation.role,
            department=invitation.department, job_title=invitation.job_title,
        ))
    staff_change(db, actor, decision + '_staff_invitation', institution.id, {'invitation_id': invitation.id})
    db.commit()
    return invite_view(invitation, institution)


@app.post('/auth/institution/staff-invitations/activate', status_code=201, tags=TAG)
def activate_staff(data: ActivateStaffIn, db: Db):
    invitation, _ = pending_token(db, data.token)
    if db.scalar(select(User.id).where(User.email == invitation.email)) is not None:
        raise HTTPException(409, 'Sign in with the invited email to respond')
    from pydantic import ValidationError

    try:
        registration = Register(full_name=data.full_name, password=data.password, email=invitation.email)
    except ValidationError as exc:
        raise HTTPException(422, 'Enter a valid full name and a password of 8 to 128 characters') from exc
    user = new_user(registration, 'institution')
    user.phone_number = invitation.phone_number
    db.add(user)
    try:
        db.flush()
        return respond(db, invitation, user, 'accept')
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'Account or membership already exists. Sign in to continue.') from exc


@app.get('/auth/institution/staff-invitations', tags=TAG)
def my_staff_invitations(user: CurrentUser, db: Db):
    invitations = db.execute(select(StaffInvitation, Institution).join(
        Institution, StaffInvitation.institution_id == Institution.id,
    ).where(StaffInvitation.email == user.email, StaffInvitation.status == 'pending',
            StaffInvitation.expires_at > utcnow(), Institution.status == 'verified'))
    return [invite_view(invitation, institution) for invitation, institution in invitations]


@app.post('/auth/institution/staff-invitations/{invitation_id}/respond', tags=TAG)
def respond_staff(invitation_id: int, data: StaffResponse, user: CurrentUser, db: Db):
    invitation = db.get(StaffInvitation, invitation_id)
    if invitation is None or invitation.email != user.email:
        raise HTTPException(404, 'Invitation not found')
    try:
        return respond(db, invitation, user, data.decision)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'Membership already exists') from exc


@app.patch(ROOT + '/{staff_user_id}', tags=TAG)
def update_staff(institution_id: int, staff_user_id: int, data: MembershipUpdate, user: CurrentUser, db: Db):
    member(db, institution_id, user.id, 'manage_staff')
    row = membership_for(db, institution_id, staff_user_id)
    if row is None:
        raise HTTPException(404, 'Staff member not found')
    if row.role == 'owner' or staff_user_id == user.id:
        raise HTTPException(403, 'Institution owner access is protected')
    before = {'role': row.role, 'status': row.status}
    after = data.model_dump(exclude_none=True)
    if not after:
        raise HTTPException(422, 'Choose a role or status change')
    result = db.execute(update(InstitutionMember).where(
        InstitutionMember.id == row.id, InstitutionMember.role == before['role'],
        InstitutionMember.status == before['status'],
    ).values(**after))
    if result.rowcount != 1:
        raise HTTPException(409, 'Staff access changed. Refresh and try again.')
    staff_change(db, user, 'update_staff_access', institution_id, {'user_id': staff_user_id, 'before': before, 'after': after})
    db.commit()
    return {'user_id': staff_user_id, 'role': row.role, 'status': row.status}
