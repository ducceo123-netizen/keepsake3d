"""All provider traffic is mocked; these tests never upload or spend credits."""
import copy
import io
import json
import struct

import httpx
import pytest
from PIL import Image

from workers.tripo.client import (
    ESTIMATED_CREDITS, MODEL, MODEL_OPTIONS, ProviderError, SubmissionUncertain,
    TripoClient, validate_glb,
)


def png():
    buffer = io.BytesIO()
    Image.new('RGB', (32, 32), 'green').save(buffer, 'PNG')
    return buffer.getvalue()


def glb_document():
    binary = struct.pack('<9f', 0, 0, 0, 1, 0, 0, 0, 1, 0)
    doc = {
        'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
        'nodes': [{'mesh': 0}], 'meshes': [{'primitives': [{'attributes': {'POSITION': 0}}]}],
        'buffers': [{'byteLength': len(binary)}],
        'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(binary)}],
        'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3'}],
    }
    return doc, binary


def pack_glb(doc=None, binary=None):
    default_doc, default_binary = glb_document()
    doc = default_doc if doc is None else doc
    binary = default_binary if binary is None else binary
    raw = json.dumps(doc, separators=(',', ':')).encode()
    raw += b' ' * (-len(raw) % 4)
    binary += b'\0' * (-len(binary) % 4)
    return (struct.pack('<4sII', b'glTF', 2, 28 + len(raw) + len(binary))
            + struct.pack('<II', len(raw), 0x4E4F534A) + raw
            + struct.pack('<II', len(binary), 0x004E4942) + binary)


def client(handler, **kwargs):
    return TripoClient('test-server-secret', transport=httpx.MockTransport(handler),
                       resolver=kwargs.get('resolver', lambda host: ['93.184.216.34']))


def test_fixed_plan_upload_create_task_download_and_no_download_auth():
    requests = []
    model = pack_glb()
    def handler(request):
        requests.append(request)
        if request.url.path == '/v3/files':
            assert request.headers['authorization'] == 'Bearer test-server-secret'
            assert 'multipart/form-data' in request.headers['content-type']
            assert b'filename="reference.png"' in request.read()
            assert b'secret-user-filename' not in request.read()
            return httpx.Response(200, json={'code': 0, 'data': {'file_token': 'file_test'}})
        if request.url.path == '/v3/generation/image-to-model':
            assert json.loads(request.read()) == {'input': 'file_test', **MODEL_OPTIONS}
            return httpx.Response(200, json={'code': 0, 'data': {'task_id': 'task-test'}})
        if request.url.path == '/v3/tasks/task-test':
            return httpx.Response(200, json={'code': 0, 'data': {
                'task_id': 'task-test', 'status': 'success', 'progress': 100,
                'credits_consumed': 30.25, 'output': {'model_url': 'https://cdn.tripo3d.ai/output/model.glb'},
                'private_provider_field': 'not passed through',
            }})
        assert request.url.host == '93.184.216.34'
        assert request.headers['host'] == 'cdn.tripo3d.ai'
        assert request.extensions['sni_hostname'] == 'cdn.tripo3d.ai'
        assert 'authorization' not in request.headers
        assert 'cookie' not in request.headers
        return httpx.Response(200, content=model)
    with client(handler) as provider:
        token = provider.upload(png(), filename='secret-user-filename.png')
        task_id = provider.create(token)
        task = provider.task(task_id)
        assert task['credits_consumed'] == 30.25
        assert 'private_provider_field' not in task
        assert provider.download_model(task['output']['model_url']) == model
    assert len(requests) == 4
    assert MODEL == 'v3.1-20260211' and ESTIMATED_CREDITS == 30
    assert MODEL_OPTIONS['face_limit'] == 50000
    assert not any(option in MODEL_OPTIONS for option in ('quad', 'smart_low_poly', 'generate_parts', 'geometry_quality'))


@pytest.mark.parametrize('response', [
    httpx.Response(500, text='test-server-secret'),
    httpx.Response(502, json={'code': 1000}),
    httpx.Response(200, text='not JSON test-server-secret'),
    httpx.Response(200, json={'code': 0, 'data': {}}),
    httpx.Response(200, json={'code': 0, 'data': {'task_id': '../bad'}}),
    httpx.Response(200, json={'code': 0, 'data': []}),
    httpx.Response(200, json={'code': 0, 'data': {'task_id': 'ok'}}, headers={'content-length': str(2**24)}),
    httpx.Response(307, headers={'location': 'https://evil.example/steal'}),
])
def test_uncertain_submission_never_retried(response):
    calls = []
    def handler(request):
        calls.append(request)
        return response
    with client(handler) as provider, pytest.raises(SubmissionUncertain) as error:
        provider.create('file_input')
    assert len(calls) == 1
    assert 'test-server-secret' not in str(error.value)


def test_network_ambiguity_and_upload_failure_are_distinct():
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout('contains test-server-secret', request=request)
    with client(handler) as provider:
        with pytest.raises(SubmissionUncertain):
            provider.create('file_test')
        with pytest.raises(ProviderError) as error:
            provider.upload(png())
        assert not isinstance(error.value, SubmissionUncertain)
        assert error.value.__cause__ is None
        assert 'test-server-secret' not in str(error.value)
    assert len(calls) == 2


@pytest.mark.parametrize('code,status', [(2010, 403), (1007, 429), (1004, 400), (2, 401), (2008, 400)])
def test_definitive_rejection_no_retry_and_redacted_error(code, status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={'code': code, 'message': 'test-server-secret'})
    with client(handler) as provider, pytest.raises(ProviderError) as error:
        provider.create('file_test')
    assert not isinstance(error.value, SubmissionUncertain)
    assert error.value.code == code
    assert 'test-server-secret' not in str(error.value)
    assert len(calls) == 1


def test_missing_key_fails_before_any_network(monkeypatch):
    monkeypatch.delenv('TRIPO_API_KEY', raising=False)
    with pytest.raises(ProviderError, match='not configured'):
        TripoClient()
    monkeypatch.setenv('TRIPO_API_KEY', 'environment-secret')
    with TripoClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'code': 0, 'data': {'task_id': 'ok'}}))) as provider:
        assert provider.create('file_test') == 'ok'


@pytest.mark.parametrize('url', [
    'http://cdn.tripo3d.ai/model.glb', 'https://127.0.0.1/model.glb',
    'https://cdn.tripo3d.ai.evil.example/model.glb', 'https://eviltripo3d.ai/model.glb',
    'https://cdn.tripo3d.ai:444/model.glb', 'https://user:password@cdn.tripo3d.ai/model.glb',
    'https://cdn.tripo3d.ai/model.glb#fragment', 'https://cdn.tripo3d.ai\\@evil.example/model.glb',
    'file:///private/model.glb', 'https://arbitrary-bucket.s3.amazonaws.com/model.glb',
])
def test_ssrf_url_rejected_before_request(url):
    def handler(_):
        pytest.fail('Unsafe URL reached transport')
    with client(handler) as provider, pytest.raises(ProviderError) as error:
        provider.download_model(url)
    assert error.value.code == 'TRIPO_UNSAFE_DOWNLOAD'


@pytest.mark.parametrize('addresses', [[], ['127.0.0.1'], ['10.0.0.1'], ['169.254.169.254'], ['::1'], ['fc00::1'], ['93.184.216.34', '10.0.0.1']])
def test_ssrf_dns_rejected_before_request(addresses):
    def handler(_):
        pytest.fail('Private address reached transport')
    with client(handler, resolver=lambda _: addresses) as provider, pytest.raises(ProviderError):
        provider.download_model('https://cdn.tripo3d.ai/model.glb')


def test_dns_is_checked_once_and_pinned():
    resolutions = []
    def resolver(host):
        resolutions.append(host)
        return ['93.184.216.34'] if len(resolutions) == 1 else ['127.0.0.1']
    def handler(request):
        assert request.url.host == '93.184.216.34'
        assert request.extensions['sni_hostname'] == 'cdn.tripo3d.ai'
        return httpx.Response(200, content=pack_glb())
    with client(handler, resolver=resolver) as provider:
        provider.download_model('https://cdn.tripo3d.ai/model.glb?signature=private')
    assert len(resolutions) == 1


def test_download_redirect_never_followed_and_no_bearer():
    calls = []
    def handler(request):
        calls.append(request)
        assert 'authorization' not in request.headers
        return httpx.Response(302, headers={'location': 'http://169.254.169.254/latest/meta-data'})
    with client(handler) as provider, pytest.raises(ProviderError):
        provider.download_model('https://cdn.tripo3d.ai/model.glb')
    assert len(calls) == 1


def test_size_and_encoding_limits(monkeypatch):
    import workers.tripo.client as module
    monkeypatch.setattr(module, 'MAX_MODEL_BYTES', 128)
    with client(lambda _: httpx.Response(200, content=b'x' * 129)) as provider, pytest.raises(ProviderError):
        provider.download_model('https://cdn.tripo3d.ai/model.glb')
    with client(lambda _: httpx.Response(200, headers={'content-length': '999999999'}, content=b'')) as provider, pytest.raises(ProviderError):
        provider.download_model('https://cdn.tripo3d.ai/model.glb')
    with client(lambda _: httpx.Response(200, headers={'content-encoding': 'gzip'}, content=b'')) as provider, pytest.raises(ProviderError):
        provider.download_model('https://cdn.tripo3d.ai/model.glb')


def test_valid_geometry_and_embedded_texture():
    doc, binary = glb_document()
    image = png()
    doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(image)})
    binary += image
    doc['buffers'][0]['byteLength'] = len(binary)
    doc['images'] = [{'bufferView': 1, 'mimeType': 'image/png'}]
    doc['textures'] = [{'source': 0}]
    result = validate_glb(pack_glb(doc, binary))
    assert result['triangles'] == 1 and result['vertices'] == 3
    assert result['texture_pixels'] == 1024 and result['images'] == 1
    assert result['embedded'] is True and result['print_approved'] is False


@pytest.mark.parametrize('mutation', [
    lambda d: d['buffers'][0].update(uri='https://attacker.example/buffer'),
    lambda d: d.update(images=[{'uri': 'file:///etc/passwd'}]),
    lambda d: d.update(extensionsRequired=['KHR_draco_mesh_compression']),
    lambda d: d['bufferViews'][0].update(byteLength=99999999),
    lambda d: d['accessors'][0].update(count=1000001),
    lambda d: d['accessors'][0].update(byteOffset=99999),
    lambda d: d['accessors'][0].update(sparse={'count': 1}),
    lambda d: d['nodes'][0].update(children=[0]),
    lambda d: d['nodes'][0].update(mesh=100),
    lambda d: d['nodes'][0].update(scale=[1, float('nan'), 1]),
    lambda d: d['meshes'][0]['primitives'][0].update(mode=1),
    lambda d: d['meshes'][0]['primitives'][0].update(indices=99),
    lambda d: d['meshes'][0]['primitives'][0].update(targets=[{}]),
    lambda d: d.update(skins=[{}]),
    lambda d: d.update(nodes=[{}]),
    lambda d: d.update(asset=[]),
])
def test_malformed_or_unsupported_geometry_rejected(mutation):
    doc, binary = glb_document()
    mutation(doc)
    with pytest.raises(ProviderError) as error:
        validate_glb(pack_glb(doc, binary))
    assert error.value.code == 'TRIPO_INVALID_MODEL'


def test_nonfinite_binary_and_out_of_range_indices_rejected():
    doc, binary = glb_document()
    with pytest.raises(ProviderError):
        validate_glb(pack_glb(doc, struct.pack('<f', float('inf')) + binary[4:]))
    doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': 6})
    doc['accessors'].append({'bufferView': 1, 'componentType': 5123, 'count': 3, 'type': 'SCALAR'})
    doc['meshes'][0]['primitives'][0]['indices'] = 1
    binary += struct.pack('<3H', 0, 1, 9)
    doc['buffers'][0]['byteLength'] = len(binary)
    with pytest.raises(ProviderError):
        validate_glb(pack_glb(doc, binary))


@pytest.mark.parametrize('data', [b'', b'not glb', pack_glb()[:-1], pack_glb() + b'junk', b'bad!' + pack_glb()[4:]])
def test_container_length_magic_and_truncation_rejected(data):
    with pytest.raises(ProviderError):
        validate_glb(data)


def test_task_status_is_not_fabricated_and_provider_text_is_redacted():
    with client(lambda _: httpx.Response(200, json={'code': 0, 'data': {
        'task_id': 'task-a', 'status': 'new-provider-state', 'progress': 999,
        'error_message': 'test-server-secret', 'error_code': 700,
    }})) as provider:
        task = provider.task('task-a')
    assert task['status'] == 'unknown' and task['progress'] == 0
    assert task['error_code'] == 700 and 'test-server-secret' not in json.dumps(task)


def test_task_mismatch_and_path_injection_rejected():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'code': 0, 'data': {'task_id': 'different', 'status': 'success'}})
    with client(handler) as provider:
        with pytest.raises(ProviderError):
            provider.task('task-a')
        with pytest.raises(ProviderError):
            provider.task('../account/balance')
        with pytest.raises(ProviderError):
            provider.create('https://attacker.example/image.png')
    assert len(calls) == 1
