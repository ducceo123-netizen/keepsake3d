"""Optional paid image generation, isolated from the authored Blender pipeline.

Remote task creation is at-most-once after an ambiguous response. Known remote
IDs can be polled again without generating or charging for another model.
"""
from __future__ import annotations

import fcntl
import hmac
import json
import math
import os
import shutil
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import Field, field_validator

from packages.schemas.models import ConsentModel, OpaqueID, Sha256, StrictModel
from workers.tripo.client import (
    ESTIMATED_CREDITS, MODEL, MODEL_OPTIONS, ProviderError,
    SubmissionUncertain, TripoClient,
)
from .service import ROOT, Service, canonical, digest, env_int, now

ACTIVE = {'QUEUED', 'UPLOADING', 'SUBMITTING', 'GENERATING', 'DOWNLOADING', 'WAITING_FOR_PROVIDER'}
UNCERTAIN = 'SUBMISSION_UNCERTAIN'


class PlanInput(StrictModel):
    photo_id: OpaqueID
    photo_sha256: Sha256


class SubmitInput(ConsentModel):
    plan_id: OpaqueID
    cost_accepted: Literal[True]
    access_code: str = Field(min_length=1, max_length=256, repr=False)

    @field_validator('cost_accepted', mode='before')
    @classmethod
    def explicit_cost(cls, value):
        if value is not True:
            raise ValueError('Explicitly accept the quoted Tripo generation cost')
        return value


class TripoService:
    def __init__(self, sessions: Service, client=None):
        self.sessions = sessions
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='tripo-job')
        self.futures = {}
        self.reconcile_future = None
        self.poll_interval = 2.0
        self.poll_window = 300.0
        self.max_jobs_hour = env_int('TRIPO_MAX_JOBS_PER_HOUR', 3, 1, 3)
        self.api_key = os.environ.get('TRIPO_API_KEY', '')
        self.access_code = os.environ.get('TRIPO_GENERATION_CODE', '')
        configured_dir = os.environ.get('TRIPO_STATE_DIR', '')
        self.root = Path(configured_dir).expanduser().resolve() if configured_dir else sessions.root / 'tripo-state'
        web = os.environ.get('KEEPSAKE_WEB_DIR', '')
        forbidden = [ROOT / 'apps/web/public', ROOT / 'apps/web/out']
        if web:
            forbidden.append(Path(web).resolve())
        if any(self.root == path or self.root.is_relative_to(path) for path in forbidden):
            raise ValueError('Tripo state and artifacts must be private, outside static web assets')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.file_lock = (self.root / '.lock').open('a+')
        try:
            fcntl.flock(self.file_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.file_lock.close()
            self.pool.shutdown(wait=False)
            raise RuntimeError('Tripo state requires exactly one service instance') from exc
        self.db = sqlite3.connect(self.root / 'tripo.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS plans (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL, photo_id TEXT NOT NULL,
                photo_sha256 TEXT NOT NULL, model TEXT NOT NULL, options_json TEXT NOT NULL,
                estimated_credits INTEGER NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS plans_session ON plans(session_id);
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, session_id TEXT UNIQUE NOT NULL, plan_id TEXT NOT NULL,
                input_hash TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                state TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
                photo_id TEXT, photo_sha256 TEXT, model TEXT NOT NULL, options_json TEXT NOT NULL,
                estimated_credits INTEGER NOT NULL, credits_consumed REAL,
                provider_file_token TEXT, provider_task_id TEXT UNIQUE,
                error_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                next_poll_at REAL NOT NULL DEFAULT 0, deleted_at TEXT
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL, kind TEXT NOT NULL,
                filename TEXT NOT NULL, sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS spend_ledger (
                job_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                reserved_credits INTEGER NOT NULL, credits_consumed REAL,
                outcome TEXT NOT NULL, provider_task_id TEXT
            );
        ''')
        if 'provider_task_id' not in {row['name'] for row in self.db.execute('PRAGMA table_info(spend_ledger)')}:
            self.db.execute('ALTER TABLE spend_ledger ADD COLUMN provider_task_id TEXT')
        if 'consent_json' not in {row['name'] for row in self.db.execute('PRAGMA table_info(jobs)')}:
            self.db.execute("ALTER TABLE jobs ADD COLUMN consent_json TEXT NOT NULL DEFAULT '{}'")
        self.db.commit()
        (self.root / 'tripo.sqlite3').chmod(0o600)
        temporary_roots = [Path(path).resolve() for path in ('/tmp', '/var/tmp', '/private/tmp')]
        known_temporary = any(sessions.root.is_relative_to(path) or self.root.is_relative_to(path) for path in temporary_roots)
        self.durable = not sessions.public or (
            os.environ.get('KEEPSAKE_STORAGE_MODE') == 'persistent'
            and os.environ.get('TRIPO_DURABLE_STATE') == '1'
            and self.root.is_relative_to(sessions.root)
            and not known_temporary
        )
        self.client = client
        self.client_error = False
        if self.client is None and self.api_key:
            try:
                self.client = TripoClient(api_key=self.api_key)
            except ProviderError:
                self.client_error = True
        if ESTIMATED_CREDITS > 30:
            raise ValueError('Tripo integration is limited to 30 credits per generation')
        self._recover()
        self.cleaner = threading.Thread(target=self._maintenance, daemon=True, name='tripo-cleanup')
        self.cleaner.start()

    def config(self):
        configured = bool(self.api_key and self.access_code)
        reason = None
        if not self.api_key:
            reason = 'Tripo generation is not configured yet. The site owner must add a server API key.'
        elif not self.access_code:
            reason = 'Tripo generation needs an operator access code before paid jobs can start.'
        elif self.client_error:
            reason = 'The server Tripo credential needs attention before generation is available.'
        elif not self.durable:
            reason = 'Tripo is unavailable on temporary storage. The site owner must configure persistent private sessions, photos, and job storage.'
        return {'configured': configured, 'available': configured and self.durable and not self.client_error,
                'reason': reason, 'model': MODEL, 'estimated_credits': ESTIMATED_CREDITS,
                'requires_access_code': True}

    def _require_available(self):
        config = self.config()
        if not config['available']:
            raise HTTPException(503, config['reason'])

    def _session_exists(self, sid):
        session = self.sessions.get(sid)
        return bool(session and session['expires_at'] >= now())

    def _photo(self, sid, photo_id, sha):
        with self.sessions.lock:
            row = self.sessions.db.execute('SELECT * FROM photos WHERE id=? AND session_id=?', (photo_id, sid)).fetchone()
            if not row or not hmac.compare_digest(row['sha256'], sha):
                raise HTTPException(422, 'Choose a current photo from this private session.')
            path = Path(row['private_path']).resolve()
            if not path.is_relative_to(self.sessions.root / sid) or not path.is_file():
                raise HTTPException(422, 'The selected photo is no longer available.')
            data = path.read_bytes()
            if digest(data) != sha:
                raise HTTPException(409, 'The selected photo changed. Upload it again before generating.')
        return data

    def plan(self, sid, body: PlanInput):
        self._require_available()
        self._photo(sid, body.photo_id, body.photo_sha256)
        with self.lock:
            existing_job = self.db.execute('SELECT id FROM jobs WHERE session_id=?', (sid,)).fetchone()
            if existing_job:
                raise HTTPException(409, 'This session already has a Tripo generation. Check its status; a second paid task will not be created.')
            plans = self.db.execute('SELECT * FROM plans WHERE session_id=? ORDER BY created_at DESC', (sid,)).fetchall()
            for row in plans:
                if row['photo_id'] == body.photo_id and row['photo_sha256'] == body.photo_sha256 and row['expires_at'] > now():
                    return self._plan_result(row)
            if len(plans) >= 20:
                raise HTTPException(429, 'This session has reached its generation planning limit.')
            identifier = uuid.uuid4().hex
            expiry = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
            self.db.execute('INSERT INTO plans VALUES(?,?,?,?,?,?,?,?,?)',
                            (identifier, sid, body.photo_id, body.photo_sha256, MODEL,
                             canonical(MODEL_OPTIONS), ESTIMATED_CREDITS, now(), expiry))
            self.db.commit()
            return self._plan_result(self.db.execute('SELECT * FROM plans WHERE id=?', (identifier,)).fetchone())

    @staticmethod
    def _plan_result(row):
        return {'id': row['id'], 'photo_id': row['photo_id'], 'photo_sha256': row['photo_sha256'],
                'model': row['model'], 'options': json.loads(row['options_json']),
                'estimated_credits': row['estimated_credits'], 'expires_at': row['expires_at']}

    def submit(self, sid, body: SubmitInput, key):
        self._require_available()
        if not hmac.compare_digest(body.access_code.encode(), self.access_code.encode()):
            raise HTTPException(403, 'The Tripo generation access code is incorrect.')
        if not key or not 8 <= len(key) <= 128 or not key.isascii():
            raise HTTPException(422, 'Provide an Idempotency-Key of 8–128 ASCII characters.')
        fingerprint = digest(canonical({'plan_id': body.plan_id, 'consent': True, 'cost_accepted': True}).encode())
        with self.lock:
            prior = self.db.execute('SELECT * FROM jobs WHERE session_id=?', (sid,)).fetchone()
            if prior:
                if prior['input_hash'] == fingerprint:
                    return self.status(sid, resume=False)
                raise HTTPException(409, 'One Tripo generation is allowed per session. Check the existing job instead of submitting another paid task.')
            quote = self.db.execute('SELECT * FROM plans WHERE id=? AND session_id=?', (body.plan_id, sid)).fetchone()
            if not quote or quote['expires_at'] <= now():
                raise HTTPException(409, 'This generation plan expired or is unavailable. Review a new plan.')
            if quote['model'] != MODEL or quote['options_json'] != canonical(MODEL_OPTIONS) or quote['estimated_credits'] != ESTIMATED_CREDITS:
                raise HTTPException(409, 'Generation settings changed. Review a new plan.')
            self._photo(sid, quote['photo_id'], quote['photo_sha256'])
            if not self._session_exists(sid):
                raise HTTPException(404, 'Session not found or expired.')
            # A submission with unknown outcome may still be running remotely.
            if self.db.execute("SELECT 1 FROM spend_ledger WHERE outcome IN ('RESERVED','SUBMITTED','UNCERTAIN')").fetchone():
                raise HTTPException(503, 'Another Tripo generation is active or awaiting confirmation. Please try later.', headers={'Retry-After': '30'})
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            if self.db.execute('SELECT COUNT(*) FROM spend_ledger WHERE created_at>?', (cutoff,)).fetchone()[0] >= self.max_jobs_hour:
                raise HTTPException(429, 'The site has reached its paid generation limit for this hour.', headers={'Retry-After': '3600'})
            self.sessions.check_storage(70 * 1024 * 1024)
            used = sum(path.stat().st_size for path in self.root.rglob('*') if path.is_file())
            if used + 70 * 1024 * 1024 > self.sessions.max_storage:
                raise HTTPException(503, 'Private model storage is full. Try again later.')
            if shutil.disk_usage(self.root).free < 140 * 1024 * 1024:
                raise HTTPException(503, 'Private model storage is full. Try again later.')
            job = uuid.uuid4().hex
            timestamp = now()
            self.db.execute('''INSERT INTO jobs(id,session_id,plan_id,input_hash,idempotency_key,state,
                photo_id,photo_sha256,model,options_json,estimated_credits,created_at,updated_at)
                VALUES(?,?,?,?,?,'QUEUED',?,?,?,?,?,?,?)''',
                (job, sid, body.plan_id, fingerprint, key, quote['photo_id'], quote['photo_sha256'],
                 MODEL, quote['options_json'], ESTIMATED_CREDITS, timestamp, timestamp))
            self.db.execute('INSERT INTO spend_ledger(job_id,created_at,reserved_credits,credits_consumed,outcome) VALUES(?,?,?,?,?)', (job, timestamp, ESTIMATED_CREDITS, None, 'RESERVED'))
            self.db.execute('UPDATE jobs SET consent_json=? WHERE id=?', (canonical({
                'policy': 'tripo-external-v1', 'external_transfer': True,
                'consent': True, 'cost_accepted': True, 'accepted_at': timestamp,
                'estimated_credits': ESTIMATED_CREDITS,
            }), job))
            self.db.commit()
            self._schedule(job)
            return self.status(sid, resume=False)

    def _schedule(self, job):
        if self.stop.is_set() or not self.config()['available']:
            return
        future = self.futures.get(job)
        if future and not future.done():
            return
        self.futures[job] = self.pool.submit(self._run, job)

    def _job(self, job):
        with self.lock:
            row = self.db.execute('SELECT * FROM jobs WHERE id=?', (job,)).fetchone()
            return dict(row) if row else None

    def _live(self, job):
        row = self._job(job)
        return bool(row and not row['deleted_at'] and self._session_exists(row['session_id']))

    def _update(self, job, **fields):
        with self.lock:
            row = self._job(job)
            if not row or row['deleted_at']:
                return False
            fields['updated_at'] = now()
            self.db.execute('UPDATE jobs SET ' + ','.join(f'{name}=?' for name in fields) + ' WHERE id=?', (*fields.values(), job))
            self.db.commit()
            return True

    def _error(self, job, code, message, uncertain=False):
        state = UNCERTAIN if uncertain else 'FAILED'
        with self.lock:
            self._update(job, state=state, error_json=canonical({'code': code, 'message': message}))
            self.db.execute("UPDATE spend_ledger SET outcome=? WHERE job_id=? AND outcome IN ('RESERVED','SUBMITTED','UNCERTAIN')", ('UNCERTAIN' if uncertain else 'FAILED_OR_REJECTED', job))
            self.db.commit()

    def _run(self, job):
        try:
            row = self._job(job)
            if not row or row['deleted_at'] or self.stop.is_set():
                return
            if not self._live(job):
                self.delete_session(row['session_id'])
                return
            if not row['provider_task_id']:
                if row['state'] == 'SUBMITTING':
                    self._error(job, 'TRIPO_SUBMISSION_UNCERTAIN', 'The provider may have accepted this generation. No second paid request was sent. Contact the site owner to reconcile it.', True)
                    return
                if row['model'] != MODEL or row['options_json'] != canonical(MODEL_OPTIONS) or row['estimated_credits'] != ESTIMATED_CREDITS:
                    self._error(job, 'TRIPO_PLAN_CHANGED', 'The server generation settings changed before submission. The quoted task was not sent to Tripo.')
                    return
                if not row['provider_file_token']:
                    self._update(job, state='UPLOADING')
                    data = self._photo(row['session_id'], row['photo_id'], row['photo_sha256'])
                    token = self.client.upload(data, filename='reference.png')
                    if self.stop.is_set() or not self._live(job):
                        return
                    self._update(job, provider_file_token=token)
                else:
                    token = row['provider_file_token']
                if self.stop.is_set() or not self._live(job):
                    return
                # Persist the uncertainty boundary BEFORE the non-idempotent call.
                if not self._update(job, state='SUBMITTING'):
                    return
                task_id = self.client.create(token)
                with self.lock:
                    # Even deletion during the HTTP call must retain its billing ID.
                    self.db.execute('UPDATE jobs SET provider_task_id=? WHERE id=?', (task_id, job))
                    self.db.execute('UPDATE spend_ledger SET outcome=?,provider_task_id=? WHERE job_id=?', ('SUBMITTED', task_id, job))
                    self.db.commit()
                    self._update(job, state='GENERATING')
            else:
                task_id = row['provider_task_id']
            deadline = time.monotonic() + self.poll_window
            while not self.stop.is_set() and self._live(job):
                if time.monotonic() >= deadline:
                    self._update(job, state='WAITING_FOR_PROVIDER', next_poll_at=time.time() + 30,
                                 error_json=canonical({'code': 'TRIPO_STILL_PENDING', 'message': 'Tripo has not finished yet. Refresh status later; no new paid task will be submitted.'}))
                    return
                try:
                    task = self.client.task(task_id)
                except ProviderError:
                    self._update(job, state='WAITING_FOR_PROVIDER', next_poll_at=time.time() + 30,
                                 error_json=canonical({'code': 'TRIPO_STATUS_UNAVAILABLE', 'message': 'The provider status is temporarily unavailable. Refresh later to check the same generation.'}))
                    return
                if task.get('task_id') != task_id:
                    raise ProviderError('The provider returned a mismatched task result.')
                state = task.get('status')
                progress = task.get('progress', 0)
                if not isinstance(progress, int) or isinstance(progress, bool):
                    progress = 0
                self._update(job, state='GENERATING', progress=max(0, min(99, progress)), error_json=None)
                if state == 'success':
                    self._complete(job, task)
                    return
                if state in {'failed', 'cancelled', 'banned', 'expired'}:
                    self._record_cost(job, task, state.upper())
                    self._error(job, 'TRIPO_TASK_FAILED', 'Tripo could not complete this generation. No replacement task was created.')
                    return
                if self.stop.wait(self.poll_interval):
                    return
        except SubmissionUncertain:
            self._error(job, 'TRIPO_SUBMISSION_UNCERTAIN', 'The provider may have accepted this generation. No second paid request was sent. Contact the site owner to reconcile it.', True)
        except ProviderError as exc:
            row = self._job(job)
            fatal_output = {'TRIPO_INVALID_MODEL', 'TRIPO_UNSAFE_DOWNLOAD', 'TRIPO_RESPONSE_TOO_LARGE', 'TRIPO_INVALID_DOWNLOAD', 'TRIPO_MISSING_OUTPUT'}
            if row and row['provider_task_id'] and exc.code in fatal_output:
                self._error(job, 'TRIPO_MODEL_NOT_ACCEPTED', 'Tripo completed this paid generation, but its model could not be safely displayed. The recorded provider charge still applies; no replacement task was created.')
            elif row and row['provider_task_id']:
                self._update(job, state='WAITING_FOR_PROVIDER', next_poll_at=time.time() + 30,
                             error_json=canonical({'code': 'TRIPO_RESULT_UNAVAILABLE', 'message': 'The existing model could not be retrieved yet. Refresh later; no new generation will be charged.'}))
            else:
                self._error(job, 'TRIPO_REQUEST_FAILED', str(exc))
        except Exception:
            row = self._job(job)
            if row and row['state'] == 'SUBMITTING' and not row['provider_task_id']:
                self._error(job, 'TRIPO_SUBMISSION_UNCERTAIN', 'The submission outcome is unknown. No second paid request was sent. Contact the site owner.', True)
            elif row and row['provider_task_id']:
                self._update(job, state='WAITING_FOR_PROVIDER', next_poll_at=time.time() + 30,
                             error_json=canonical({'code': 'TRIPO_RESULT_UNAVAILABLE', 'message': 'This generation needs another status check. Refresh later; no new paid task will be submitted.'}))
            else:
                self._error(job, 'TRIPO_REQUEST_FAILED', 'The photo could not be submitted to Tripo. No automatic paid retry was attempted.')
        finally:
            row = self._job(job)
            if row and not self._session_exists(row['session_id']):
                self.delete_session(row['session_id'])

    def _record_cost(self, job, task, outcome):
        consumed = task.get('credits_consumed')
        if isinstance(consumed, bool) or not isinstance(consumed, (int, float)) or not math.isfinite(consumed) or consumed < 0:
            consumed = None
        with self.lock:
            if consumed is None:
                previous = self.db.execute('SELECT credits_consumed FROM spend_ledger WHERE job_id=?', (job,)).fetchone()
                consumed = previous['credits_consumed'] if previous else None
            self.db.execute('UPDATE spend_ledger SET outcome=?,credits_consumed=? WHERE job_id=?', (outcome, consumed, job))
            self.db.execute('UPDATE jobs SET credits_consumed=? WHERE id=?', (consumed, job))
            self.db.commit()
        return consumed

    def _complete(self, job, task):
        # Billing is established by provider success, independent of whether our
        # artifact ingestion subsequently accepts or can retrieve the output.
        consumed = self._record_cost(job, task, 'SUCCESS')
        self._update(job, state='DOWNLOADING', progress=99)
        if self.stop.is_set() or not self._live(job):
            return
        url = (task.get('output') or {}).get('model_url')
        if not isinstance(url, str):
            raise ProviderError('Tripo did not return a model download.', 'TRIPO_MISSING_OUTPUT')
        blob = self.client.download_model(url)
        if self.stop.is_set() or not self._live(job):
            return
        row = self._job(job)
        glb_sha = digest(blob)
        provenance = {'schema_version': 'tripo-generation-1.0', 'provider': 'tripo',
                      'model': row['model'], 'options': json.loads(row['options_json']),
                      'source_photo_sha256': row['photo_sha256'], 'request_sha256': row['input_hash'],
                      'provider_task_id': row['provider_task_id'], 'external_transfer': True,
                      'consent_policy': 'tripo-external-v1', 'estimated_credits': row['estimated_credits'],
                      'credits_consumed': consumed, 'print_approved': False, 'locked_design_geometry': False,
                      'artifacts': [{'kind': 'glb', 'sha256': glb_sha, 'size_bytes': len(blob)}]}
        provenance['job_checksum'] = digest(canonical(provenance).encode())
        with self.lock:
            if not self._live(job) or self.stop.is_set():
                return
            folder = self.root / 'artifacts' / job
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.db.execute('DELETE FROM artifacts WHERE job_id=?', (job,))
            for kind, filename, data in [('glb', 'model.glb', blob), ('provenance', 'provenance.json', canonical(provenance).encode())]:
                path = folder / filename
                temporary = folder / (filename + '.partial')
                temporary.write_bytes(data)
                temporary.chmod(0o600)
                temporary.replace(path)
                self.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?)', (uuid.uuid4().hex, job, kind, filename, digest(data), len(data)))
            self.db.execute('UPDATE jobs SET state=?,progress=100,credits_consumed=?,error_json=NULL,provider_file_token=NULL,updated_at=? WHERE id=?', ('READY', consumed, now(), job))
            self.db.execute('UPDATE spend_ledger SET outcome=?,credits_consumed=? WHERE job_id=?', ('SUCCESS', consumed, job))
            self.db.commit()

    def status(self, sid, resume=True):
        with self.lock:
            row = self.db.execute('SELECT * FROM jobs WHERE session_id=?', (sid,)).fetchone()
            if not row or row['deleted_at']:
                return {'job_id': None, 'state': 'NOT_STARTED', 'progress': 0, 'provider_task_id': None,
                        'estimated_credits': ESTIMATED_CREDITS, 'credits_consumed': None, 'error': None,
                        'artifacts': [], 'model': MODEL, 'photo_id': None}
            if resume and row['state'] == 'WAITING_FOR_PROVIDER' and row['next_poll_at'] <= time.time():
                self._schedule(row['id'])
            artifacts = [{'id': a['id'], 'kind': a['kind'], 'sha256': a['sha256'], 'size_bytes': a['size_bytes'],
                          'url': f'/api/v1/sessions/{sid}/tripo/artifacts/{a["id"]}'}
                         for a in self.db.execute('SELECT * FROM artifacts WHERE job_id=?', (row['id'],))]
            return {'job_id': row['id'], 'state': row['state'], 'progress': row['progress'],
                    'provider_task_id': row['provider_task_id'], 'estimated_credits': row['estimated_credits'],
                    'credits_consumed': row['credits_consumed'], 'error': json.loads(row['error_json']) if row['error_json'] else None,
                    'artifacts': artifacts, 'model': row['model'], 'photo_id': row['photo_id']}

    def artifact(self, sid, aid):
        with self.lock:
            row = self.db.execute('SELECT a.* FROM artifacts a JOIN jobs j ON a.job_id=j.id WHERE a.id=? AND j.session_id=? AND j.deleted_at IS NULL AND j.state=?', (aid, sid, 'READY')).fetchone()
            if not row:
                raise HTTPException(404, 'Private model file not found.')
            path = self.root / 'artifacts' / row['job_id'] / row['filename']
            if not path.is_file():
                raise HTTPException(404, 'Private model file is no longer available.')
            return path, 'model/gltf-binary' if row['kind'] == 'glb' else 'application/json', row['filename']

    def delete_session(self, sid):
        with self.lock:
            row = self.db.execute('SELECT id,provider_task_id,state FROM jobs WHERE session_id=?', (sid,)).fetchone()
            self.db.execute('DELETE FROM plans WHERE session_id=?', (sid,))
            if row:
                if row['state'] in {'QUEUED', 'UPLOADING'} and not row['provider_task_id']:
                    self.db.execute('UPDATE spend_ledger SET outcome=? WHERE job_id=?', ('CANCELLED_BEFORE_SUBMISSION', row['id']))
                # Preserve only a minimal paid-task tombstone; no photo or model data.
                self.db.execute('UPDATE jobs SET deleted_at=?,state=?,photo_id=NULL,photo_sha256=NULL,provider_file_token=NULL,options_json=?,error_json=NULL WHERE id=?', (now(), 'DELETED', '{}', row['id']))
                self.db.execute('DELETE FROM artifacts WHERE job_id=?', (row['id'],))
                shutil.rmtree(self.root / 'artifacts' / row['id'], ignore_errors=True)
            self.db.commit()

    def _recover(self):
        with self.lock:
            for row in self.db.execute('SELECT * FROM jobs WHERE deleted_at IS NULL').fetchall():
                if not self._session_exists(row['session_id']):
                    self.delete_session(row['session_id'])
                elif row['state'] == 'SUBMITTING' and not row['provider_task_id']:
                    self._error(row['id'], 'TRIPO_SUBMISSION_UNCERTAIN', 'The server restarted while submitting. The provider may have accepted it; no second paid request was sent.', True)
                elif row['state'] in ACTIVE:
                    self._schedule(row['id'])

    def _maintenance(self):
        while not self.stop.wait(30):
            with self.lock:
                sessions = {r['session_id'] for r in self.db.execute('SELECT session_id FROM plans UNION SELECT session_id FROM jobs WHERE deleted_at IS NULL')}
            for sid in sessions:
                if not self._session_exists(sid):
                    self.delete_session(sid)
            # A deleted session must not cause another active provider task to be
            # created. Reconcile only billing status; never retrieve deleted files.
            if self.config()['available'] and not self.stop.is_set():
                if self.reconcile_future is None or self.reconcile_future.done():
                    self.reconcile_future = self.pool.submit(self._reconcile_deleted)

    def _reconcile_deleted(self):
        with self.lock:
            deleted = self.db.execute("SELECT s.job_id,s.provider_task_id FROM spend_ledger s JOIN jobs j ON j.id=s.job_id WHERE j.deleted_at IS NOT NULL AND s.outcome='SUBMITTED'").fetchall()
        for row in deleted:
            if self.stop.is_set():
                break
            try:
                task = self.client.task(row['provider_task_id'])
                if task.get('status') in {'success', 'failed', 'cancelled', 'banned', 'expired'}:
                    self._record_cost(row['job_id'], task, task['status'].upper())
            except ProviderError:
                pass

    def close(self):
        self.stop.set()
        self.cleaner.join(timeout=2)
        self.pool.shutdown(wait=True, cancel_futures=True)
        close = getattr(self.client, 'close', None)
        if close:
            close()
        self.db.close()
        fcntl.flock(self.file_lock, fcntl.LOCK_UN)
        self.file_lock.close()


def install_routes(app):
    def owned(request, sid, authorization):
        request.app.state.service.authorize(sid, authorization)
        return request.app.state.tripo

    @app.get('/api/v1/tripo/config')
    def config(request: Request):
        return request.app.state.tripo.config()

    @app.post('/api/v1/sessions/{sid}/tripo/plan', status_code=201)
    def plan(sid: str, body: PlanInput, request: Request, authorization: str | None = Header(None)):
        svc = owned(request, sid, authorization)
        request.app.state.service.rate_limit('tripo-plan:' + sid, 12)
        return svc.plan(sid, body)

    @app.post('/api/v1/sessions/{sid}/tripo/submit', status_code=202)
    def submit(sid: str, body: SubmitInput, request: Request, authorization: str | None = Header(None), idempotency_key: str | None = Header(None)):
        svc = owned(request, sid, authorization)
        request.app.state.service.rate_limit('tripo-submit:' + sid, 6)
        return svc.submit(sid, body, idempotency_key)

    @app.get('/api/v1/sessions/{sid}/tripo/status')
    def status(sid: str, request: Request, authorization: str | None = Header(None)):
        return owned(request, sid, authorization).status(sid)

    @app.get('/api/v1/sessions/{sid}/tripo/artifacts/{aid}')
    def artifact(sid: str, aid: str, request: Request, authorization: str | None = Header(None)):
        path, media, filename = owned(request, sid, authorization).artifact(sid, aid)
        return FileResponse(path, media_type=media, filename=filename)
