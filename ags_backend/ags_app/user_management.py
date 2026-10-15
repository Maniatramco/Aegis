"""Authenticated account management with persistent administrator roles."""
import time
from typing import Literal
from contextlib import contextmanager
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select, delete
from . import core, relational

router = APIRouter()
_attempts = {}


def verify_password(user, value):
    now = time.monotonic()
    attempts = [stamp for stamp in _attempts.get(user.id, []) if stamp > now - 300]
    if len(attempts) >= 10:
        raise HTTPException(429, 'Too many password attempts. Try again in five minutes.')
    _attempts[user.id] = attempts + [now]
    if not core.password_valid(value, user.password_hash):
        raise HTTPException(400, 'Your current password is incorrect. Nothing changed.')
    _attempts.pop(user.id, None)


class PasswordInput(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    password: SecretStr = Field(min_length=12, max_length=200)
    confirmation: SecretStr = Field(min_length=12, max_length=200)


class CreateUser(PasswordInput):
    username: str = Field(min_length=1, max_length=120, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.@-]*$')


class ResetPassword(PasswordInput):
    current_password: SecretStr = Field(min_length=1, max_length=200)

class ChangeRole(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    role: Literal['user','administrator']
    current_password: SecretStr = Field(min_length=1,max_length=200)

class DatasetAssignments(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset_ids: list[str] = Field(max_length=1000)


class DeleteUser(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    username: str = Field(min_length=1, max_length=120)
    current_password: SecretStr = Field(min_length=1, max_length=200)


def public_user(user):
    return {key: getattr(user, key) for key in (
        'id', 'username', 'role', 'created_at', 'updated_at', 'created_by', 'updated_by')
    } | {'is_admin': user.role == 'administrator'}


def matched_password(body):
    password = body.password.get_secret_value()
    if password != body.confirmation.get_secret_value():
        raise HTTPException(400, 'Passwords do not match. Nothing changed.')
    return password


@contextmanager
def account_audit(owner):
    token = relational.actor_override.set(owner)
    source = relational.source.set('user_management')
    try:
        yield
    finally:
        relational.source.reset(source)
        relational.actor_override.reset(token)


def remove_account(user_id, owner, username, *, current_password=None):
    """Remove an account and grants without deleting shared workspace content.

    HTTP callers supply the acting administrator's password. Trusted operators
    can call this function directly after authorizing the exact account removal.
    Historical private artifacts remain archived outside normal application APIs.
    """
    from .dataset_access import PRIVATE
    with core.document_lock('administrator-auth'), core.document_lock('dataset-access'), account_audit(owner):
        with core.Session.begin() as session:
            accounts = list(session.scalars(select(core.User).order_by(core.User.id).with_for_update()))
            actor = next((user for user in accounts if user.id == owner), None)
            if not actor or actor.role != 'administrator':
                raise HTTPException(403, 'Administrator access required.')
            if current_password is not None:
                verify_password(actor, current_password)
            user = next((user for user in accounts if user.id == user_id), None)
            if not user:
                raise HTTPException(404, 'User not found.')
            if username != user.username:
                raise HTTPException(400, 'Type the exact username to confirm deletion. Nothing changed.')
            if user.role == 'administrator' and sum(account.role == 'administrator' for account in accounts) <= 1:
                raise HTTPException(409, 'Keep at least one administrator. This account cannot be deleted.')
            if user.id == owner:
                raise HTTPException(400, 'You cannot delete your signed-in account. Ask another administrator.')
            records = list(session.scalars(select(core.Record).where(core.Record.owner == user.id)))
            if any(record.kind not in PRIVATE for record in records):
                raise HTTPException(409, 'This account owns workspace content. Transfer its ownership before deleting the user. Nothing changed.')
            if session.scalar(select(core.Job.id).where(core.Job.owner == user.id).limit(1)):
                raise HTTPException(409, 'This account owns processing jobs. Resolve their ownership before deleting the user. Nothing changed.')

            connection = session.connection()
            grants = list(session.scalars(select(relational.UserDataset).where(relational.UserDataset.user_id == user.id)))
            sessions = list(session.scalars(select(core.Login.id).where(core.Login.owner == user.id)))
            # Save only account/record metadata, never password hashes or session
            # credentials. The payload files remain in their original storage.
            archive = {
                'user': public_user(user), 'deleted_by': owner, 'deleted_at': time.time(),
                'records': [{column.name: getattr(record, column.name) for column in core.Record.__table__.columns} for record in records],
                'dataset_ids': [grant.dataset_id for grant in grants], 'audit_references': [],
            }
            for table in core.Base.metadata.sorted_tables:
                for name in ('created_by', 'updated_by'):
                    if name not in table.c:
                        continue
                    column = table.c[name]
                    references = list(connection.execute(select(*table.primary_key.columns).where(column == user.id)).mappings())
                    if references:
                        archive['audit_references'].append({'table': table.name, 'column': name, 'rows': [dict(row) for row in references]})
            archive_ref = f'account-archives/{user.id}/{core.uid()}.json'
            core.local_store.put_json(archive_ref, archive)
            session.execute(delete(core.Login).where(core.Login.owner == user.id))
            session.execute(delete(relational.UserDataset).where(relational.UserDataset.user_id == user.id))
            connection.execute(core.Record.__table__.delete().where(core.Record.owner == user.id))
            # Historical attribution is retained in the protected archive;
            # nullable FK fields cannot continue to point at a removed account.
            for table in core.Base.metadata.sorted_tables:
                for name in ('created_by', 'updated_by'):
                    if name in table.c:
                        connection.execute(table.update().where(table.c[name] == user.id).values({name: None}))
            session.delete(user)
    return {'ok': True, 'user_id': user_id, 'username': username,
            'sessions_revoked': len(sessions), 'assignments_removed': len(grants),
            'private_records_archived': len(records), 'shared_content_preserved': True}


def install(app, auth):
    def administrator(owner=Depends(auth)):
        with core.Session() as session:
            if not session.get(core.User, owner):
                raise HTTPException(401, 'Sign in required.')
            require_administrator(owner,session)
        return owner

    def require_administrator(owner, session):
        # Recheck after obtaining the mutation lock too: a dependency may have
        # run before another admin demoted this account.
        if not core.is_administrator(owner,session):
            raise HTTPException(403,'Administrator access required.')

    @router.get('/api/users')
    def users(owner=Depends(administrator)):
        with core.Session() as session:
            return [public_user(user) for user in session.scalars(
                select(core.User).order_by(core.User.username))]

    @router.post('/api/users')
    def create_user(body: CreateUser, owner=Depends(administrator)):
        password = matched_password(body)
        with core.document_lock('administrator-auth'), account_audit(owner):
            with core.Session.begin() as session:
                require_administrator(owner,session)
                if session.scalar(select(core.User).where(core.User.username == body.username)):
                    raise HTTPException(409, 'This username already exists. No account was changed.')
                user = core.User(id=core.uid(), username=body.username,
                                 password_hash=core.password_hash(password))
                session.add(user)
                session.flush()
                return public_user(user)

    @router.post('/api/users/{user_id}/password')
    def reset_password(user_id: str, body: ResetPassword, owner=Depends(administrator)):
        if user_id == owner:
            raise HTTPException(400, 'Use Change my password to update your own account.')
        password = matched_password(body)
        with core.document_lock('administrator-auth'), account_audit(owner):
            with core.Session.begin() as session:
                admin = session.get(core.User, owner)
                if not admin:
                    raise HTTPException(401, 'Sign in required.')
                require_administrator(owner,session)
                verify_password(admin, body.current_password.get_secret_value())
                user = session.get(core.User, user_id)
                if not user:
                    raise HTTPException(404, 'User not found.')
                user.password_hash = core.password_hash(password)
                session.execute(delete(core.Login).where(core.Login.owner == user.id))
        return {'ok': True, 'sessions_revoked': True}

    @router.delete('/api/users/{user_id}')
    def delete_user(user_id: str, body: DeleteUser, owner=Depends(administrator)):
        return remove_account(user_id, owner, body.username,
                              current_password=body.current_password.get_secret_value())

    @router.patch('/api/users/{user_id}/role')
    def change_role(user_id: str, body: ChangeRole, response: Response, owner=Depends(administrator)):
        with core.document_lock('administrator-auth'), account_audit(owner):
            with core.Session.begin() as session:
                # Lock in a stable order for Oracle/PostgreSQL across API pods.
                # SQLite uses the shared filesystem lock above.
                accounts=list(session.scalars(select(core.User).order_by(core.User.id).with_for_update()))
                require_administrator(owner,session)
                actor=next(user for user in accounts if user.id==owner)
                verify_password(actor,body.current_password.get_secret_value())
                user=next((user for user in accounts if user.id==user_id),None)
                if not user:raise HTTPException(404,'User not found.')
                if user.role==body.role:return {'user':public_user(user),'sessions_revoked':False}
                if user.role=='administrator' and body.role=='user' and sum(account.role=='administrator' for account in accounts)<=1:
                    raise HTTPException(409,'Keep at least one administrator. Promote another user before changing this role.')
                user.role=body.role
                session.execute(delete(core.Login).where(core.Login.owner==user.id))
                session.flush()
                result=public_user(user)
        if user_id==owner:response.delete_cookie('aegis_session',path='/')
        return {'user':result,'sessions_revoked':True}

    @router.post('/api/auth/password')
    def change_password(body: ResetPassword, response: Response, owner=Depends(auth)):
        password = matched_password(body)
        with core.document_lock('administrator-auth'), account_audit(owner):
            with core.Session.begin() as session:
                user = session.get(core.User, owner)
                if not user:
                    raise HTTPException(401, 'Sign in required.')
                verify_password(user, body.current_password.get_secret_value())
                user.password_hash = core.password_hash(password)
                session.execute(delete(core.Login).where(core.Login.owner == owner))
        response.delete_cookie('aegis_session', path='/')
        return {'ok': True, 'sessions_revoked': True}

    @router.get('/api/users/{user_id}/datasets')
    def assigned_datasets(user_id: str, owner=Depends(administrator)):
        with core.Session() as session:
            user=session.get(core.User,user_id)
            if not user:raise HTTPException(404,'User not found.')
            grants=list(session.scalars(select(relational.UserDataset).where(relational.UserDataset.user_id==user_id)))
            return {'user_id':user_id,'all_datasets':core.is_administrator(user_id,session),'dataset_ids':[grant.dataset_id for grant in grants if grant.enabled],
                    'assignments':[{'dataset_id':grant.dataset_id,'enabled':grant.enabled,'created_at':grant.created_at,'created_by':grant.created_by,'updated_at':grant.updated_at,'updated_by':grant.updated_by} for grant in grants]}

    @router.put('/api/users/{user_id}/datasets')
    def map_datasets(user_id: str, body: DatasetAssignments, owner=Depends(administrator)):
        ids=set(body.dataset_ids)
        if len(ids)!=len(body.dataset_ids):raise HTTPException(400,'Dataset IDs must be unique.')
        with core.document_lock('administrator-auth'), core.document_lock('dataset-access'), account_audit(owner):
            with core.Session.begin() as session:
                require_administrator(owner,session)
                if not session.get(core.User,user_id):raise HTTPException(404,'User not found.')
                if core.is_administrator(user_id,session):raise HTTPException(400,'Administrators always have access to every dataset.')
                found=set(session.scalars(select(relational.Dataset.dataset_id).where(relational.Dataset.dataset_id.in_(ids))))
                if found!=ids:raise HTTPException(404,'One or more datasets no longer exist. No assignments changed.')
                existing={grant.dataset_id:grant for grant in session.scalars(select(relational.UserDataset).where(relational.UserDataset.user_id==user_id))}
                for id,grant in existing.items():
                    if grant.enabled!=(id in ids):grant.enabled=id in ids
                for id in ids-existing.keys():session.add(relational.UserDataset(user_id=user_id,dataset_id=id))
        return {'ok':True,'user_id':user_id,'dataset_ids':sorted(ids)}

    app.include_router(router)
