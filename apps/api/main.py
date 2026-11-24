from __future__ import annotations
import asyncio
import hmac
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from packages.schemas.models import Approval, Corrections, CreateSession, Submit, DemoManifest
from .service import MAX_BYTES, ROOT, Service
from workers.blender.run import find_blender, verify_manifest


class LimitBodyMiddleware:
    """Bound streamed/chunked requests before multipart parsing or disk spooling."""
    def __init__(self, app):
        self.app=app

    async def __call__(self, scope, receive, send):
        if scope['type']!='http':
            return await self.app(scope,receive,send)
        limit=MAX_BYTES+1024*1024
        headers=dict(scope.get('headers',[]))
        try:
            declared=int(headers.get(b'content-length',b'0'))
        except ValueError:
            return await JSONResponse({'detail':'Invalid request length.'},status_code=400)(scope,receive,send)
        if declared>limit:
            return await JSONResponse({'detail':'Choose an image smaller than 10 MB.'},status_code=413)(scope,receive,send)
        consumed=0
        body_complete=False
        body_started=asyncio.get_running_loop().time()
        async def bounded_receive():
            nonlocal consumed,body_complete
            if body_complete:
                return await receive()
            remaining=120-(asyncio.get_running_loop().time()-body_started)
            if remaining<=0:
                raise HTTPException(408,'The upload timed out. Please try again.')
            try:
                message=await asyncio.wait_for(receive(),timeout=min(30,remaining))
            except TimeoutError as exc:
                raise HTTPException(408,'The upload timed out. Please try again.') from exc
            if message['type']=='http.request':
                consumed+=len(message.get('body',b''))
                body_complete=not message.get('more_body',False)
                if consumed>limit:
                    raise HTTPException(413,'Choose an image smaller than 10 MB.')
            return message
        return await self.app(scope,bounded_receive,send)


class PublicFiles(StaticFiles):
    """Only the exported web tree is public; API and dotfiles never fall through."""
    async def get_response(self, path, scope):
        parts=Path(path).parts
        if any(part.startswith('.') for part in parts) or (parts and parts[0] in {'api','docs','redoc','openapi.json'}):
            raise HTTPException(404,'Not found')
        return await super().get_response(path,scope)

def web_configuration():
    mode=os.environ.get('KEEPSAKE_DEPLOYMENT_MODE','local-demo')
    if mode not in {'local-demo','public-demo'}:
        raise ValueError('KEEPSAKE_DEPLOYMENT_MODE must be local-demo or public-demo')
    public=mode=='public-demo'
    configured=os.environ.get('KEEPSAKE_ALLOWED_ORIGIN',os.environ.get('RENDER_EXTERNAL_URL','') if public else 'http://localhost:3000')
    origins=[value.strip().rstrip('/') for value in configured.split(',') if value.strip()]
    for origin in origins:
        parsed=urlsplit(origin)
        if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username or '*' in origin:
            raise ValueError('Allowed origins must be exact HTTP(S) origins without paths or wildcards')
        if public and parsed.scheme!='https' and parsed.hostname not in {'localhost','127.0.0.1','::1'}:
            raise ValueError('Public demo origins must use HTTPS')
    if not public:
        origins=list(dict.fromkeys([*origins,'http://127.0.0.1:3000']))
    hosts={'localhost','127.0.0.1','[::1]'}
    if not public:
        hosts.add('testserver')
    hosts.update(urlsplit(origin).hostname for origin in origins)
    render_host=os.environ.get('RENDER_EXTERNAL_HOSTNAME')
    if render_host:
        hosts.add(render_host)
    hosts.update(value.strip() for value in os.environ.get('KEEPSAKE_ALLOWED_HOSTS','').split(',') if value.strip())
    if any('*' in host or '/' in host for host in hosts):
        raise ValueError('Allowed hosts must be exact host names without wildcards')
    operator=os.environ.get('KEEPSAKE_OPERATOR_TOKEN','')
    if public and operator and len(operator)<32:
        raise ValueError('Public operator token must contain at least 32 random characters')
    return mode,origins,sorted(hosts)


def create_app(data_dir: Path | None = None):
    mode,origins,hosts=web_configuration()
    docs_enabled=os.environ.get("KEEPSAKE_ENABLE_DOCS","0" if mode=="public-demo" else "1")=="1"
    @asynccontextmanager
    async def lifespan(app):
        app.state.service=Service(data_dir)
        yield
        app.state.service.close()
    app=FastAPI(title='Keepsake 3D demo API',version='0.1.0',lifespan=lifespan,
        docs_url='/docs' if docs_enabled else None,redoc_url=None,openapi_url='/openapi.json' if docs_enabled else None,
        description='Private local sessions. Appearance analysis uses explicit mock defaults. Blender outputs are real procedural demo geometry; no production approval or commerce is enabled.')
    app.add_middleware(LimitBodyMiddleware)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=hosts)
    app.add_middleware(CORSMiddleware,allow_origins=origins,allow_methods=['GET','POST','DELETE','OPTIONS'],allow_headers=['Authorization','Content-Type','Idempotency-Key'],allow_credentials=False)

    @app.middleware('http')
    async def privacy_headers(request,call_next):
        is_api=request.url.path.startswith('/api/')
        origin=request.headers.get('origin')
        if is_api and request.method not in {'GET','HEAD','OPTIONS'} and origin and origin not in origins:
            response=JSONResponse({'detail':'This origin is not allowed.'},status_code=403)
        else:
            upload_slot=False
            try:
                if is_api and request.url.path!='/api/v1/health':
                    # Socket client only. Uvicorn runs --no-proxy-headers; untrusted XFF cannot bypass limits.
                    client=request.client.host if request.client else 'unknown'
                    request.app.state.service.rate_limit('api:'+client,240)
                parts=request.url.path.strip('/').split('/')
                if request.method=='POST' and len(parts)==5 and parts[:3]==['api','v1','sessions'] and parts[-1]=='photos':
                    svc=request.app.state.service
                    svc.authorize(parts[3],request.headers.get('authorization'))
                    upload_slot=svc.upload_request_capacity.acquire(blocking=False)
                    if not upload_slot:
                        raise HTTPException(503,'Other photos are being uploaded. Please try again shortly.',headers={'Retry-After':'3'})
                response=await call_next(request)
            except HTTPException as exc:
                response=JSONResponse({'detail':exc.detail},status_code=exc.status_code,headers=exc.headers)
            finally:
                if upload_slot:
                    request.app.state.service.upload_request_capacity.release()
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
        if is_api or request.url.path=='/openapi.json':
            csp="default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        elif docs_enabled and request.url.path=='/docs':
            csp="default-src 'self' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' https://fastapi.tiangolo.com; frame-ancestors 'none'"
        else:
            csp="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self' blob:; font-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        response.headers['Content-Security-Policy']=csp
        if mode=='public-demo':
            response.headers['Strict-Transport-Security']='max-age=31536000'
        return response

    def service(request: Request):
        return request.app.state.service

    def owned(request,sid,authorization):
        svc=service(request);svc.authorize(sid,authorization);return svc

    @app.get('/api/v1/health')
    def health(request:Request):
        svc=service(request)
        with svc.lock:
            svc.db.execute('SELECT 1').fetchone()
        generation_available=False
        try:
            verify_manifest(json.loads((ROOT/'assets/designs/better-together/0.1.0-demo/manifest.json').read_text()))
            generation_available=find_blender() is not None
        except (OSError,ValueError,KeyError):
            pass
        return {'status':'ok','mode':mode,'storage':os.environ.get('KEEPSAKE_STORAGE_MODE','local'),
            'appearance_provider':'mock-defaults-v1','generation_available':generation_available,'production_enabled':False}

    def design():
        path=ROOT/'assets/designs/better-together/0.1.0-demo/manifest.json'
        if path.exists():
            return DemoManifest.model_validate_json(path.read_text()).model_dump()
        return {'design_id':'better-together','version':'0.1.0-demo','status':'DEMO_NOT_PRINT_APPROVED','print_approved':False,'character_slots':['left','right'],'outputs':['glb','stl','png']}

    @app.get('/api/v1/designs')
    def designs():
        return {'designs':[design()]}

    @app.get('/api/v1/designs/better-together')
    def get_design():
        return design()

    @app.post('/api/v1/customization-sessions',status_code=201)
    def new_session(request: Request,body:CreateSession=CreateSession()):
        svc=service(request);svc.rate_limit('create:'+(request.client.host if request.client else 'unknown'),10)
        return svc.create(body.design_id,body.design_version)

    @app.post('/api/v1/sessions/{sid}/photos',status_code=201)
    async def upload(sid:str,request:Request,file:UploadFile=File(...),authorization:str|None=Header(None)):
        svc=owned(request,sid,authorization);svc.rate_limit('upload:'+sid)
        data=await file.read(MAX_BYTES+1)
        await file.close()
        return await run_in_threadpool(svc.upload,sid,data,file.content_type or '')

    @app.post('/api/v1/sessions/{sid}/fixture',status_code=201)
    def fixture(sid:str,request:Request,authorization:str|None=Header(None)):
        svc=owned(request,sid,authorization);svc.rate_limit('upload:'+sid)
        return svc.fixture(sid)

    @app.delete('/api/v1/sessions/{sid}/photos/{pid}',status_code=204)
    def remove_photo(sid:str,pid:str,request:Request,authorization:str|None=Header(None)):
        owned(request,sid,authorization).remove_photo(sid,pid)
        return Response(status_code=204)

    @app.get('/api/v1/sessions/{sid}/photos/{pid}')
    def photo(sid:str,pid:str,request:Request,authorization:str|None=Header(None)):
        path,media,_=owned(request,sid,authorization).file(sid,'photo',pid)
        return FileResponse(path,media_type=media,headers={'Content-Disposition':'inline'})

    @app.post('/api/v1/sessions/{sid}/submit',status_code=202)
    def submit(sid:str,body:Submit,request:Request,authorization:str|None=Header(None),idempotency_key:str|None=Header(None)):
        svc=owned(request,sid,authorization);svc.rate_limit('build:'+sid,8)
        return svc.start(sid,body.names,idempotency_key)

    @app.get('/api/v1/sessions/{sid}/status')
    @app.get('/api/v1/sessions/{sid}/preview')
    def status(sid:str,request:Request,authorization:str|None=Header(None)):
        return owned(request,sid,authorization).status(sid)

    @app.post('/api/v1/sessions/{sid}/corrections',status_code=202)
    def correct(sid:str,body:Corrections,request:Request,authorization:str|None=Header(None),idempotency_key:str|None=Header(None)):
        svc=owned(request,sid,authorization);svc.rate_limit('build:'+sid,8)
        changes=body.model_dump(exclude_none=True)
        if not any(changes['characters'].values()):
            raise HTTPException(422,'Choose at least one supported correction.')
        return svc.start(sid,None,idempotency_key,changes)

    @app.post('/api/v1/sessions/{sid}/approve')
    def approve(sid:str,body:Approval,request:Request,authorization:str|None=Header(None)):
        return owned(request,sid,authorization).approve(sid,body.model_revision,body.job_checksum)

    @app.get('/api/v1/sessions/{sid}/artifacts/{aid}')
    def artifact(sid:str,aid:str,request:Request,authorization:str|None=Header(None)):
        path,media,filename=owned(request,sid,authorization).file(sid,'artifact',aid)
        return FileResponse(path,media_type=media,filename=filename)

    @app.delete('/api/v1/sessions/{sid}',status_code=204)
    def delete(sid:str,request:Request,authorization:str|None=Header(None)):
        owned(request,sid,authorization).delete(sid)
        return Response(status_code=204)

    @app.get('/api/v1/admin/jobs')
    def admin_jobs(request:Request,authorization:str|None=Header(None)):
        expected=os.environ.get('KEEPSAKE_OPERATOR_TOKEN','')
        actual=authorization[7:] if authorization and authorization.startswith('Bearer ') else ''
        if not expected or not hmac.compare_digest(expected,actual):
            raise HTTPException(403,'Operator access is not configured or this token is invalid.')
        svc=service(request)
        with svc.lock:
            rows=[dict(r) for r in svc.db.execute('SELECT id,session_id,revision,state,attempts,created_at,finished_at,error_code FROM build_jobs ORDER BY created_at DESC LIMIT 100')]
        return {'jobs':rows,'production_enabled':False}
    web_dir=os.environ.get('KEEPSAKE_WEB_DIR','')
    if web_dir:
        directory=Path(web_dir).resolve()
        private=(data_dir or Path(os.environ.get('KEEPSAKE_DATA_DIR',ROOT/'.data/private'))).resolve()
        if not (directory/'index.html').is_file():
            raise ValueError('KEEPSAKE_WEB_DIR must contain the exported index.html')
        if directory==ROOT or private.is_relative_to(directory) or directory.is_relative_to(private):
            raise ValueError('Public web assets and private storage must be separate directories')
        app.mount('/',PublicFiles(directory=directory,html=True,follow_symlink=False),name='web')
    return app

app=create_app()
