"""Verify the relay with synthetic text on loopback, without touching live AI."""
import http.server
import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / 'ags_runtime/ags_oke'
KEYS = RUNTIME / 'secrets'
NAME = 'aegis-oke-ssh-check'


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'aegis-relay-smoke-ok')

    def log_message(self, *_):
        pass


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, capture_output=True, text=True, **kwargs)


def main():
    KEYS.mkdir(parents=True, exist_ok=True)
    host = KEYS / 'ssh_host_ed25519_key'
    if not host.exists():
        run(['ssh-keygen', '-t', 'ed25519', '-N', '', '-f', str(host)])
    private = Path.home() / '.oci/aegis-hosting/aegis-web-ed25519'
    shutil.copyfile(str(private) + '.pub', KEYS / 'authorized_keys')
    known = RUNTIME / 'known_hosts_smoke'
    known.write_text('[127.0.0.1]:32222 ' + Path(str(host) + '.pub').read_text().strip() + '\n')
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 11436), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    process = None
    try:
        run(['docker', 'run', '-d', '--platform', 'linux/arm64', '--name', NAME,
            '--cap-drop', 'ALL', '--cap-add', 'SETUID', '--cap-add', 'SETGID', '--cap-add', 'SYS_CHROOT',
            '-p', '127.0.0.1:32222:2222', '--mount', f'type=bind,source={KEYS},target=/run/ssh-keys,readonly',
            'aegis-oke-ssh:pilot-arm64'])
        time.sleep(2)
        common = ['ssh', '-i', str(private), '-p', '32222', '-o', 'BatchMode=yes',
            '-o', 'StrictHostKeyChecking=yes', '-o', f'UserKnownHostsFile={known}',
            '-o', 'ExitOnForwardFailure=yes', '-o', 'ConnectTimeout=5']
        log = RUNTIME / 'relay-smoke.log'
        with log.open('w') as stream:
            process = subprocess.Popen(common + ['-N', '-R', '0.0.0.0:11434:127.0.0.1:11436',
                'relay@127.0.0.1'], stdout=stream, stderr=stream)
            success = False
            for _ in range(20):
                if process.poll() is not None:
                    raise RuntimeError('Relay exited: ' + log.read_text())
                probe = subprocess.run(['docker', 'exec', NAME, 'wget', '-qO-',
                    'http://127.0.0.1:11434'], capture_output=True, text=True)
                if probe.stdout == 'aegis-relay-smoke-ok':
                    success = True
                    break
                time.sleep(.5)
            assert success, 'Reverse relay failed'
            shell = subprocess.run(common + ['relay@127.0.0.1', 'echo forbidden-command'],
                capture_output=True, text=True, timeout=10)
            assert shell.returncode != 0 and 'forbidden-command' not in shell.stdout
            denied = subprocess.run(common + ['-N', '-R', '0.0.0.0:11435:127.0.0.1:11436',
                'relay@127.0.0.1'], capture_output=True, text=True, timeout=10)
            assert denied.returncode != 0, 'Unexpected remote port permitted'
            print('Relay smoke passed: pinned host key, approved reverse forwarding, shell denied, other ports denied')
            (RUNTIME / 'relay-smoke-result.json').write_text(json.dumps({
                'reverse_forwarding': True, 'pinned_host_key': True, 'shell_denied': True,
                'unapproved_port_denied': True}))
    finally:
        if process:
            process.terminate()
            process.wait(timeout=10)
        subprocess.run(['docker', 'rm', '-f', NAME], capture_output=True)
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
