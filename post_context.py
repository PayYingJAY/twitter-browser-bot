"""Extract the reply target and its visible context from an X article."""
import base64
import re
from urllib.parse import parse_qs, urlencode, urlsplit

import requests


READ_POST = r'''(article, summary = false) => {
    const articleSelector = '[data-testid="tweet"]';
    const quoteSelector = '[data-testid="quoteTweet"], [data-testid="quoteTweetContainer"], [data-testid="tweet"]';
    const isQuote = node => node.matches(quoteSelector) ||
        (node.matches('[role="link"][tabindex]') &&
         Boolean(node.querySelector('[data-testid="User-Name"], [data-testid="UserName"]')));
    const quotes = [...article.querySelectorAll(`${quoteSelector}, [role="link"][tabindex]`)].filter(isQuote);
    const quote = quotes.find(node => node.parentElement.closest(articleSelector) === article);
    const outsideQuotes = node => !quotes.some(card => card.contains(node));
    const belongsToArticle = node => node.closest(articleSelector) === article && outsideQuotes(node);
    const permalink = [...article.querySelectorAll('a[href*="/status/"]')].find(node =>
        belongsToArticle(node) && node.hostname === 'x.com' && node.querySelector('time') &&
        /^\/[a-z0-9_]{1,15}\/status\/\d+\/?$/i.test(node.pathname));

    function read(scope, owns) {
        const all = selector => [...scope.querySelectorAll(selector)].filter(owns);
        const text = all('[data-testid="tweetText"]')[0]?.innerText?.trim() || '';
        const players = all('video, [data-testid="videoPlayer"], [data-testid="videoComponent"]');
        const photoCards = all('[data-testid="tweetPhoto"]').filter(node =>
            !node.closest('[data-testid="videoPlayer"], [data-testid="videoComponent"]'));
        const photos = all('[data-testid="tweetPhoto"] img').filter(img =>
            photoCards.includes(img.closest('[data-testid="tweetPhoto"]')));
        const result = {text, has_video: Boolean(players.length), has_photo: Boolean(photoCards.length)};
        if (summary) return result;

        // Read captions that the browser already has. This does not play or fetch the video.
        const captions = new Set();
        for (const video of players.filter(node => node.tagName === 'VIDEO')) {
            for (const track of Array.from(video.textTracks || [])) {
                if (!['captions', 'subtitles'].includes(track.kind)) continue;
                for (const cue of Array.from(track.cues || track.activeCues || []).slice(0, 160)) {
                    captions.add((cue.getCueAsHTML?.().textContent || cue.text || '').trim());
                }
            }
        }
        for (const caption of all('[data-testid="videoCaption"], [data-testid="videoCaptions"]')) {
            if (caption.getClientRects().length) captions.add(caption.innerText.trim());
        }
        return {...result,
            images: photos.map(img => img.currentSrc || img.src).filter(Boolean),
            captions: [...captions].filter(Boolean).join('\n')};
    }

    return {url: permalink?.href || '', ...read(article, belongsToArticle),
        quote: quote ? read(quote, node => !quotes.some(card =>
            card !== quote && quote.contains(card) && card.contains(node))) : null};
}'''

POST_SUMMARY = f'nodes => nodes.map(node => ({READ_POST})(node, true)).filter(post => post.url)'

MAX_IMAGES = 4
MAX_IMAGE_BYTES = 1_500_000
IMAGE_FORMATS = {'image/jpeg', 'image/png', 'image/webp'}


def has_context(post):
    quote = post.get('quote') or {}
    return any(part.get('text', '').strip() or part.get('has_photo') or part.get('has_video')
               for part in (post, quote))


def public_photo_url(source):
    """Build a canonical URL without forwarding arbitrary hosts or query parameters."""
    try:
        parsed = urlsplit(source)
    except ValueError:
        return None
    if parsed.scheme != 'https' or parsed.netloc.lower() != 'pbs.twimg.com':
        return None
    if not re.fullmatch(r'/media/[A-Za-z0-9_-]+(?:\.(?:jpe?g|png|webp))?', parsed.path):
        return None
    file_format = parse_qs(parsed.query).get('format', [''])[0]
    query = {'name': 'large'}
    if file_format in ('jpg', 'jpeg', 'png', 'webp'):
        query['format'] = file_format
    return f'https://pbs.twimg.com{parsed.path}?{urlencode(query)}'


def download_photo(url):
    try:
        with requests.get(url, stream=True, timeout=(4, 5), allow_redirects=False) as response:
            mime = response.headers.get('content-type', '').split(';', 1)[0].strip().lower()
            if response.status_code != 200 or mime not in IMAGE_FORMATS:
                return None
            data = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                data.extend(chunk)
                if len(data) > MAX_IMAGE_BYTES:
                    return None
    except requests.RequestException:
        return None
    if not data:
        return None
    return f'data:{mime};base64,{base64.b64encode(data).decode("ascii")}'


def prepare_context(post, include_images):
    """Keep quoted material and image attachments attributed to their own authors."""
    sections = {}
    images = []
    photos = {}
    for name, part in (('target', post), ('quoted', post.get('quote'))):
        if part is None:
            continue
        section = {'text': part.get('text', '').strip()[:8000]}
        if part.get('has_video'):
            section.update(has_video=True, available_captions=part.get('captions', '').strip()[:8000])
        if part.get('has_photo'):
            urls = dict.fromkeys(filter(None, map(public_photo_url, part.get('images', ()))))
            first = len(images)
            if include_images and not part.get('has_video'):
                for url in urls:
                    if url not in photos and len(photos) < MAX_IMAGES:
                        photos[url] = download_photo(url)
                    photo = photos.get(url)
                    if photo and len(images) < MAX_IMAGES:
                        images.append((name, photo))
            section['images_attached'] = len(images) - first
            section['some_images_unavailable'] = not urls or len(images) - first < len(set(part.get('images', ())))
        sections[name] = section
    return sections, images
