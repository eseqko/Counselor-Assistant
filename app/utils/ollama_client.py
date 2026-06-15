"""Ollama local LLM client — all data stays on the machine (FERPA safe)."""
import requests
import json
import os

# Defaults — can be overridden via environment or settings
OLLAMA_BASE_URL = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'gemma4:e4b')


def _get_settings():
    """Read Ollama settings from the data directory if available."""
    settings_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'data', 'ollama_settings.json'
    )
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_settings(base_url, model):
    """Persist Ollama settings to disk."""
    settings_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'data', 'ollama_settings.json'
    )
    with open(settings_path, 'w') as f:
        json.dump({'base_url': base_url, 'model': model}, f)


def get_base_url():
    settings = _get_settings()
    return settings.get('base_url', OLLAMA_BASE_URL)


def get_model():
    settings = _get_settings()
    return settings.get('model', OLLAMA_MODEL)


def is_available():
    """Check if Ollama is running and reachable."""
    try:
        resp = requests.get(f'{get_base_url()}/api/tags', timeout=3)
        return resp.status_code == 200
    except requests.RequestException:
        # Catch the whole requests hierarchy (ConnectionError, Timeout, and also
        # MissingSchema/InvalidURL from a malformed saved base_url). This runs on
        # every authenticated page via the app-state probe, so it must never 500.
        return False


def list_models():
    """Return list of available model names from Ollama."""
    try:
        resp = requests.get(f'{get_base_url()}/api/tags', timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return [m['name'] for m in data.get('models', [])]
    except Exception:
        return []


DEFAULT_GENERATE_TIMEOUT = int(os.environ.get('OLLAMA_TIMEOUT', '180'))
DEFAULT_NUM_CTX = int(os.environ.get('OLLAMA_NUM_CTX', '4096'))


def generate(prompt, system=None, temperature=0.7, timeout=None, num_ctx=None):
    """Send a prompt to Ollama and return the response text."""
    payload = {
        'model': get_model(),
        'prompt': prompt,
        'stream': False,
        'options': {
            'temperature': temperature,
            'num_ctx': num_ctx or DEFAULT_NUM_CTX,
        },
    }
    if system:
        payload['system'] = system

    resp = requests.post(
        f'{get_base_url()}/api/generate',
        json=payload,
        timeout=timeout if timeout is not None else DEFAULT_GENERATE_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get('response', '').strip()


def generate_stream(prompt, system=None, temperature=0.7, timeout=None, num_ctx=None):
    """Yield (token, done) tuples from Ollama's streaming NDJSON endpoint."""
    payload = {
        'model': get_model(),
        'prompt': prompt,
        'stream': True,
        'options': {
            'temperature': temperature,
            'num_ctx': num_ctx or DEFAULT_NUM_CTX,
        },
    }
    if system:
        payload['system'] = system

    resp = requests.post(
        f'{get_base_url()}/api/generate',
        json=payload,
        timeout=timeout if timeout is not None else DEFAULT_GENERATE_TIMEOUT,
        stream=True,
    )
    resp.raise_for_status()
    for line in resp.iter_lines():
        if line:
            data = json.loads(line)
            token = data.get('response', '')
            done = data.get('done', False)
            yield token, done
            if done:
                break
