"""Optional language-model provider for the Reachmark AI crew.

Design rules that this module enforces:

* **The crew works with no provider at all.** Every agent has a deterministic
  engine; this module only improves phrasing when a key is configured.
* **Facts never come from a model.** Prompts may carry saved records and measured
  observations, and the answer is always treated as *wording* to be reviewed by the
  owner. Nothing a model returns can change a stage, send a message, or invent a
  figure.
* **Contact details are masked by default.** Unless ``CREW_LLM_SEND_CONTACTS=1``,
  e-mail addresses and phone numbers are stripped before a prompt leaves the host.
* **Failures are quiet.** Any error returns ``None`` and the deterministic path
  continues; the crew never blocks on a provider.

Environment
-----------
``CREW_LLM_PROVIDER``   auto | ollama | openai | anthropic | none   (default auto)
``CREW_LLM_API_KEY``    provider key (falls back to OPENAI_API_KEY / ANTHROPIC_API_KEY)
``CREW_LLM_MODEL``      default gpt-4o-mini / claude-3-5-sonnet-latest
``CREW_LLM_BASE_URL``   OpenAI-compatible base, default https://api.openai.com/v1
``OLLAMA_HOST``         local Ollama server, default http://127.0.0.1:11434
``CREW_LLM_MODEL``      for Ollama, default llama3.1
``CREW_LLM_TIMEOUT``    seconds, default 25
``CREW_LLM_BUDGET``     max completion calls per crew run, default 12
"""
import os, re, json, time

try:
    import requests
except ImportError:  # pragma: no cover - requests is a hard dependency of the app
    requests = None

DEFAULT_OPENAI = 'https://api.openai.com/v1'
DEFAULT_ANTHROPIC = 'https://api.anthropic.com/v1'
DEFAULT_OLLAMA = 'http://127.0.0.1:11434'
DEFAULT_OLLAMA_MODEL = 'llama3.1'
EMAIL_RE = re.compile(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+')
PHONE_RE = re.compile(r'(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)')
USAGE = {'calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'failures': 0}


class ProviderUnavailable(RuntimeError):
    """Raised when no provider is configured, or the provider refused the call."""


def _env(*names, default=''):
    for name in names:
        value = os.getenv(name, '').strip()
        if value:
            return value
    return default


def ollama_base():
    return _env('OLLAMA_HOST', 'CREW_LLM_BASE_URL', default=DEFAULT_OLLAMA).rstrip('/')


def resolve_provider():
    """Return (provider, api_key, model, base_url). Raises ProviderUnavailable.

    Ollama runs on your own machine, so it needs no API key — it is selected when you ask
    for it (``CREW_LLM_PROVIDER=ollama``) or when ``OLLAMA_HOST`` is set and nothing else
    is configured. In ``auto`` mode a configured cloud key still wins; a local model is
    never chosen silently.
    """
    choice = _env('CREW_LLM_PROVIDER', default='auto').lower()
    openai_key = _env('CREW_LLM_API_KEY', 'OPENAI_API_KEY')
    anthropic_key = _env('ANTHROPIC_API_KEY')
    ollama_host = _env('OLLAMA_HOST')
    if choice == 'none':
        raise ProviderUnavailable('Provider disabled with CREW_LLM_PROVIDER=none.')
    if choice == 'ollama' or (choice == 'auto' and ollama_host and not (openai_key or anthropic_key)):
        return ('ollama', '', _env('CREW_LLM_MODEL', default=DEFAULT_OLLAMA_MODEL), ollama_base())
    if choice in ('openai', 'anthropic') or True:
        if choice == 'anthropic':
            key = _env('CREW_LLM_API_KEY', 'ANTHROPIC_API_KEY') or anthropic_key
            if not key:
                raise ProviderUnavailable('Anthropic requested but no key is set.')
            return 'anthropic', key, _env('CREW_LLM_MODEL', default='claude-3-5-sonnet-latest'), _env('CREW_LLM_BASE_URL', default=DEFAULT_ANTHROPIC).rstrip('/')
        key = openai_key or anthropic_key
        if not key:
            raise ProviderUnavailable('No CREW_LLM_API_KEY / OPENAI_API_KEY configured.')
        if not openai_key and anthropic_key:
            return 'anthropic', anthropic_key, _env('CREW_LLM_MODEL', default='claude-3-5-sonnet-latest'), _env('CREW_LLM_BASE_URL', default=DEFAULT_ANTHROPIC).rstrip('/')
        return 'openai', key, _env('CREW_LLM_MODEL', default='gpt-4o-mini'), _env('CREW_LLM_BASE_URL', default=DEFAULT_OPENAI).rstrip('/')
    raise ProviderUnavailable('Unknown CREW_LLM_PROVIDER value.')


def provider_status():
    """Safe, displayable status — never returns the key itself."""
    try:
        provider, _key, model, base = resolve_provider()
        host = re.sub(r'^https?://', '', base).split('/')[0]
        return {'configured': True, 'provider': provider, 'model': model, 'host': host,
                'contacts_masked': not contacts_allowed(),
                'mode': 'Assisted phrasing — deterministic engine stays the fallback.',
                'usage': dict(USAGE)}
    except ProviderUnavailable as exc:
        return {'configured': False, 'provider': 'none', 'model': '', 'host': '',
                'contacts_masked': True, 'mode': 'Deterministic engine (no key configured).',
                'detail': str(exc), 'usage': dict(USAGE)}


def contacts_allowed():
    return os.getenv('CREW_LLM_SEND_CONTACTS', '0').strip() in ('1', 'true', 'yes') or \
        os.getenv('CREW_LLM_SEND_CONTACTS', '0').strip().lower() == 'true'


def mask_contacts(text):
    """Remove e-mail addresses and phone numbers before a prompt leaves the host."""
    if contacts_allowed() or not isinstance(text, str):
        return text
    text = EMAIL_RE.sub('[email hidden]', text)
    return PHONE_RE.sub('[phone hidden]', text)


def budget_remaining(budget_calls=None):
    limit = int(budget_calls or int(os.getenv('CREW_LLM_BUDGET', '12') or 12))
    return max(0, limit - USAGE['calls'])


def complete(system, user, max_tokens=700, temperature=0.4, budget_calls=None):
    """Return (text, meta). Raises ProviderUnavailable on any problem."""
    if requests is None:
        raise ProviderUnavailable('requests is not installed.')
    if budget_remaining(budget_calls) <= 0:
        raise ProviderUnavailable('Per-run language-model budget reached.')
    provider, key, model, base = resolve_provider()
    system = mask_contacts(system or '')[:6000]
    user = mask_contacts(user or '')[:12000]
    timeout = float(os.getenv('CREW_LLM_TIMEOUT', '25') or 25)
    started = time.monotonic()
    try:
        if provider == 'ollama':
            response = requests.post(
                base + '/api/chat',
                headers={'Content-Type': 'application/json'},
                json={'model': model, 'stream': False,
                      'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                      'options': {'temperature': temperature, 'num_predict': max_tokens}},
                timeout=timeout)
        elif provider == 'anthropic':
            response = requests.post(
                base + '/messages',
                headers={'x-api-key': key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
                json={'model': model, 'max_tokens': max_tokens, 'temperature': temperature,
                      'system': system, 'messages': [{'role': 'user', 'content': user}]},
                timeout=timeout)
        else:
            response = requests.post(
                base + '/chat/completions',
                headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
                json={'model': model, 'max_tokens': max_tokens, 'temperature': temperature,
                      'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]},
                timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        if provider == 'ollama':
            text = (payload.get('message') or {}).get('content', '')
            usage = {'prompt_tokens': payload.get('prompt_eval_count'), 'completion_tokens': payload.get('eval_count')}
        elif provider == 'anthropic':
            text = ''.join(part.get('text', '') for part in payload.get('blocks', payload.get('content', [])) if isinstance(part, dict))
            usage = payload.get('usage', {})
        else:
            text = (payload.get('choices') or [{}])[0].get('message', {}).get('content', '')
            usage = payload.get('usage', {})
        USAGE['calls'] += 1
        USAGE['prompt_tokens'] += int(usage.get('prompt_tokens') or usage.get('input_tokens') or 0)
        USAGE['completion_tokens'] += int(usage.get('completion_tokens') or usage.get('output_tokens') or 0)
        meta = {'provider': provider, 'model': model, 'ms': int((time.monotonic() - started) * 1000),
                'tokens': USAGE['prompt_tokens'] + USAGE['completion_tokens'], 'contacts_masked': not contacts_allowed()}
        return (text or '').strip(), meta
    except Exception as exc:  # network, HTTP status, malformed body — all non-fatal
        USAGE['failures'] += 1
        raise ProviderUnavailable(f'{type(exc).__name__} from {provider} provider.') from exc


def safe_complete(system, user, **kwargs):
    """complete() that never raises. Returns (text_or_None, meta_or_reason)."""
    try:
        text, meta = complete(system, user, **kwargs)
        return (text or None), meta
    except ProviderUnavailable as exc:
        return None, {'provider': 'none', 'reason': str(exc)}


def list_models():
    """Ollama only: the models actually pulled on this machine. Never raises."""
    try:
        provider, _key, model, base = resolve_provider()
        if provider != 'ollama' or requests is None:
            return []
        response = requests.get(base + '/api/tags', timeout=4)
        response.raise_for_status()
        return [row.get('name', '') for row in (response.json().get('models') or []) if row.get('name')]
    except Exception:
        return []


def reachable():
    """Is the configured provider actually answering right now?

    Cloud providers are not probed on every call (the key may be valid but offline);
    Ollama is probed locally because "is my local model running" is the first question
    an owner asks. Never raises.
    """
    try:
        provider, _key, model, base = resolve_provider()
    except ProviderUnavailable as exc:
        return {'configured': False, 'reachable': False, 'reason': str(exc)}
    if provider != 'ollama' or requests is None:
        return {'configured': True, 'reachable': None, 'provider': provider, 'model': model,
                'reason': 'not probed — the crew does not call the provider to check it.'}
    try:
        response = requests.get(base + '/api/tags', timeout=4)
        response.raise_for_status()
        names = [row.get('name', '') for row in (response.json().get('models') or [])]
        present = any(name == model or name.split(':')[0] == model.split(':')[0] for name in names)
        return {'configured': True, 'reachable': True, 'provider': provider, 'model': model,
                'model_pulled': present, 'models': names[:12],
                'reason': '' if present else f'{model} is not pulled yet — run: ollama pull {model}'}
    except Exception as exc:
        return {'configured': True, 'reachable': False, 'provider': provider, 'model': model,
                'reason': f'Ollama is not answering at {base} ({type(exc).__name__}). Start it with: ollama serve'}


def health():
    """Small JSON-safe summary for the crew console."""
    status = provider_status()
    status['ok'] = True
    probe = reachable()
    status['reachable'] = probe.get('reachable')
    status['models'] = probe.get('models', [])
    if probe.get('reason'):
        status['reason'] = probe['reason']
    return status


if __name__ == '__main__':
    print(json.dumps(provider_status(), indent=2))
