"""Local configuration and provider presets. Secrets never come from JSON."""
import json
import os
import math
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
PRESETS = {
    'openai': ('openai_chat', 'https://api.openai.com/v1', 'OPENAI_API_KEY'),
    'openai_responses': ('openai_responses', 'https://api.openai.com/v1', 'OPENAI_API_KEY'),
    'anthropic': ('anthropic', 'https://api.anthropic.com/v1', 'ANTHROPIC_API_KEY'),
    'gemini': ('gemini', 'https://generativelanguage.googleapis.com/v1beta', 'GEMINI_API_KEY'),
    'deepseek': ('openai_chat', 'https://api.deepseek.com/v1', 'DEEPSEEK_API_KEY'),
    'qwen': ('openai_chat', 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'DASHSCOPE_API_KEY'),
    'ark': ('openai_chat', 'https://ark.cn-beijing.volces.com/api/v3', 'VOLCENGINE_ARK_API_KEY'),
    'ark_coding': ('openai_chat', 'https://ark.cn-beijing.volces.com/api/coding/v3', 'VOLCENGINE_ARK_API_KEY'),
    'ollama': ('openai_chat', 'http://localhost:11434/v1', 'LLM_API_KEY'),
    'custom': ('openai_chat', '', 'LLM_API_KEY'),
}

def load_config(filename=None):
    path = Path(filename).resolve() if filename else ROOT / 'config.json'
    load_dotenv(path.parent / '.env', override=False)
    with path.open(encoding='utf-8') as f:
        config = json.load(f)
    for field in ('openai_api_key', 'api_key', 'password', 'username', 'my_username'):
        config.pop(field, None)
    config['my_username'] = os.getenv('TWITTER_MY_USERNAME', '')
    if config.get('ai_mode', 'doubao_web') not in ('doubao_web', 'api'):
        raise ValueError('ai_mode must be doubao_web or api')
    if not 1 <= int(config.get('max_tweets', 10)) <= 500:
        raise ValueError('max_tweets must be between 1 and 500')
    if not 10 <= int(config.get('reply_max_length', 100)) <= 280:
        raise ValueError('reply_max_length must be between 10 and 280')
    for key in ('reading_delay_seconds', 'scroll_delay_seconds', 'interaction_delay_seconds_range', 'idle_delay_seconds'):
        if key in config:
            value = config[key]
            if (not isinstance(value, list) or len(value) != 2 or
                    any(isinstance(item, bool) or not isinstance(item, (float, int)) or not math.isfinite(item) for item in value)
                    or not 0 < value[0] <= value[1] <= 86400):
                raise ValueError(f'{key} must be [positive minimum, maximum] in seconds')
    if type(config.get('continuous', False)) is not bool:
        raise ValueError('continuous must be true or false')
    if not 1 <= int(config.get('history_sync_scrolls', 15)) <= 200:
        raise ValueError('history_sync_scrolls must be between 1 and 200')
    follow = config.get('follow_back',{})
    if not isinstance(follow,dict) or type(follow.get('enabled',False)) is not bool:
        raise ValueError('follow_back must be an object with enabled=true or false')
    interval=follow.get('check_interval_seconds',300)
    if isinstance(interval,bool) or not isinstance(interval,(int,float)) or not math.isfinite(interval) or not 60 <= interval <= 86400:
        raise ValueError('follow_back.check_interval_seconds must be between 60 and 86400')
    if 'interval_seconds' in follow:
        interval=follow['interval_seconds']
        if (not isinstance(interval,list) or len(interval)!=2 or
                any(isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) for value in interval)
                or not 0 < interval[0] <= interval[1] <= 86400):
            raise ValueError('follow_back.interval_seconds must be [positive minimum, maximum]')
    if 'cooldown_seconds' in follow:
        steps=follow['cooldown_seconds']
        if (not isinstance(steps,list) or not 1 <= len(steps) <= 20 or
                any(isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0 < value <= 604800 for value in steps)
                or steps!=sorted(steps)):
            raise ValueError('follow_back.cooldown_seconds must be an increasing list of positive seconds')
    config['_root'] = str(path.parent)
    return config

def api_settings(config):
    api = config.get('api', {})
    provider = api.get('provider', 'openai')
    if provider not in PRESETS:
        raise ValueError('Unknown provider; use custom for a compatible gateway')
    protocol, base, key_env = PRESETS[provider]
    protocol = api.get('protocol') or protocol
    if protocol not in ('openai_chat', 'openai_responses', 'anthropic', 'gemini'):
        raise ValueError('Unsupported API protocol')
    base = (os.getenv('LLM_BASE_URL') or api.get('base_url') or base).rstrip('/')
    p = urlsplit(base)
    if p.username or p.password or p.query or p.fragment:
        raise ValueError('Base URL must not contain credentials, query or fragment')
    if not p.hostname or not (p.scheme == 'https' or (p.scheme == 'http' and p.hostname in ('localhost', '127.0.0.1', '::1'))):
        raise ValueError('API requires HTTPS, except localhost')
    key = os.getenv('LLM_API_KEY') or os.getenv(api.get('api_key_env') or key_env, '')
    if not key and provider != 'ollama':
        raise ValueError('API key missing: configure .env')
    model = os.getenv('LLM_MODEL') or api.get('model', '')
    if not model:
        raise ValueError('Set api.model or LLM_MODEL to a model available in your account')
    return dict(protocol=protocol, base_url=base, api_key=key, model=model,
                timeout=max(1, min(float(api.get('timeout_seconds', 120)), 600)),
                max_tokens=max(64, int(api.get('max_output_tokens', 1024))),
                version=api.get('anthropic_version', '2023-06-01'),
                trust_env=bool(api.get('trust_env', True)), extra_body=api.get('extra_body', {}))
