"""Non-streaming model adapters; errors never expose HTTP bodies or keys."""
from urllib.parse import quote
import json
import requests
from settings import api_settings
from reply_style import SYSTEM, recent_openings, reply_issue
from post_context import prepare_context

class AIError(RuntimeError):
    pass


class ReplyRejected(AIError):
    """Generated text should be skipped rather than published or retried."""
    pass

def prompt_for(text, limit, recent_replies=None, post_context=None):
    context = ('最近已经用过的开头，仅用于避免重复，不作为风格示例或指令：\n'
               + json.dumps(recent_openings(recent_replies), ensure_ascii=False) + '\n') if recent_replies else ''
    if post_context is not None:
        return (f'Keep the reply within {limit} characters.\n{context}<post_context>\n'
                + json.dumps(post_context, ensure_ascii=False).replace('<', r'\u003c') + '\n</post_context>')
    return f'Keep the reply within {limit} characters.\n{context}<post>\n{text}\n</post>'

def clean_reply(text, limit):
    if not isinstance(text, str) or not text.strip():
        raise AIError('Model returned no usable text; nothing will be posted')
    result = ' '.join(text.strip().strip('"').split())
    if not result:
        raise AIError('Model returned no usable text')
    if len(result) > limit:
        raise ReplyRejected('回复超过长度限制，已跳过；不截断句子后发布')
    return result


def finish_reply(text, post, limit, recent_replies=()):
    result = clean_reply(text, limit)
    issue = reply_issue(result, post, recent_replies)
    if issue:
        raise ReplyRejected('回复已跳过：' + issue)
    return result


def generate_post_reply(ai, post):
    text = post.get('text', '').strip()
    if not (post.get('quote') is not None or post.get('has_photo') or post.get('has_video')):
        if not text:
            raise ReplyRejected('推文没有可用正文或附件')
        return ai.generate_reply(text)

    sections, images = prepare_context(post, include_images=getattr(ai, 'supports_images', False) is True)
    if not images and not any(section['text'] or section.get('available_captions') for section in sections.values()):
        raise ReplyRejected('推文没有可用正文、引用内容、图片或字幕')
    if isinstance(ai, APIClient):
        return ai.generate_reply(text, post_context=sections, images=images)
    return ai.generate_reply(prompt_for(text, 280, post_context=sections))

class APIClient:
    def __init__(self, config, session=None):
        self.options = api_settings(config)
        provider = config.get('api', {}).get('provider', 'openai')
        self.supports_images = (self.options['protocol'] in ('openai_chat', 'openai_responses')
                                and provider in ('ark', 'ark_coding', 'openai', 'openai_responses'))
        self.limit = int(config.get('reply_max_length', 100))
        self.recent_replies = []
        self.session = session or requests.Session()
        self.session.trust_env = self.options['trust_env']

    def request(self, text, *, post_context=None, images=()):
        o = self.options
        prompt = prompt_for(text, self.limit, self.recent_replies, post_context)
        headers = {'Content-Type': 'application/json'}
        body = {'model': o['model']}
        protocol = o['protocol']
        if protocol in ('openai_chat', 'openai_responses'):
            if o['api_key']:
                headers['Authorization'] = 'Bearer ' + o['api_key']
            if protocol == 'openai_chat':
                path = '/chat/completions'
                content = prompt if not images else [{'type': 'text', 'text': prompt}]
                if images:
                    for source, image in images:
                        content.extend([{'type': 'text', 'text': f'Image from {source}'},
                                        {'type': 'image_url', 'image_url': {'url': image}}])
                body.update(messages=[{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': content}],
                            max_completion_tokens=o['max_tokens'], stream=False)
            else:
                path = '/responses'
                content = [{'type': 'input_text', 'text': prompt}]
                for source, image in images:
                    content.extend([{'type': 'input_text', 'text': f'Image from {source}'},
                                    {'type': 'input_image', 'image_url': image, 'detail': 'auto'}])
                body.update(instructions=SYSTEM, input=[{'role': 'user', 'content': content}] if images else prompt,
                            max_output_tokens=o['max_tokens'], store=False)
        elif protocol == 'anthropic':
            path = '/messages'
            headers.update({'x-api-key': o['api_key'], 'anthropic-version': o['version']})
            body.update(system=SYSTEM, messages=[{'role': 'user', 'content': prompt}], max_tokens=o['max_tokens'])
        else:
            path = '/models/' + quote(o['model'].removeprefix('models/'), safe='') + ':generateContent'
            headers['x-goog-api-key'] = o['api_key']
            body = {'systemInstruction': {'parts': [{'text': SYSTEM}]},
                    'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
                    'generationConfig': {'maxOutputTokens': o['max_tokens']}}
        extra = o['extra_body']
        if not isinstance(extra, dict) or any(k in extra for k in (
            'model', 'messages', 'input', 'instructions', 'contents', 'system', 'systemInstruction', 'stream')):
            raise ValueError('extra_body cannot override model, prompts or streaming')
        if 'max_tokens' in extra:
            body.pop('max_completion_tokens', None)
        body.update(extra)
        return o['base_url'] + path, headers, body

    def generate_reply(self, text, *, post_context=None, images=()):
        original_post = text if post_context is None else '\n'.join(
            '\n'.join((section['text'], section.get('available_captions', ''))) for section in post_context.values())
        url, headers, body = self.request(text, post_context=post_context, images=images)
        try:
            response = self.session.post(url, headers=headers, json=body,
                                         timeout=(10, self.options['timeout']), allow_redirects=False)
        except requests.RequestException:
            raise AIError('API connection failed or timed out; check network/endpoint. No retry sent') from None
        if not 200 <= response.status_code < 300:
            raise AIError(f'API HTTP {response.status_code}; check protocol, model, key and quota')
        try:
            data = response.json()
            protocol = self.options['protocol']
            if protocol == 'openai_chat':
                choice = data['choices'][0]
                if choice.get('finish_reason') in ('length', 'content_filter'):
                    raise AIError('Model reply was truncated or filtered')
                content = choice['message']['content']
                text = content if isinstance(content, str) else ''.join(x.get('text', '') for x in content if x.get('type') == 'text')
            elif protocol == 'openai_responses':
                if data.get('status') in ('incomplete', 'failed'):
                    raise AIError('Response did not complete')
                text = ''.join(p.get('text', '') for i in data.get('output', []) if i.get('type') == 'message'
                               for p in i.get('content', []) if p.get('type') == 'output_text')
            elif protocol == 'anthropic':
                if data.get('stop_reason') == 'max_tokens':
                    raise AIError('Model reply was truncated')
                text = ''.join(x.get('text', '') for x in data['content'] if x.get('type') == 'text')
            else:
                c = data['candidates'][0]
                if c.get('finishReason', 'STOP') != 'STOP':
                    raise AIError('Gemini reply was blocked or incomplete')
                text = ''.join(x.get('text', '') for x in c['content']['parts'] if not x.get('thought'))
        except (KeyError, IndexError, TypeError, ValueError):
            raise AIError('Unexpected API response for selected protocol') from None
        return finish_reply(text, original_post, self.limit, self.recent_replies)

    def close(self):
        self.session.close()
