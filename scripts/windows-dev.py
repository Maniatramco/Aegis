"""Local Windows adapter for Aegis scripts/local-smoke.sh. No external model calls."""
import argparse, base64, json, os, secrets, shutil, socket, subprocess, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('action', choices=['start', 'stop'])
parser.add_argument('--mock', action='store_true')
parser.add_argument('--ollama-executable',type=Path,default=REPO.parent/'.local-tools/ollama/ollama.exe')
parser.add_argument('--ollama-models',type=Path,default=REPO.parent/'.local-tools/ollama-models')
parser.add_argument('--runtime-dir', type=Path, default=REPO / 'data/native-windows')
args = parser.parse_args()
STATE = args.runtime_dir.resolve()
STATE.mkdir(parents=True,exist_ok=True)
pidfile = STATE / 'processes.json'
if args.action == 'stop':
    if pidfile.exists():
        for proc in json.loads(pidfile.read_text()):
            # Verify ownership before stopping: Windows can reuse an old PID.
            query = f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {int(proc['pid'])}').CommandLine"
            current = subprocess.run(['powershell.exe', '-NoProfile', '-Command', query],
                                     capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if (current.stdout.strip().lower()==proc['command'].lower() if proc.get('command') else str(REPO).lower() in current.stdout.lower()):
                subprocess.run(['taskkill', '/PID', str(proc['pid']), '/T', '/F'],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        pidfile.unlink()
    print('Stopped recorded Aegis processes; all data preserved.')
    raise SystemExit
if pidfile.exists():
    raise SystemExit('Recorded processes exist. Run stop before restarting.')
for port in (3000, 8000):
    with socket.socket() as s:
        if s.connect_ex(('127.0.0.1', port)) == 0:
            raise SystemExit(f'Port {port} already in use; existing service preserved.')
envpath = REPO / '.env'
if not envpath.exists():
    text = (REPO / '.env.example').read_text()
    for key, value in {
        'CHANGE_ME_MASTER_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        'CHANGE_ME_SESSION_SECRET': secrets.token_urlsafe(48),
        'CHANGE_ME_DATABASE_PASSWORD': secrets.token_hex(24),
        'CHANGE_ME_BOOTSTRAP_TOKEN': secrets.token_urlsafe(32),
    }.items():
        text = text.replace(key, value)
    envpath.write_text(text)
env = os.environ.copy()
for line in envpath.read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        key, value = line.split('=', 1)
        env[key] = value
env.update(MODEL_PROVIDER='mock' if args.mock else 'ollama', EMBEDDING_PROVIDER='mock' if args.mock else 'ollama', SEARCH_PROVIDER='local',
           STORAGE_PROVIDER='local', QUEUE_PROVIDER='database',
           AEGIS_OLLAMA_PORT='11435', AEGIS_ALLOW_MOCK='true' if args.mock else 'false', AEGIS_LOCAL_ONLY='true', AEGIS_MODEL='qwen3:4b', EMBEDDING_MODEL='nomic-embed-text', AEGIS_TIMEOUT='180', PYTHONPATH=str(REPO / 'backend'),
           AEGIS_STORAGE_ROOT=str(STATE / 'demo-data'),
           API_INTERNAL_URL='http://127.0.0.1:8000', NEXT_TELEMETRY_DISABLED='1')
env.pop('DATABASE_URL', None)
for key in ('OPENAI_API_KEY', 'OCI_GENAI_API_KEY'):
    env.pop(key, None)
py = str(REPO / '.venv/Scripts/python.exe')
node = shutil.which('node')
if not node or not Path(py).exists() or not (REPO / 'frontend/node_modules/next/dist/bin/next').exists():
    raise SystemExit('Install Node, the project .venv, and frontend dependencies before starting.')
processes = []
def launch(name, command, cwd, process_env):
    with (STATE / f'{name}.log').open('a') as log:
        proc=subprocess.Popen(command,cwd=cwd,env=process_env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                              creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
    processes.append({'name':name,'pid':proc.pid,'command':subprocess.list2cmdline(command)})
    pidfile.write_text(json.dumps(processes))
    return proc

if not args.mock:
    import httpx
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',11435))==0:
            raise SystemExit('Aegis model port 11435 is occupied; preserve that process and inspect ownership before starting.')
    executable=args.ollama_executable.resolve(strict=True)
    models=args.ollama_models.resolve(strict=True)
    ollama_env=env|{'OLLAMA_HOST':'127.0.0.1:11435','OLLAMA_MODELS':str(models),'OLLAMA_NO_CLOUD':'1',
                    'OLLAMA_NUM_PARALLEL':'1','OLLAMA_MAX_LOADED_MODELS':'1','OLLAMA_CONTEXT_LENGTH':'4096'}
    daemon=launch('ollama',[str(executable),'serve'],REPO,ollama_env)
    ready=False
    with httpx.Client(timeout=2,trust_env=False,follow_redirects=False) as client:
        for _ in range(40):
            if daemon.poll() is not None:break
            try:
                response=client.get('http://127.0.0.1:11435/api/tags');response.raise_for_status()
                names={model['name'] for model in response.json()['models']}
                ready={'qwen3:4b','nomic-embed-text:latest'}<=names
                break
            except httpx.HTTPError:time.sleep(.25)
    if not ready:
        raise SystemExit('Isolated Ollama did not become ready with the existing models. Inspect ollama.log; use stop before retrying.')

commands = [
    ('api', [py, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'], REPO),
    ('worker', [py, '-m', 'app.worker'], REPO),
    ('web', [node, str(REPO / 'frontend/node_modules/next/dist/bin/next'), 'dev', '-H', '127.0.0.1', '-p', '3000'], REPO / 'frontend'),
]
for name, command, cwd in commands:
    launch(name,command,cwd,env)
print('Started Aegis local-only development mode: http://127.0.0.1:3000')
print('Backend health: http://127.0.0.1:8000/health')
print('Local process logs:', STATE)
print('Aegis model endpoint: http://127.0.0.1:11435 (separate from Ollama desktop)')
