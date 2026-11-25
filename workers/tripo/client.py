"""Bounded Tripo v3 client. Task creation is deliberately never retried.

Official contract: https://developers.tripo3d.ai/en/docs/generation-image-to-model/standard
Download hosts are limited to Tripo-owned domains documented in the API examples.
Do not broaden this to generic S3/OSS domains without verifying a provider host.
"""
from __future__ import annotations

import io
import ipaddress
import json
import math
import os
import re
import socket
import struct
from collections.abc import Callable, Sequence
from urllib.parse import urlsplit

import httpx
from PIL import Image

API_ORIGIN = 'https://openapi.tripo3d.ai/v3'
MODEL = 'v3.1-20260211'
MODEL_OPTIONS = {
    'model': MODEL, 'texture': True, 'pbr': True,
    'texture_quality': 'standard', 'texture_version': 'v3.5-20260815',
    'face_limit': 50000, 'enable_image_autofix': False,
    'texture_alignment': 'original_image',
}
ESTIMATED_CREDITS = 30
MAX_MODEL_BYTES = 64 * 1024 * 1024
MAX_PREVIEW_BYTES = 8 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_API_BYTES = 1024 * 1024
DOWNLOAD_DOMAINS = ('tripo3d.ai', 'tripo3d.com')
_ID = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')
_TOKEN = re.compile(r'file_[A-Za-z0-9_-]{1,192}\Z')


class ProviderError(Exception):
    def __init__(self, public_message: str, code: str | int | None = None):
        self.public_message = public_message
        self.code = code
        super().__init__(public_message)


class SubmissionUncertain(ProviderError):
    """A task might exist. Reconcile its outcome; never automatically resubmit."""

    def __init__(self, public_message: str = 'Tripo may have received this generation. Do not submit it again while its outcome is being checked.', code: str = 'TRIPO_SUBMISSION_UNCERTAIN'):
        super().__init__(public_message, code)


def _error(code: str, message: str) -> ProviderError:
    return ProviderError(message, code)


def _public_addresses(host: str) -> list[str]:
    return list(dict.fromkeys(item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)))


def _json(raw: bytes):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('Duplicate JSON key')
            value[key] = item
        return value
    def invalid(_):
        raise ValueError('Nonfinite JSON number')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def _bounded(response: httpx.Response, limit: int) -> bytes:
    length = response.headers.get('content-length')
    if length is not None:
        try:
            if int(length) < 0 or int(length) > limit:
                raise ValueError()
        except ValueError:
            raise _error('TRIPO_RESPONSE_TOO_LARGE', 'Tripo returned a file larger than this preview supports.') from None
    data = bytearray()
    for chunk in response.iter_bytes(chunk_size=65536):
        if len(data) + len(chunk) > limit:
            raise _error('TRIPO_RESPONSE_TOO_LARGE', 'Tripo returned a file larger than this preview supports.')
        data.extend(chunk)
    return bytes(data)


class TripoClient:
    def __init__(self, api_key: str | None = None, *, transport: httpx.BaseTransport | None = None,
                 resolver: Callable[[str], Sequence[str]] | None = None):
        key = os.environ.get('TRIPO_API_KEY', '') if api_key is None else api_key
        if not isinstance(key, str) or not key.strip() or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise _error('TRIPO_NOT_CONFIGURED', 'Tripo generation is not configured on this server.')
        self._transport = transport
        self._resolver = resolver or _public_addresses
        self._client = httpx.Client(
            headers={'Authorization': 'Bearer ' + key, 'Accept': 'application/json'},
            timeout=httpx.Timeout(60, connect=10), follow_redirects=False,
            trust_env=False, transport=transport,
        )

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _request(self, method: str, path: str, *, creating: bool = False, **kwargs) -> dict:
        # No retry loop, including on 429. The service decides how to resume reads.
        try:
            with self._client.stream(method, API_ORIGIN + path, **kwargs) as response:
                status = response.status_code
                if creating and status >= 500:
                    raise SubmissionUncertain()
                raw = _bounded(response, MAX_API_BYTES)
                try:
                    body = _json(raw)
                except (ValueError, UnicodeError, RecursionError):
                    if creating and 200 <= status < 400:
                        raise SubmissionUncertain() from None
                    raise _error('TRIPO_INVALID_RESPONSE', 'Tripo returned an unreadable response.') from None
                if not isinstance(body, dict):
                    if creating and 200 <= status < 400:
                        raise SubmissionUncertain()
                    raise _error('TRIPO_INVALID_RESPONSE', 'Tripo returned an unreadable response.')
                code = body.get('code')
                if status not in range(200, 300) or type(code) is not int or code != 0:
                    if creating and 200 <= status < 400 and (type(code) is not int or code == 0):
                        raise SubmissionUncertain()
                    message = {
                        2: 'Tripo authentication failed. The server credential needs attention.',
                        1002: 'Tripo authentication failed. The server credential needs attention.',
                        1007: 'Tripo is rate limited. Please wait before checking again.',
                        2000: 'Tripo is currently processing its maximum number of tasks.',
                        2008: 'Tripo declined this image under its content policy.',
                        2010: 'The Tripo account does not have enough credits for this generation.',
                        2015: 'This Tripo model version is no longer available.',
                    }.get(code if type(code) is int else None, 'Tripo could not complete this request.')
                    raise ProviderError(message, code if type(code) is int else 'TRIPO_REQUEST_FAILED')
                data = body.get('data')
                if not isinstance(data, dict):
                    if creating:
                        raise SubmissionUncertain()
                    raise _error('TRIPO_INVALID_RESPONSE', 'Tripo returned an incomplete response.')
                return data
        except httpx.HTTPError:
            if creating:
                raise SubmissionUncertain() from None
            raise _error('TRIPO_CONNECTION_FAILED', 'The connection to Tripo failed. Please check again shortly.') from None
        except ProviderError as exc:
            if creating and exc.code == 'TRIPO_RESPONSE_TOO_LARGE':
                raise SubmissionUncertain() from None
            raise

    def upload(self, image: bytes, filename: str = 'reference.png') -> str:
        if not isinstance(image, bytes) or not 0 < len(image) <= MAX_IMAGE_BYTES:
            raise _error('TRIPO_INVALID_IMAGE', 'Use a JPEG or PNG image smaller than 20 MB.')
        # The service owns pixel decoding, normalization, metadata stripping and consent.
        if image.startswith(b'\x89PNG\r\n\x1a\n'):
            mime, safe_name = 'image/png', 'reference.png'
        elif image.startswith(b'\xff\xd8\xff'):
            mime, safe_name = 'image/jpeg', 'reference.jpg'
        else:
            raise _error('TRIPO_INVALID_IMAGE', 'Use a JPEG or PNG image.')
        data = self._request('POST', '/files', files={'file': (safe_name, image, mime)})
        token = data.get('file_token')
        if not isinstance(token, str) or not _TOKEN.fullmatch(token):
            raise _error('TRIPO_INVALID_RESPONSE', 'Tripo did not return a usable image token.')
        return token

    def create(self, file_token: str) -> str:
        if not isinstance(file_token, str) or not _TOKEN.fullmatch(file_token):
            raise _error('TRIPO_INVALID_INPUT', 'A valid uploaded image is required.')
        data = self._request('POST', '/generation/image-to-model', creating=True,
                             json={'input': file_token, **MODEL_OPTIONS})
        task_id = data.get('task_id')
        if not isinstance(task_id, str) or not _ID.fullmatch(task_id):
            raise SubmissionUncertain()
        return task_id

    def task(self, task_id: str) -> dict:
        if not isinstance(task_id, str) or not _ID.fullmatch(task_id):
            raise _error('TRIPO_INVALID_INPUT', 'A valid Tripo task is required.')
        data = self._request('GET', '/tasks/' + task_id)
        if data.get('task_id') != task_id or not isinstance(data.get('status'), str):
            raise _error('TRIPO_INVALID_RESPONSE', 'Tripo returned an unexpected task.')
        status = data['status']
        result = {'task_id': task_id, 'status': status if status in {'queued', 'running', 'success', 'failed', 'cancelled', 'banned', 'expired'} else 'unknown'}
        progress = data.get('progress', 0)
        result['progress'] = progress if type(progress) is int and 0 <= progress <= 100 else 0
        for key in ('type', 'created_at', 'completed_at'):
            if isinstance(data.get(key), str) and len(data[key]) <= 64:
                result[key] = data[key]
        credits = data.get('credits_consumed')
        if type(credits) in (int, float) and math.isfinite(credits) and credits >= 0:
            result['credits_consumed'] = credits
        if type(data.get('error_code')) is int:
            result['error_code'] = data['error_code']
        if data.get('error_message'):
            result['error_message'] = 'Tripo could not complete this task.'
        output = data.get('output')
        if isinstance(output, dict):
            result['output'] = {key: output[key] for key in ('model_url', 'rendered_image_url')
                                if isinstance(output.get(key), str) and len(output[key]) <= 8192}
        return result

    def _download(self, url: str, limit: int) -> bytes:
        try:
            if not isinstance(url, str) or len(url) > 8192 or any(ord(c) < 33 or ord(c) > 126 for c in url):
                raise ValueError()
            parsed = urlsplit(url)
            host = parsed.hostname or ''
            if (parsed.scheme != 'https' or parsed.port not in (None, 443) or parsed.username is not None
                    or parsed.password is not None or parsed.fragment or '\\' in url
                    or not any(host == domain or host.endswith('.' + domain) for domain in DOWNLOAD_DOMAINS)):
                raise ValueError()
            addresses = self._resolver(host)
            if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
                raise ValueError()
            # Connect to the checked IP; retain hostname for TLS verification and HTTP.
            # httpcore's sni_hostname extension avoids a second DNS lookup/rebinding.
            pinned = httpx.URL(url).copy_with(host=str(ipaddress.ip_address(addresses[0])))
        except (ValueError, TypeError, OSError, httpx.InvalidURL):
            raise _error('TRIPO_UNSAFE_DOWNLOAD', 'Tripo returned an unsupported download address.') from None
        try:
            with httpx.Client(timeout=httpx.Timeout(60, connect=10), trust_env=False,
                              follow_redirects=False, transport=self._transport) as client:
                with client.stream('GET', pinned, headers={'Host': host, 'Accept-Encoding': 'identity'},
                                   extensions={'sni_hostname': host}) as response:
                    if response.status_code != 200:
                        raise _error('TRIPO_DOWNLOAD_FAILED', 'The Tripo model download is not available. Please check again shortly.')
                    if response.headers.get('content-encoding', 'identity').lower() != 'identity':
                        raise _error('TRIPO_INVALID_DOWNLOAD', 'Tripo returned an unsupported download encoding.')
                    return _bounded(response, limit)
        except httpx.HTTPError:
            raise _error('TRIPO_DOWNLOAD_FAILED', 'The Tripo model download was interrupted. Please check again shortly.') from None

    def download_model(self, url: str) -> bytes:
        data = self._download(url, MAX_MODEL_BYTES)
        validate_glb(data)
        return data

    def download_preview(self, url: str) -> bytes:
        data = self._download(url, MAX_PREVIEW_BYTES)
        _image_info(data)
        return data


def _image_info(data: bytes) -> int:
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ('PNG', 'JPEG', 'WEBP') or min(image.size) < 1 or max(image.size) > 4096 or getattr(image, 'n_frames', 1) != 1:
                raise ValueError()
            pixels = image.width * image.height
            image.verify()
            return pixels
    except (OSError, ValueError, Image.DecompressionBombError, SyntaxError):
        raise _error('TRIPO_INVALID_MODEL', 'Tripo returned an unsupported or damaged texture image.') from None


def validate_glb(data: bytes) -> dict:
    """Validate the bounded static embedded GLB subset supported by this beta.

    This is ingestion validation, not full glTF conformance or printability QA.
    Sparse accessors, animation, skins, compression and external files are excluded.
    """
    try:
        return _validate_glb(data)
    except ProviderError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, struct.error, UnicodeError, RecursionError, OverflowError):
        raise _error('TRIPO_INVALID_MODEL', 'Tripo returned an invalid or unsupported GLB model.') from None


def _validate_glb(data: bytes) -> dict:
    def require(condition):
        if not condition:
            raise ValueError()
    def integer(value, lower=0, upper=MAX_MODEL_BYTES):
        require(type(value) is int and lower <= value <= upper)
        return value
    require(isinstance(data, bytes) and 28 <= len(data) <= MAX_MODEL_BYTES)
    magic, version, total = struct.unpack_from('<4sII', data)
    require(magic == b'glTF' and version == 2 and total == len(data))
    offset, chunks = 12, []
    while offset < total:
        length, kind = struct.unpack_from('<II', data, offset)
        offset += 8
        require(length % 4 == 0 and offset + length <= total)
        chunks.append((kind, memoryview(data)[offset:offset + length]))
        offset += length
    require(offset == total and len(chunks) == 2 and chunks[0][0] == 0x4E4F534A and chunks[1][0] == 0x004E4942)
    require(len(chunks[0][1]) <= 2 * 1024 * 1024)
    doc = _json(bytes(chunks[0][1]))
    require(isinstance(doc, dict) and doc.get('asset', {}).get('version') == '2.0')
    def inspect(value, depth=0):
        require(depth <= 48)
        if isinstance(value, dict):
            require('uri' not in value)
            for child in value.values():
                inspect(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                inspect(child, depth + 1)
        elif isinstance(value, float):
            require(math.isfinite(value))
    inspect(doc)
    allowed_extensions = {'KHR_materials_unlit', 'KHR_texture_transform', 'KHR_materials_ior', 'KHR_materials_specular', 'KHR_materials_clearcoat', 'KHR_materials_sheen', 'KHR_materials_transmission', 'KHR_materials_volume', 'KHR_materials_emissive_strength'}
    require(set(doc.get('extensionsRequired', [])) <= allowed_extensions)
    require(not doc.get('skins') and not doc.get('animations'))
    binary = chunks[1][1]
    buffers = doc['buffers']
    require(len(buffers) == 1)
    size = integer(buffers[0]['byteLength'], 1)
    require(size <= len(binary) <= size + 3)
    views = doc['bufferViews']
    require(isinstance(views, list) and len(views) <= 8192)
    for view in views:
        require(view.get('buffer') == 0 and not view.get('extensions'))
        start, length = integer(view.get('byteOffset', 0)), integer(view['byteLength'], 1)
        require(start + length <= size)
        if 'byteStride' in view:
            stride = integer(view['byteStride'], 4, 252)
            require(stride % 4 == 0)
    accessors = doc['accessors']
    require(isinstance(accessors, list) and 0 < len(accessors) <= 4096)
    layouts = []
    components = {5120: ('b', 1), 5121: ('B', 1), 5122: ('h', 2), 5123: ('H', 2), 5125: ('I', 4), 5126: ('f', 4)}
    widths = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}
    total_values = 0
    for accessor in accessors:
        require(not accessor.get('sparse') and not accessor.get('extensions'))
        count = integer(accessor['count'], 1, 1000000)
        view = views[integer(accessor['bufferView'], 0, len(views) - 1)]
        fmt, component_size = components[accessor['componentType']]
        width = widths[accessor['type']]
        packed = component_size * width
        stride = view.get('byteStride', packed)
        start = integer(accessor.get('byteOffset', 0))
        require(stride >= packed and stride % component_size == 0 and start % component_size == 0)
        require(start + (count - 1) * stride + packed <= view['byteLength'])
        absolute = view.get('byteOffset', 0) + start
        require(absolute % component_size == 0)
        total_values += count * width
        require(total_values <= 8000000)
        if fmt == 'f':
            for index in range(count):
                require(all(math.isfinite(v) for v in struct.unpack_from('<' + fmt * width, binary, absolute + index * stride)))
        layouts.append((absolute, stride, fmt, width, count))
    meshes = doc['meshes']
    require(isinstance(meshes, list) and 0 < len(meshes) <= 512)
    triangles, vertices, mesh_triangles = 0, 0, []
    for mesh in meshes:
        initial_triangles = triangles
        primitives = mesh['primitives']
        require(isinstance(primitives, list) and 0 < len(primitives) <= 512)
        for primitive in primitives:
            require(primitive.get('mode', 4) == 4 and not primitive.get('targets') and not primitive.get('extensions'))
            attributes = primitive['attributes']
            position = integer(attributes['POSITION'], 0, len(accessors) - 1)
            accessor = accessors[position]
            require(accessor['componentType'] == 5126 and accessor['type'] == 'VEC3')
            count = accessor['count']
            for attribute in attributes.values():
                require(accessors[integer(attribute, 0, len(accessors) - 1)]['count'] == count)
            vertices += count
            if 'indices' in primitive:
                index = integer(primitive['indices'], 0, len(accessors) - 1)
                start, stride, fmt, width, indices = layouts[index]
                require(fmt in ('B', 'H', 'I') and width == 1 and indices % 3 == 0)
                for i in range(indices):
                    require(struct.unpack_from('<' + fmt, binary, start + i * stride)[0] < count)
                triangles += indices // 3
            else:
                require(count % 3 == 0)
                triangles += count // 3
            if 'material' in primitive:
                integer(primitive['material'], 0, len(doc.get('materials', [])) - 1)
        mesh_triangles.append(triangles - initial_triangles)
    require(0 < triangles <= 200000 and 0 < vertices <= 500000)
    nodes = doc['nodes']
    require(isinstance(nodes, list) and 0 < len(nodes) <= 4096)
    children_seen = set()
    for node in nodes:
        require('skin' not in node)
        if 'mesh' in node:
            integer(node['mesh'], 0, len(meshes) - 1)
        for key, count in (('matrix', 16), ('translation', 3), ('rotation', 4), ('scale', 3)):
            if key in node:
                values = node[key]
                require(isinstance(values, list) and len(values) == count and all(type(v) in (int, float) and math.isfinite(v) and abs(v) <= 1000000 for v in values))
        for child in node.get('children', []):
            integer(child, 0, len(nodes) - 1)
            require(child not in children_seen)
            children_seen.add(child)
    seen, active = set(), set()
    def visit(index, depth=0):
        require(depth <= 48 and index not in active)
        if index in seen:
            return
        active.add(index)
        for child in nodes[index].get('children', []):
            visit(child, depth + 1)
        active.remove(index)
        seen.add(index)
    for index in range(len(nodes)):
        visit(index)
    scenes = doc['scenes']
    require(isinstance(scenes, list) and 0 < len(scenes) <= 64)
    scene = scenes[integer(doc.get('scene', 0), 0, len(scenes) - 1)]
    roots = scene['nodes']
    require(isinstance(roots, list) and bool(roots))
    for index in roots:
        integer(index, 0, len(nodes) - 1)
    reachable = set()
    def collect(index):
        if index in reachable:
            return
        reachable.add(index)
        for child in nodes[index].get('children', []):
            collect(child)
    for index in roots:
        collect(index)
    require(any('mesh' in nodes[index] for index in reachable))
    require(sum(mesh_triangles[nodes[index]['mesh']] for index in reachable if 'mesh' in nodes[index]) <= 400000)
    pixels = 0
    images = doc.get('images', [])
    require(isinstance(images, list) and len(images) <= 32)
    for image in images:
        require(image.get('mimeType') in ('image/png', 'image/jpeg', 'image/webp'))
        view = views[integer(image['bufferView'], 0, len(views) - 1)]
        start = view.get('byteOffset', 0)
        pixels += _image_info(bytes(binary[start:start + view['byteLength']]))
        require(pixels <= 32 * 1024 * 1024)
    for texture in doc.get('textures', []):
        integer(texture['source'], 0, len(images) - 1)
    return {'bytes': len(data), 'vertices': vertices, 'triangles': triangles, 'images': len(images), 'texture_pixels': pixels, 'embedded': True, 'print_approved': False}
