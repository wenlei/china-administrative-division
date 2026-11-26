"""Validate a warm region backend, then gracefully reload only its stable router.

The operator starts the inactive backend first. This tool never starts, stops,
recreates, or deletes a container. Without --execute it only validates the plan.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

CONFIG = '/etc/nginx/region-check/nginx.conf'
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
UPSTREAM = re.compile(r'upstream region_active\s*\{\s*server ([A-Za-z0-9_.-]+):8000;\s*keepalive 16;\s*\}\s*\Z')


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE)


def inspect(name):
    return json.loads(run('docker', 'inspect', name))[0]


def upstream(name):
    if not NAME.fullmatch(name):
        raise ValueError('Invalid backend container name')
    return f'upstream region_active {{\n    server {name}:8000;\n    keepalive 16;\n}}\n'


def read_backend(value):
    match = UPSTREAM.fullmatch(value)
    if not match:
        raise ValueError('Unrecognized upstream configuration; review it before switching')
    return match[1]


def atomic_write(path, value):
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        output.write(value)
        output.flush()
        os.fsync(output.fileno())
    try:
        temporary.chmod(0o644)
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def health(client, host):
    if not NAME.fullmatch(host):
        raise ValueError('Invalid health host')
    code = ("import urllib.request;print(urllib.request.urlopen("
            + repr('http://' + host + ':8000/health') + ",timeout=3).read().decode())")
    return json.loads(run('docker', 'exec', client, 'python', '-c', code))


def check_health(value, version, digest):
    if (value.get('status') != 'ok' or value.get('service') != 'regionCheck'
            or value.get('version') != version or value.get('data_sha256') != digest
            or not isinstance(value.get('current_count'), int) or value['current_count'] <= 0):
        raise RuntimeError('Backend readiness or reference-data identity mismatch')


def draining_workers(router):
    # BusyBox ps is present in the pinned nginx Alpine router image.
    return 'worker process is shutting down' in run('docker', 'exec', router, 'ps', '-o', 'args')


def wait_route(client, router, version, digest, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = health(client, router)
            check_health(value, version, digest)
            return value
        except (RuntimeError, ValueError, subprocess.SubprocessError):
            time.sleep(0.2)
    raise RuntimeError('Route failed verification')


def switch(directory, router, candidate, version, digest, image, execute=False, timeout=30):
    directory = Path(directory).resolve(strict=True)
    if not all(NAME.fullmatch(n) for n in [router, candidate]):
        raise ValueError('Invalid container name')
    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('Expected data SHA256 is required')
    with (directory / '.switch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = directory / 'upstream.conf'
        previous = path.read_text()
        old = read_backend(previous)
        if old == candidate:
            raise ValueError('Candidate is already active')
        front, back = inspect(router), inspect(candidate)
        if front['State']['Status'] != 'running' or back['State']['Status'] != 'running':
            raise RuntimeError('Router and candidate must already be running')
        if back['Image'] != image:
            raise RuntimeError('Candidate image differs from the reviewed image ID')
        if not set(front['NetworkSettings']['Networks']) & set(back['NetworkSettings']['Networks']):
            raise RuntimeError('Router and candidate do not share a network')
        mounts = [m for m in front['Mounts'] if m['Destination'] == '/etc/nginx/region-check']
        if len(mounts) != 1 or Path(mounts[0]['Source']).resolve() != directory or mounts[0]['RW']:
            raise RuntimeError('Router must bind this config directory read-only')
        if draining_workers(router):
            raise RuntimeError('Previous requests are still draining; retain both backends and retry later')
        before = health(candidate, router)
        if before.get('status') != 'ok' or before.get('service') != 'regionCheck':
            raise RuntimeError('Current route is not healthy')
        check_health(health(candidate, old), before['version'], before['data_sha256'])
        check_health(health(candidate, candidate), version, digest)
        result = {'status': 'validated-not-switched', 'previous': old, 'candidate': candidate,
                  'image': image, 'version': version, 'data_sha256': digest,
                  'router_container_id': front['Id'], 'containers_stopped': 0}
        if not execute:
            return result
        try:
            atomic_write(path, upstream(candidate))
            run('docker', 'exec', router, 'nginx', '-t', '-c', CONFIG)
            run('docker', 'exec', router, 'nginx', '-s', 'reload', '-c', CONFIG)
            wait_route(candidate, router, version, digest, timeout)
        except Exception:
            atomic_write(path, previous)
            run('docker', 'exec', router, 'nginx', '-t', '-c', CONFIG)
            run('docker', 'exec', router, 'nginx', '-s', 'reload', '-c', CONFIG)
            wait_route(candidate, router, before['version'], before['data_sha256'], timeout)
            raise
        if inspect(router)['Id'] != front['Id']:
            raise RuntimeError('Router identity changed unexpectedly; inspect before further action')
        result.update(status='switched', old_backend_retained=True,
                      previous_requests_draining=draining_workers(router))
        atomic_write(directory / 'last-switch.json', json.dumps(result, indent=2) + '\n')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-dir', required=True)
    parser.add_argument('--router', default='regionCheck')
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--data-sha256', required=True)
    parser.add_argument('--image-id', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    print(json.dumps(switch(args.config_dir, args.router, args.candidate, args.version,
                            args.data_sha256, args.image_id, args.execute), indent=2))


if __name__ == '__main__':
    main()
