"""Bounded internal HTTP API; request addresses are never logged or persisted."""
import argparse
import json
import os
import re
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from region_check import RegionIndex, VERSION

MAX_BODY = 256 * 1024
MAX_BATCH = 100


def openapi():
    address = {'type': 'string', 'minLength': 2, 'maxLength': 1000}
    def response(description):
        return {'description': description, 'content': {'application/json': {
            'schema': {'type': 'object', 'additionalProperties': True}}}}
    def query(name, schema, required=False):
        return {'name': name, 'in': 'query', 'required': required, 'schema': schema}
    def post(summary, schema):
        return {'summary': summary, 'requestBody': {'required': True, 'content': {
            'application/json': {'schema': schema}}}, 'responses': {
                '200': response('Query result'), '400': response('Invalid input'),
                '413': response('Request too large'), '415': response('JSON required')}}
    return {'openapi': '3.1.0', 'info': {'title': 'regionCheck', 'version': VERSION,
            'description': 'Read-only levels 1–4 matching. Provincial source dates differ. '
                           'Historical events are incomplete. No external address services.'},
            'paths': {
                '/health': {'get': {'summary': 'Readiness', 'responses': {'200': response('Ready')}}},
                '/api/coverage': {'get': {'summary': 'Data coverage and provincial sources',
                                        'responses': {'200': response('Coverage')}}},
                '/api/divisions/search': {'get': {'summary': 'Search current and historical names',
                    'parameters': [query('q', {'type': 'string', 'minLength': 2, 'maxLength': 100}, True),
                                   query('limit', {'type': 'integer', 'minimum': 1, 'maximum': 50})],
                    'responses': {'200': response('Names, snapshots and events'),
                                  '400': response('Invalid query')}}},
                '/api/divisions/{code}/history': {'get': {'summary': 'History and explicit succession events',
                    'parameters': [{'name': 'code', 'in': 'path', 'required': True,
                                    'schema': {'type': 'string', 'pattern': '^(?:[0-9]{6}|[0-9]{9}|[0-9]{12})$'}}],
                    'responses': {'200': response('History; snapshots are not automatically change events'),
                                  '404': response('Unknown code'), '400': response('Invalid code')}}},
                '/api/addresses/match': {'post': post('Match a current or historical address', {
                    'type': 'object', 'required': ['address'], 'additionalProperties': False,
                    'properties': {'address': address}})},
                '/api/addresses/match-batch': {'post': post('Match up to 100 addresses', {
                    'type': 'object', 'required': ['addresses'], 'additionalProperties': False,
                    'properties': {'addresses': {'type': 'array', 'minItems': 1,
                                                'maxItems': MAX_BATCH, 'items': address}}})}}}


class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class BoundedServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address, index):
        self.index = index
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.sendall(b'HTTP/1.0 503 Service Unavailable\r\nContent-Length: 0\r\n\r\n')
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            request.settimeout(10)
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        print('regionCheck: request connection failed', flush=True)


class Handler(BaseHTTPRequestHandler):
    server_version = 'regionCheck/' + VERSION
    sys_version = ''

    def log_message(self, format, *args):
        # BaseHTTPRequestHandler normally logs query strings, including names.
        pass

    def reply(self, status, body, content_type='application/json; charset=utf-8'):
        data = body.encode() if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        if self.headers.get('Transfer-Encoding'):
            raise APIError(400, 'Transfer-Encoding is not supported')
        if self.headers.get_content_type() != 'application/json':
            raise APIError(415, 'Content-Type must be application/json')
        try:
            size = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            raise APIError(400, 'Invalid Content-Length') from None
        if size < 0:
            raise APIError(411, 'Content-Length required')
        if size > MAX_BODY:
            raise APIError(413, 'Request body too large')
        data = self.rfile.read(size)
        if len(data) != size:
            raise APIError(400, 'Incomplete request body')
        try:
            value = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            raise APIError(400, 'Invalid JSON') from None
        if not isinstance(value, dict):
            raise APIError(400, 'Expected a JSON object')
        return value

    def route(self):
        url = urlsplit(self.path)
        q = parse_qs(url.query, keep_blank_values=True)
        index = self.server.index
        if self.command == 'GET':
            if url.path in ('/', '/docs'):
                return self.reply(200, Path(__file__).with_name('docs.html').read_text(), 'text/html; charset=utf-8')
            if url.path == '/openapi.json':
                return self.reply(200, openapi())
            if url.path == '/health':
                return self.reply(200, {'status': 'ok', 'service': 'regionCheck', 'version': VERSION,
                                        'edition': index.data['edition'], 'current_count': len(index.current),
                                        'data_sha256': index.digest})
            if url.path == '/api/coverage':
                return self.reply(200, index.summary())
            if url.path == '/api/divisions/search':
                if set(q) - {'q', 'limit'} or any(len(v) != 1 for v in q.values()):
                    raise ValueError('Unknown or repeated query parameter')
                limit = int(q.get('limit', ['20'])[0])
                if not 1 <= limit <= 50:
                    raise ValueError('limit must be between 1 and 50')
                return self.reply(200, index.search(q.get('q', [''])[0], limit))
            found = re.fullmatch(r'/api/divisions/([^/]+)/history', url.path)
            if found:
                return self.reply(200, index.history(found[1]))
        elif self.command == 'POST' and url.path in ('/api/addresses/match', '/api/addresses/match-batch'):
            data = self.body()
            if url.path.endswith('match-batch'):
                if set(data) != {'addresses'} or not isinstance(data['addresses'], list):
                    raise ValueError('Expected addresses array')
                values = data['addresses']
                if not 1 <= len(values) <= MAX_BATCH:
                    raise ValueError('Batch must contain 1 to 100 addresses')
                if any(not isinstance(a, str) or not 2 <= len(a.strip()) <= 1000 for a in values):
                    raise ValueError('Every address must contain 2 to 1000 characters')
                return self.reply(200, {'results': [index.match(a) for a in values], 'count': len(values)})
            if set(data) != {'address'}:
                raise ValueError('Expected only address')
            return self.reply(200, index.match(data['address']))
        raise APIError(404, 'Endpoint not found')

    def handle_api(self):
        try:
            self.route()
        except APIError as error:
            self.reply(error.status, {'error': error.message})
        except (ValueError, TypeError, RecursionError):
            self.reply(400, {'error': 'Invalid input; see /openapi.json for field requirements'})
        except KeyError:
            self.reply(404, {'error': 'Division not found'})
        except (socket.timeout, TimeoutError):
            self.close_connection = True
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception:
            self.reply(500, {'error': 'Internal query error'})

    do_GET = handle_api
    do_POST = handle_api


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', default=os.getenv('REGION_DATA', '/data'))
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    index = RegionIndex(args.data)
    print(json.dumps({'service': 'regionCheck', 'version': VERSION, 'edition': index.data['edition'],
                      'current_count': len(index.current), 'data_sha256': index.digest}), flush=True)
    BoundedServer((args.host, args.port), index).serve_forever()
