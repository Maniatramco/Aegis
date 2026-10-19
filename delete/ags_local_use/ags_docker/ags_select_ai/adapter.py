"""Offline OpenAI-compatible bridge for Oracle Select AI and a downloaded Ollama model.

Every destination/model is fixed server-side. No provider SDKs, remote fallback,
model downloads, tools, URL fetching or proxy environment settings are used.
"""
import datetime
import hmac
import json
import os
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request
from sql_guard import validate_sql

MODEL = 'qwen3:4b'
MODEL_URL = 'http://model:11434'
TOKEN = os.environ['LOCAL_SELECT_AI_TOKEN']
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_):
        raise ValueError('Model redirects are forbidden')


CLIENT = build_opener(ProxyHandler({}), NoRedirect())
AUDIT = Path('/audit/requests.jsonl')
LOCK = threading.Lock()


def local_request(path, payload=None):
    request = Request(MODEL_URL + path, data=json.dumps(payload).encode() if payload is not None else None,
                      headers={'Content-Type': 'application/json'})
    with CLIENT.open(request, timeout=180) as response:
        if response.url != MODEL_URL + path:
            raise ValueError('Model redirects are forbidden')
        return json.load(response)


def verify_model():
    models = local_request('/api/tags')['models']
    matches = [value for value in models if value['name'] == MODEL]
    if len(matches) != 1 or matches[0].get('size', 0) < 100_000_000:
        raise ValueError('The downloaded local model is unavailable')
    if matches[0].get('remote_host') or matches[0].get('remote_model'):
        raise ValueError('Cloud models are disabled')


def audit(value):
    # Content-free evidence: never log prompts, schema text, SQL or credentials.
    with LOCK:
        with AUDIT.open('a', encoding='utf-8') as output:
            output.write(json.dumps(value) + '\n')


class Handler(BaseHTTPRequestHandler):
    server_version = 'AegisLocalSelectAI/1'

    def log_message(self, *_):
        pass

    def send_json(self, code, value):
        data = json.dumps(value).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        return hmac.compare_digest(self.headers.get('Authorization', '').encode(), ('Bearer ' + TOKEN).encode())

    def do_GET(self):
        if self.path != '/health':
            return self.send_json(404, {'error': 'Unknown local route'})
        try:
            verify_model()
            self.send_json(200, {'status': 'ready', 'model': MODEL, 'model_location': 'local',
                                 'cloud_enabled': False, 'external_provider_calls': 0})
        except Exception:
            self.send_json(503, {'status': 'unavailable', 'model': MODEL, 'cloud_enabled': False})

    def do_POST(self):
        if self.path != '/v1/chat/completions':
            return self.send_json(404, {'error': 'Unknown local route'})
        if not self.authorized():
            audit({'time': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   'status': 'denied', 'authorization_scheme': self.headers.get('Authorization', '').split(' ', 1)[0],
                   'authorization_length': len(self.headers.get('Authorization', '')), 'external_provider_calls': 0})
            return self.send_json(401, {'error': 'Local model credential required'})
        started = time.monotonic()
        event = {'time': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'model': MODEL,
                 'destination': MODEL_URL, 'external_provider_calls': 0, 'status': 'failed'}
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 131072:
                raise ValueError('Request is too large')
            body = json.loads(self.rfile.read(length))
            if body.get('model') != MODEL or body.get('stream') or body.get('tools') or body.get('functions'):
                raise ValueError('Only the fixed local text model is supported')
            messages = body.get('messages')
            if not isinstance(messages, list) or not messages or len(messages) > 20:
                raise ValueError('Invalid local messages')
            for message in messages:
                if message.get('role') not in ('system', 'user', 'assistant') or not isinstance(message.get('content'), str):
                    raise ValueError('Only text messages are supported')
            messages.append({'role': 'user', 'content': 'Return only the final Oracle SQL query in a JSON object with one key sql. No explanation or reasoning. /no_think'})
            verify_model()
            # This cached Qwen model's older chat template always opens <think>.
            # Render Qwen's documented non-thinking prefix explicitly instead.
            prompt = ''.join('<|im_start|>' + message['role'] + '\n' + message['content']
                             + '<|im_end|>\n' for message in messages)
            prompt += '<|im_start|>assistant\n<think>\n\n</think>\n\n'
            result = local_request('/api/generate', {'model': MODEL, 'prompt': prompt, 'raw': True,
                'format': {'type': 'object', 'properties': {'sql': {'type': 'string'}}, 'required': ['sql'], 'additionalProperties': False},
                'stream': False, 'think': False, 'keep_alive': '5m',
                'options': {'temperature': 0, 'num_ctx': 8192,
                            'num_predict': min(1024, max(64, int(body.get('max_tokens', 1024))))}})
            content = json.loads(result.get('response', '{}')).get('sql', '').strip()
            if not content:
                raise ValueError('The local model returned no answer')
            # Oracle itself may parse showsql output while enforcing object_list.
            # Apply the same strict allow-list before it reaches that parser.
            content = validate_sql(content)
            prompt_tokens, output_tokens = result.get('prompt_eval_count', 0), result.get('eval_count', 0)
            event.update(status='completed', prompt_tokens=prompt_tokens, output_tokens=output_tokens)
            self.send_json(200, {'id': 'local-' + str(time.time_ns()), 'object': 'chat.completion',
                'created': int(time.time()), 'model': MODEL,
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content},
                             'finish_reason': 'length' if result.get('done_reason') == 'length' else 'stop'}],
                'usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': output_tokens,
                          'total_tokens': prompt_tokens + output_tokens}})
        except ValueError as error:
            self.send_json(400, {'error': str(error)})
        except Exception:
            self.send_json(503, {'error': 'Local model unavailable. No cloud fallback was attempted.'})
        finally:
            event['duration_ms'] = round((time.monotonic() - started) * 1000)
            audit(event)


if __name__ == '__main__':
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
