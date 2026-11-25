from __future__ import annotations
import hashlib
import fcntl
import hmac
import io
import json
import os
import secrets
import signal
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError
from packages.schemas.models import Parameters, DemoManifest, AppearanceProfileInput, assert_transition
from packages.schemas.constants import DESIGN_ID, DESIGN_VERSION
from workers.appearance.profiles import merge_parameters, merge_overrides, changed_overrides, describe_fields, provenance_metadata, public_summary
from workers.appearance.mock import extract as extract_technical_fixture

ROOT = Path(__file__).resolve().parents[2]
MAX_BYTES = 10 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000

def env_int(name, default, minimum, maximum):
    value=int(os.environ.get(name,str(default)))
    if not minimum<=value<=maximum:
        raise ValueError(f'{name} must be between {minimum} and {maximum}')
    return value

def now():
    return datetime.now(timezone.utc).isoformat()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)

def digest(data: bytes):
    return hashlib.sha256(data).hexdigest()

def terminate_tree(process, force=False):
    try:
        if os.name == 'posix':
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
        elif force:
            process.kill()
        else:
            process.terminate()
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        terminate_tree(process, True)
    except ProcessLookupError:
        pass

class Service:
    def __init__(self, data_dir: Path | None = None):
        self.root = (data_dir or Path(os.environ.get('KEEPSAKE_DATA_DIR', ROOT / '.data/private'))).resolve()
        self.public=os.environ.get('KEEPSAKE_DEPLOYMENT_MODE','local-demo')=='public-demo'
        if self.root.is_relative_to(ROOT/'apps/web/public') or self.root.is_relative_to(ROOT/'apps/web/out'):
            raise ValueError('Private session storage must not be inside web assets')
        self.max_storage=env_int('KEEPSAKE_MAX_STORAGE_MB',512 if self.public else 2048,64,10240)*1024*1024
        self.max_sessions=env_int('KEEPSAKE_MAX_SESSIONS',100 if self.public else 1000,1,10000)
        self.max_builds_hour=env_int('KEEPSAKE_MAX_BUILDS_PER_HOUR',30 if self.public else 300,1,1000)
        self.max_image_pixels=env_int('KEEPSAKE_MAX_IMAGE_PIXELS',8_000_000 if self.public else 20_000_000,4096,20_000_000)
        self.build_timeout=env_int('KEEPSAKE_BUILD_TIMEOUT_SECONDS',600,60,1200)
        self.build_workers=env_int('KEEPSAKE_BUILD_WORKERS',1,1,2)
        self.max_pending=env_int('KEEPSAKE_MAX_PENDING_BUILDS',2,1,8)
        if self.max_pending<self.build_workers:
            raise ValueError('Pending build capacity must include all running workers')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.instance_lock=(self.root/'.service.lock').open('a+')
        try:
            fcntl.flock(self.instance_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.instance_lock.close()
            raise RuntimeError('This local queue requires exactly one API process per data directory') from exc
        self.lock = threading.RLock()
        self.upload_request_capacity=threading.BoundedSemaphore(2)
        self.image_capacity=threading.BoundedSemaphore(1)
        # On small public demo instances, image decode and Blender share one memory budget.
        self.memory_capacity=threading.BoundedSemaphore(1) if self.public else None
        self.db = sqlite3.connect(self.root / 'keepsake.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript((ROOT / 'migrations/001_local.sql').read_text())
        self.db.executescript((Path(__file__).parent/'migrations/002_appearance_profiles.sql').read_text())
        if 'appearance_profile_id' not in {row['name'] for row in self.db.execute('PRAGMA table_info(build_jobs)')}:
            self.db.execute('ALTER TABLE build_jobs ADD COLUMN appearance_profile_id TEXT REFERENCES appearance_profiles(id) ON DELETE SET NULL')
        self.db.commit()
        (self.root/'keepsake.sqlite3').chmod(0o600)
        self.pool = ThreadPoolExecutor(max_workers=self.build_workers, thread_name_prefix='keepsake-build')
        self.capacity = threading.BoundedSemaphore(self.max_pending)
        self.processes = {}
        self.limits = defaultdict(deque)
        self.stop = threading.Event()
        self.retention = max(1, min(168, int(os.environ.get('KEEPSAKE_RETENTION_HOURS', '24'))))
        # A local process restart must never leave customers spinning forever.
        with self.lock:
            for row in self.db.execute("SELECT id,state,job_id FROM sessions WHERE state IN ('PHOTO_VALIDATING','AI_ANALYZING','PARAMETERS_READY','MODEL_BUILDING','MODEL_RENDERING','QA_RUNNING')"):
                self.db.execute('UPDATE sessions SET state=?,error_json=? WHERE id=?', ('FAILED', canonical({'code':'WORKER_RESTARTED','message':'The local worker restarted. Please try again.'}), row['id']))
                self.db.execute('UPDATE build_jobs SET state=?,error_code=?,finished_at=? WHERE id=?', ('FAILED','WORKER_RESTARTED',now(),row['job_id']))
            self.db.commit()
        self.purge_expired()
        self.cleaner = threading.Thread(target=self._maintenance, daemon=True)
        self.cleaner.start()

    def close(self):
        self.stop.set()
        self.cleaner.join(timeout=2)
        with self.lock:
            for process in list(self.processes.values()):
                terminate_tree(process)
        self.pool.shutdown(wait=True, cancel_futures=True)
        self.db.close()
        fcntl.flock(self.instance_lock,fcntl.LOCK_UN)
        self.instance_lock.close()

    def _maintenance(self):
        while not self.stop.wait(60):
            self.purge_expired()

    def purge_expired(self):
        with self.lock:
            ids = [r['id'] for r in self.db.execute('SELECT id FROM sessions WHERE expires_at < ?', (now(),))]
        for sid in ids:
            self.delete(sid)

    def rate_limit(self, key, count=20, seconds=60):
        with self.lock:
            clock=time.monotonic()
            if key not in self.limits and len(self.limits)>=2048:
                self.limits=defaultdict(deque,{k:v for k,v in self.limits.items() if v and v[-1]>clock-3600})
                if len(self.limits)>=2048:
                    raise HTTPException(429,'The demo is receiving too many requests. Please try again later.',headers={'Retry-After':'60'})
            queue = self.limits[key]
            cutoff = clock-seconds
            while queue and queue[0] < cutoff:
                queue.popleft()
            if len(queue) >= count:
                retry=max(1,int(queue[0]+seconds-clock)+1)
                raise HTTPException(429,'The demo limit has been reached. Please try again later.',headers={'Retry-After':str(retry)})
            queue.append(clock)

    def check_storage(self, additional=0):
        used=0
        for path in self.root.rglob('*'):
            try:
                if path.is_file():
                    used+=path.stat().st_size
            except FileNotFoundError:
                continue
        if used+additional>self.max_storage or shutil.disk_usage(self.root).free<additional+64*1024*1024:
            raise HTTPException(503,'The demo storage is full. Delete an old session or try again after files expire.',headers={'Retry-After':'60'})

    def event(self, sid, action, detail=None):
        self.db.execute('INSERT INTO audit_events(session_id,action,created_at,detail_json) VALUES (?,?,?,?)', (sid, action, now(), canonical(detail or {})))

    def create(self, design_id, version):
        sid, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
        created = now()
        expires = (datetime.now(timezone.utc) + timedelta(hours=self.retention)).isoformat()
        with self.lock:
            self.rate_limit('global:create',60)
            if self.db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]>=self.max_sessions:
                raise HTTPException(503,'The demo has reached its active session limit. Please try again after sessions expire.',headers={'Retry-After':'60'})
            self.check_storage(1024*1024)
            self.db.execute('INSERT INTO sessions(id,token_hash,design_id,design_version,state,created_at,expires_at) VALUES (?,?,?,?,?,?,?)', (sid,digest(token.encode()),design_id,version,'CREATED',created,expires))
            self.event(sid,'CREATED')
            self.db.commit()
        (self.root / sid).mkdir(mode=0o700)
        return {'id':sid,'token':token,'state':'CREATED','revision':0,'expires_at':expires,'retention_hours':self.retention}

    def authorize(self, sid, authorization):
        token = authorization[7:] if authorization and authorization.startswith('Bearer ') else ''
        with self.lock:
            row = self.db.execute('SELECT * FROM sessions WHERE id=?',(sid,)).fetchone()
        if not row or not token or not hmac.compare_digest(row['token_hash'],digest(token.encode())):
            raise HTTPException(404,'Session not found or access has expired.')
        if row['expires_at'] < now():
            self.delete(sid)
            raise HTTPException(410,'This session has expired and its files were deleted. Please start again.')
        return dict(row)

    def get(self,sid):
        with self.lock:
            row = self.db.execute('SELECT * FROM sessions WHERE id=?',(sid,)).fetchone()
            return dict(row) if row else None

    def transition(self,sid,target,detail=None):
        with self.lock:
            row=self.get(sid)
            if not row:
                raise RuntimeError('SESSION_REMOVED')
            if row['state']==target:
                return
            assert_transition(row['state'],target)
            self.db.execute('UPDATE sessions SET state=? WHERE id=?',(target,sid))
            if row['job_id']:
                self.db.execute('UPDATE build_jobs SET state=? WHERE id=?',(target,row['job_id']))
            self.event(sid,target,detail)
            self.db.commit()

    def _normalize_image(self,data:bytes,content_type:str):
        if len(data)>MAX_BYTES:
            raise HTTPException(413,'Choose an image smaller than 10 MB.')
        signatures = {'image/png': data.startswith(b'\x89PNG\r\n\x1a\n'), 'image/jpeg': data.startswith(b'\xff\xd8\xff'), 'image/webp': data[:4]==b'RIFF' and data[8:12]==b'WEBP'}
        if not signatures.get(content_type,False):
            raise HTTPException(415,'Choose a valid JPEG, PNG, or WebP image. File contents must match its format.')
        try:
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {'PNG','JPEG','WEBP'} or getattr(source,'n_frames',1)!=1:
                    raise ValueError('Use a still image')
                width,height=source.size
                if min(width,height)<64 or max(width,height)>6000 or width*height>self.max_image_pixels:
                    raise ValueError('Use an image from 64 to 6000 pixels per side, up to 20 megapixels')
                source.load()
                clean=ImageOps.exif_transpose(source).convert('RGB')
                clean.thumbnail((2048,2048),Image.Resampling.LANCZOS)
                output=io.BytesIO()
                clean.save(output,format='PNG',optimize=True)
                encoded=output.getvalue()
                width,height=clean.size
        except (ValueError,OSError,UnidentifiedImageError,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
            raise HTTPException(422,f'The image could not be safely read. Use a still image from 64 to 6000 pixels per side (up to {self.max_image_pixels//1_000_000} megapixels).') from exc
        return width,height,encoded

    def upload(self,sid,data:bytes,content_type:str,synthetic=False):
        if not self.image_capacity.acquire(blocking=False):
            raise HTTPException(503,'Another image is being prepared. Please try again shortly.',headers={'Retry-After':'3'})
        acquired_memory=False
        try:
            if self.memory_capacity:
                acquired_memory=self.memory_capacity.acquire(blocking=False)
                if not acquired_memory:
                    raise HTTPException(503,'The demo workshop is rendering a model. Please try this photo again shortly.',headers={'Retry-After':'10'})
            width,height,encoded=self._normalize_image(data,content_type)
        finally:
            if acquired_memory:
                self.memory_capacity.release()
            self.image_capacity.release()
        with self.lock:
            row=self.get(sid)
            if not row or row['state'] not in {'CREATED','PHOTO_UPLOADED'}:
                raise HTTPException(409,'Photos can only be changed before you create a preview. Start a new session to change them.')
            if self.db.execute('SELECT COUNT(*) FROM photos WHERE session_id=?',(sid,)).fetchone()[0]>=3:
                raise HTTPException(422,'You can upload up to three photos.')
            self.check_storage(len(encoded))
            pid=uuid.uuid4().hex
            path=self.root / sid / 'photos' / f'{pid}.png'
            path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            path.write_bytes(encoded)
            path.chmod(0o600)
            self.db.execute('INSERT INTO photos VALUES(?,?,?,?,?,?,?,?)',(pid,sid,str(path),width,height,digest(encoded),now(),int(synthetic)))
            self.event(sid,'PHOTO_STORED',{'photo_id':pid,'synthetic':synthetic,'metadata_stripped':True})
            self.db.commit()
            self.transition(sid,'PHOTO_UPLOADED')
        return {'id':pid,'width':width,'height':height,'synthetic':synthetic,'sha256':digest(encoded),'url':f'/api/v1/sessions/{sid}/photos/{pid}'}

    def fixture(self,sid):
        image=Image.new('RGB',(640,480),(250,246,240))
        draw=ImageDraw.Draw(image)
        draw.rounded_rectangle((60,32,580,442),radius=24,fill=(242,222,218))
        for x,color in [(230,(168,93,80)),(410,(95,120,136))]:
            draw.ellipse((x-52,105,x+52,209),fill=(189,143,111))
            draw.rounded_rectangle((x-74,218,x+74,372),radius=40,fill=color)
            draw.arc((x-19,154,x+19,179),0,180,fill=(71,49,43),width=3)
        draw.text((175,398),'SYNTHETIC DEMO — NO REAL PEOPLE',fill=(71,49,43))
        output=io.BytesIO(); image.save(output,format='PNG')
        return self.upload(sid,output.getvalue(),'image/png',True)

    def remove_photo(self,sid,pid):
        with self.lock:
            session=self.get(sid)
            if session['state'] not in {'CREATED','PHOTO_UPLOADED'}:
                raise HTTPException(409,'Start a new session to change photos after generation.')
            photo=self.db.execute('SELECT * FROM photos WHERE id=? AND session_id=?',(pid,sid)).fetchone()
            if not photo:
                raise HTTPException(404,'Photo not found.')
            Path(photo['private_path']).unlink(missing_ok=True)
            self.db.execute('DELETE FROM photos WHERE id=?',(pid,))
            self.event(sid,'PHOTO_DELETED',{'photo_id':pid})
            self.db.commit()
            if self.db.execute('SELECT COUNT(*) FROM photos WHERE session_id=?',(sid,)).fetchone()[0]==0:
                self.transition(sid,'CREATED')

    def _validate_assignments(self,sid,assignments):
        for assignment in assignments.values():
            photo=self.db.execute('SELECT * FROM photos WHERE id=? AND session_id=?',(assignment['photo_id'],sid)).fetchone()
            if not photo or not hmac.compare_digest(photo['sha256'],assignment['photo_sha256']):
                raise HTTPException(422,'The selected photo is missing, changed, or belongs to a different session. Analyze the current photo again.')
            if not Path(photo['private_path']).is_file() or digest(Path(photo['private_path']).read_bytes())!=photo['sha256']:
                raise HTTPException(409,'The stored photo changed. Upload and analyze it again.')
            if assignment['box'][2]*photo['width']<24 or assignment['box'][3]*photo['height']<24:
                raise HTTPException(422,'The selected face is too small. Use a clearer, closer photo.')

    def _store_profile(self,sid,payload,parent_id=None):
        payload=describe_fields(payload)
        input_sha=digest(canonical({'parent_id':parent_id,'payload':payload}).encode())
        existing=self.db.execute('SELECT payload_json FROM appearance_profiles WHERE session_id=? AND input_sha256=?',(sid,input_sha)).fetchone()
        if existing:
            return json.loads(existing['payload_json'])
        count=self.db.execute('SELECT COUNT(*) FROM appearance_profiles WHERE session_id=?',(sid,)).fetchone()[0]
        if count>=32:
            raise HTTPException(429,'This session has reached its appearance review limit. Start a new session.')
        revision=self.db.execute('SELECT COALESCE(MAX(revision),0)+1 FROM appearance_profiles WHERE session_id=?',(sid,)).fetchone()[0]
        profile={'id':uuid.uuid4().hex,'revision':revision,'parent_id':parent_id,'created_at':now(),**payload}
        profile['sha256']=digest(canonical(profile).encode())
        self.db.execute('INSERT INTO appearance_profiles VALUES(?,?,?,?,?,?,?,?)',(profile['id'],sid,revision,parent_id,input_sha,profile['sha256'],canonical(profile),profile['created_at']))
        self.event(sid,'APPEARANCE_PROFILE_SAVED',{'profile_id':profile['id'],'profile_revision':revision,'source':profile['source'],'external_transfer':False})
        self.db.commit()
        return profile

    def _get_profile(self,sid,profile_id,expected_sha=None):
        row=self.db.execute('SELECT payload_json,profile_sha256 FROM appearance_profiles WHERE id=? AND session_id=?',(profile_id,sid)).fetchone()
        if not row:
            raise HTTPException(404,'Appearance profile not found in this session.')
        if expected_sha and not hmac.compare_digest(expected_sha,row['profile_sha256']):
            raise HTTPException(409,'The appearance profile changed. Review it again before generation.')
        profile=json.loads(row['payload_json'])
        if profile.get('sha256')!=row['profile_sha256'] or digest(canonical({key:value for key,value in profile.items() if key!='sha256'}).encode())!=row['profile_sha256']:
            raise HTTPException(409,'The stored appearance profile failed its integrity check. Analyze the photos again.')
        return profile

    def save_appearance_profile(self,sid,body):
        payload=AppearanceProfileInput.model_validate(body).model_dump(exclude_none=True)
        with self.lock:
            session=self.get(sid)
            normalized=describe_fields({**payload,'consent_policy':'browser-local-v1','external_transfer':False})
            fingerprint=digest(canonical({'parent_id':None,'payload':normalized}).encode())
            previous=self.db.execute('SELECT id FROM appearance_profiles WHERE session_id=? AND input_sha256=?',(sid,fingerprint)).fetchone()
            if previous:
                self._validate_assignments(sid,normalized['assignments'])
                return self._get_profile(sid,previous['id'])
            if not session or session['state'] not in {'PHOTO_UPLOADED','FAILED','PREVIEW_READY','CUSTOMER_APPROVED','MANUAL_REVIEW_REQUIRED'}:
                raise HTTPException(409,'Wait for the current operation before reviewing another appearance.')
            self._validate_assignments(sid,payload['assignments'])
            params=payload['parameters']
            if merge_parameters(params,payload['manual_overrides'])!=params:
                raise HTTPException(422,'Manual overrides must match the reviewed parameters.')
            payload.update({'consent_policy':'browser-local-v1','external_transfer':False})
            profile=self._store_profile(sid,payload)
            self.db.execute('UPDATE sessions SET consent_at=COALESCE(consent_at,?) WHERE id=?',(now(),sid))
            self.db.commit()
            return profile

    def appearance_profile(self,sid,profile_id):
        with self.lock:
            return self._get_profile(sid,profile_id)

    def _derived_profile(self,sid,profile,params,overrides):
        if profile['parameters']==params:
            return profile
        payload={key:value for key,value in profile.items() if key not in {'id','revision','sha256','parent_id','created_at'}}
        payload['parameters']=params
        payload['manual_overrides']=merge_overrides(profile.get('manual_overrides',{}),changed_overrides(profile['parameters'],overrides))
        return self._store_profile(sid,payload,parent_id=profile['id'])

    def start(self,sid,names,key,corrections=None,profile_id=None,profile_sha256=None,mode='photo'):
        if not key or not 8<=len(key)<=128 or not key.isascii():
            raise HTTPException(422,'Provide an Idempotency-Key of 8–128 ASCII characters.')
        fingerprint=digest(canonical({'names':names,'corrections':corrections,'profile_id':profile_id,'profile_sha256':profile_sha256,'mode':mode}).encode())
        with self.lock:
            previous=self.db.execute('SELECT * FROM build_jobs WHERE session_id=? AND idempotency_key=?',(sid,key)).fetchone()
            if previous:
                if previous['input_hash']!=fingerprint:
                    raise HTTPException(409,'This idempotency key was already used with different input.')
                return self.status(sid)
            row=self.get(sid)
            if not row:
                raise HTTPException(404,'Session not found.')
            if row['design_version']!=DESIGN_VERSION:
                raise HTTPException(409,'Start a new session for the current version of this design.')
            allowed={'PHOTO_UPLOADED','PREVIEW_READY','CUSTOMER_APPROVED','FAILED','MANUAL_REVIEW_REQUIRED'}
            if row['state'] not in allowed:
                raise HTTPException(409,'This session is already processing. Wait for the current preview.')
            photos=list(self.db.execute('SELECT * FROM photos WHERE session_id=?',(sid,)))
            if not photos:
                raise HTTPException(422,'Add at least one photo and analyze both selected people.')
            if corrections is not None:
                previous_appearance=json.loads(row['appearance_json']) if row['appearance_json'] else {}
                if not row['params_json'] or not previous_appearance.get('profile_id'):
                    raise HTTPException(409,'No reviewed appearance is available for correction.')
                profile=self._get_profile(sid,previous_appearance['profile_id'])
                self._validate_assignments(sid,profile.get('assignments',{}))
                params=merge_parameters(json.loads(row['params_json']),corrections)
                profile=self._derived_profile(sid,profile,params,corrections)
            elif mode=='technical-fixture':
                if not all(photo['synthetic'] for photo in photos):
                    raise HTTPException(422,'Technical fixture mode accepts only the explicitly generated synthetic fixture, never uploaded photos.')
                params,_=extract_technical_fixture(names)
                params=params.model_dump()
                profile=self._store_profile(sid,{'source':'technical-fixture','analysis_version':'1.0','reviewed':True,'consent':True,'consent_policy':'technical-fixture-v1','external_transfer':False,'assignments':{},'observations':{},'manual_overrides':{},'parameters':params})
            else:
                if not profile_id or not profile_sha256:
                    raise HTTPException(422,'Analyze and review both people before generating your model. Photo mode never falls back to demo defaults.')
                profile=self._get_profile(sid,profile_id,profile_sha256)
                if profile['source']!='browser-mediapipe-v1':
                    raise HTTPException(422,'Photo mode requires a reviewed browser analysis profile.')
                self._validate_assignments(sid,profile['assignments'])
                params=profile['parameters']
                if names is not None:
                    name_changes={'characters':{'left':{'engraving_text':names[0].strip()},'right':{'engraving_text':names[1].strip()}}}
                    named=merge_parameters(params,name_changes)
                    profile=self._derived_profile(sid,profile,named,name_changes)
                    params=named
            appearance=public_summary(profile)
            attempts=self.db.execute('SELECT COUNT(*) FROM build_jobs WHERE session_id=?',(sid,)).fetchone()[0]
            if attempts>=12:
                raise HTTPException(429,'This demo session has reached its 12-build limit. Start a new session.')
            self.check_storage(64*1024*1024*self.max_pending)
            if not self.capacity.acquire(blocking=False):
                raise HTTPException(503,'The workshop is busy. Please try again shortly.',headers={'Retry-After':'10'})
            try:
                self.rate_limit('global:build',self.max_builds_hour,3600)
                job=uuid.uuid4().hex
                previous_profile=(json.loads(row['appearance_json']) if row['appearance_json'] else {}).get('profile_sha256')
                retry_same=row['state']=='FAILED' and row['params_json']==canonical(params) and previous_profile==profile['sha256']
                revision=row['revision'] if retry_same else row['revision']+1
                attempt=self.db.execute('SELECT COUNT(*) FROM build_jobs WHERE session_id=? AND revision=?',(sid,revision)).fetchone()[0]+1
                if attempt>3:
                    raise HTTPException(429,'This revision has reached its three-attempt limit. Change a supported detail or start a new session.')
                self.db.execute('INSERT INTO build_jobs(id,session_id,revision,state,input_hash,idempotency_key,attempts,created_at,appearance_profile_id) VALUES(?,?,?,?,?,?,?,?,?)',(job,sid,revision,row['state'],fingerprint,key,attempt,now(),profile['id']))
                self.db.execute('UPDATE sessions SET revision=?,job_id=?,params_json=?,appearance_json=?,consent_at=COALESCE(consent_at,?),checksum=NULL,error_json=NULL WHERE id=?',(revision,job,canonical(params),canonical(appearance),now(),sid))
                self.event(sid,'CONSENT_RECORDED' if corrections is None else 'CORRECTION_REQUESTED',{'revision':revision,'policy':profile['consent_policy'],'external_transfer':False,'profile_id':profile['id']})
                self.db.commit()
                self.transition(sid,'PARAMETERS_READY',{'source':profile['source'],'browser_reviewed':profile['reviewed']})
                self.pool.submit(self._build,sid,job,revision,params,provenance_metadata(profile))
            except Exception:
                self.capacity.release()
                raise
        return self.status(sid)

    def _advance(self,sid,target):
        stages=['PARAMETERS_READY','MODEL_BUILDING','MODEL_RENDERING','QA_RUNNING']
        row=self.get(sid)
        if not row or row['state'] not in stages or target not in stages:
            return
        current=stages.index(row['state'])
        for state in stages[current+1:stages.index(target)+1]:
            self.transition(sid,state)

    def _build(self,sid,job,revision,params,appearance_metadata):
        folder=self.root/sid/'jobs'/job
        acquired_memory=False
        try:
            if self.memory_capacity:
                while not self.memory_capacity.acquire(timeout=.25):
                    if self.stop.is_set() or not self.get(sid):
                        raise RuntimeError('SESSION_REMOVED')
                acquired_memory=True
            folder.mkdir(mode=0o700,parents=True,exist_ok=True)
            source=folder/'params.json'
            source.write_text(canonical(params))
            appearance_path=folder/'appearance.json'
            appearance_path.write_text(canonical(appearance_metadata))
            self.transition(sid,'MODEL_BUILDING')
            command=[sys.executable,str(ROOT/'workers/blender/run.py'),'--params',str(source),'--output',str(folder),'--revision',str(revision),'--appearance',str(appearance_path)]
            with (folder/'worker.log').open('w') as logs:
                process=subprocess.Popen(command,cwd=ROOT,stdout=logs,stderr=subprocess.STDOUT,start_new_session=True)
                with self.lock:
                    self.processes[sid]=process
                start=time.monotonic()
                while process.poll() is None:
                    if not self.get(sid) or self.stop.is_set():
                        terminate_tree(process)
                        raise RuntimeError('SESSION_REMOVED')
                    if time.monotonic()-start>self.build_timeout:
                        terminate_tree(process, True)
                        raise RuntimeError('BUILD_TIMEOUT')
                    try:
                        progress=json.loads((folder/'progress.json').read_text())
                        self._advance(sid,progress.get('state'))
                    except (OSError,json.JSONDecodeError):
                        pass
                    time.sleep(0.25)
                if process.returncode:
                    logs.flush()
                    logged=(folder/'worker.log').read_text(errors='replace')
                    if 'BLENDER_UNAVAILABLE' in logged or 'BLENDER_NOT_FOUND' in logged or 'Blender not found' in logged or 'No Blender' in logged:
                        raise RuntimeError('BLENDER_NOT_FOUND')
                    if 'BLENDER_TIMEOUT' in logged:
                        raise RuntimeError('BUILD_TIMEOUT')
                    raise RuntimeError('BUILD_FAILED')
            self._advance(sid,'QA_RUNNING')
            self._accept_artifacts(sid,job,revision,folder,params,appearance_metadata)
        except Exception as exc:
            code=str(exc) if str(exc) in {'BUILD_TIMEOUT','BLENDER_NOT_FOUND','BUILD_FAILED','PROVENANCE_MISMATCH','QA_FAILED'} else 'BUILD_FAILED'
            messages={
                'BLENDER_NOT_FOUND':'Blender is not installed. Follow the setup guide, then retry this preview.',
                'BUILD_TIMEOUT':'This model took too long to build. Please retry or check the local worker.',
                'BUILD_FAILED':'The local model worker could not finish. Check the private worker log, then retry.',
                'PROVENANCE_MISMATCH':'The model outputs did not match this revision. Please retry; no preview was approved.',
                'QA_FAILED':'This model did not pass the demo geometry checks. Please adjust or retry.',
            }
            with self.lock:
                row=self.get(sid)
                if row:
                    self.db.execute('UPDATE sessions SET error_json=? WHERE id=?',(canonical({'code':code,'message':messages[code]}),sid))
                    self.db.execute('UPDATE build_jobs SET error_code=?,finished_at=? WHERE id=?',(code,now(),job))
                    self.db.commit()
                    if row['state'] not in {'FAILED','CANCELLED','EXPIRED'}:
                        self.transition(sid,'FAILED',{'code':code})
        finally:
            if acquired_memory:
                self.memory_capacity.release()
            with self.lock:
                self.processes.pop(sid,None)
                exists=self.get(sid) is not None
            if not exists:
                shutil.rmtree(self.root/sid,ignore_errors=True)
            self.capacity.release()

    def _accept_artifacts(self,sid,job,revision,folder,params,appearance_metadata=None):
        provenance=json.loads((folder/'provenance.json').read_text())
        qa=json.loads((folder/'qa.json').read_text())
        manifest=DemoManifest.model_validate_json((ROOT/f'assets/designs/{DESIGN_ID}/{DESIGN_VERSION}/manifest.json').read_text()).model_dump()
        params_sha=digest(canonical(params).encode())
        if any((
            provenance.get('model_revision') != revision,
            provenance.get('design_id') != DESIGN_ID,
            provenance.get('design_version') != DESIGN_VERSION,
            provenance.get('params_sha256') != params_sha,
            provenance.get('master_sha256') != manifest['master_sha256'],
            provenance.get('same_scene_export') is not True,
            provenance.get('status') != 'DEMO_NOT_PRINT_APPROVED',
            appearance_metadata is not None and provenance.get('appearance_profile')!=appearance_metadata,
        )):
            raise RuntimeError('PROVENANCE_MISMATCH')
        master=(ROOT/manifest['master_blend_asset']).resolve()
        if not master.is_relative_to(ROOT/'assets/designs') or digest(master.read_bytes())!=manifest['master_sha256']:
            raise RuntimeError('PROVENANCE_MISMATCH')
        claimed=provenance.get('artifacts',[])
        expected={'glb':'model.glb','stl':'model.stl','png':'preview.png','qa':'qa.json'}
        if len(claimed)!=len(expected) or {a.get('kind') for a in claimed}!=set(expected):
            raise RuntimeError('PROVENANCE_MISMATCH')
        for artifact in claimed:
            filename=expected[artifact['kind']]
            path=folder/filename
            if any((artifact.get('filename')!=filename,
                    artifact.get('model_revision')!=revision,
                    artifact.get('params_sha256')!=params_sha,
                    artifact.get('master_sha256')!=manifest['master_sha256'],
                    artifact.get('sha256')!=digest(path.read_bytes()),
                    artifact.get('bytes')!=path.stat().st_size)):
                raise RuntimeError('PROVENANCE_MISMATCH')
        if (folder/'model.glb').read_bytes()[:4]!=b'glTF' or not (folder/'model.stl').stat().st_size or (folder/'preview.png').read_bytes()[:8]!=b'\x89PNG\r\n\x1a\n':
            raise RuntimeError('PROVENANCE_MISMATCH')
        with self.lock:
            if self.get(sid):
                self.db.execute('INSERT OR REPLACE INTO qa_reports VALUES(?,?)',(job,canonical(qa)))
                self.db.commit()
        if qa.get('passed') is not True or qa.get('result')!='DEMO_GEOMETRY_CHECKED' or qa.get('print_approved') is not False:
            raise RuntimeError('QA_FAILED')
        checksum=provenance.get('job_checksum')
        unsigned={key:value for key,value in provenance.items() if key!='job_checksum'}
        if checksum!=digest(canonical(unsigned).encode()):
            raise RuntimeError('PROVENANCE_MISMATCH')
        with self.lock:
            if not self.get(sid):
                return
            for kind,name in [('glb','model.glb'),('stl','model.stl'),('png','preview.png'),('provenance','provenance.json'),('qa','qa.json')]:
                path=folder/name
                sha=digest(path.read_bytes())
                path.chmod(0o600)
                self.db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,job,kind,str(path),sha,revision,canonical({'master_sha256':provenance.get('master_sha256'),'params_sha256':provenance.get('params_sha256'),'engine_version':provenance.get('engine_version'),'design_version':DESIGN_VERSION,'production_approved':False})))
            self.db.execute('INSERT OR REPLACE INTO qa_reports VALUES(?,?)',(job,canonical(qa)))
            self.db.execute('UPDATE sessions SET checksum=? WHERE id=?',(checksum,sid))
            self.db.execute('UPDATE build_jobs SET finished_at=? WHERE id=?',(now(),job))
            self.db.commit()
            self.transition(sid,'PREVIEW_READY',{'revision':revision,'production_approved':False})

    def status(self,sid):
        with self.lock:
            row=self.get(sid)
            if not row:
                raise HTTPException(404,'Session not found.')
            photos=[{'id':p['id'],'width':p['width'],'height':p['height'],'synthetic':bool(p['synthetic']),'sha256':p['sha256'],'url':f'/api/v1/sessions/{sid}/photos/{p["id"]}'} for p in self.db.execute('SELECT * FROM photos WHERE session_id=? ORDER BY created_at',(sid,))]
            artifacts=[{'id':a['id'],'kind':a['kind'],'sha256':a['sha256'],'revision':a['revision'],'metadata':json.loads(a['metadata_json']),'url':f'/api/v1/sessions/{sid}/artifacts/{a["id"]}'} for a in self.db.execute('SELECT * FROM artifacts WHERE job_id=?',(row['job_id'],))]
            qa=self.db.execute('SELECT report_json FROM qa_reports WHERE job_id=?',(row['job_id'],)).fetchone()
            history=[{'state':e['action'],'at':e['created_at'],'detail':json.loads(e['detail_json'])} for e in self.db.execute('SELECT * FROM audit_events WHERE session_id=? ORDER BY id',(sid,))]
        return {'id':sid,'state':row['state'],'revision':row['revision'],'job_id':row['job_id'],'error':json.loads(row['error_json']) if row['error_json'] else None,'photos':photos,'params':json.loads(row['params_json']) if row['params_json'] else None,'appearance':json.loads(row['appearance_json']) if row['appearance_json'] else None,'artifacts':artifacts,'qa':json.loads(qa['report_json']) if qa else None,'checksum':row['checksum'],'history':history,'expires_at':row['expires_at'],'quality_level':'DEMO','production_approved':False}

    def approve(self,sid,revision,checksum):
        with self.lock:
            row=self.get(sid)
            if row['revision']!=revision or not row['checksum'] or not hmac.compare_digest(row['checksum'],checksum):
                raise HTTPException(409,'The preview changed. Review the current revision before approving it.')
            if row['state']=='CUSTOMER_APPROVED':
                return self.status(sid)
            if row['state']!='PREVIEW_READY':
                raise HTTPException(409,'Wait until this model is ready for review.')
            self.transition(sid,'CUSTOMER_APPROVED',{'revision':revision,'checksum':checksum,'production_approved':False})
        return self.status(sid)

    def file(self,sid,kind,fid):
        with self.lock:
            if kind=='photo':
                row=self.db.execute('SELECT private_path FROM photos WHERE id=? AND session_id=?',(fid,sid)).fetchone()
                media='image/png';filename='reference.png'
            else:
                row=self.db.execute('SELECT a.* FROM artifacts a JOIN build_jobs b ON a.job_id=b.id WHERE a.id=? AND b.session_id=?',(fid,sid)).fetchone()
                media={'glb':'model/gltf-binary','stl':'model/stl','png':'image/png','qa':'application/json','provenance':'application/json'}.get(row['kind'] if row else '', 'application/octet-stream')
                filename=Path(row['private_path']).name if row else ''
            if not row:
                raise HTTPException(404,'File not found.')
            path=Path(row['private_path']).resolve()
            if not path.is_relative_to(self.root/sid) or not path.is_file():
                raise HTTPException(404,'File not found.')
        return path,media,filename

    def delete(self,sid):
        with self.lock:
            process=self.processes.get(sid)
            if process:
                terminate_tree(process)
            self.db.execute('DELETE FROM sessions WHERE id=?',(sid,))
            self.db.commit()
        shutil.rmtree(self.root/sid,ignore_errors=True)
