import os
import json
import subprocess
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from browser import create_browser
from existing_chrome import ExistingChrome, chrome_endpoint


@contextmanager
def chrome_profile_directory():
    directory = tempfile.TemporaryDirectory()
    try:
        yield directory.name
    finally:
        # Windows may release Chrome's dictionary/cache handles after process exit.
        for attempt in range(30):
            try:
                directory.cleanup()
                break
            except PermissionError:
                if attempt == 29:
                    raise
                time.sleep(0.1)


class EndpointTests(unittest.TestCase):
    def test_missing_permission_explains_how_to_enable_it(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'chrome://inspect'):
                chrome_endpoint({'user_data_dir': directory})

    def test_discovery_and_malformed_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'DevToolsActivePort'
            path.write_text('9222\n/devtools/browser/example\n')
            self.assertEqual(chrome_endpoint({'user_data_dir': directory}),
                             'ws://127.0.0.1:9222/devtools/browser/example')
            for content in ('', '9222', '0\n/devtools/browser/example', '9222\n//remote.example/path'):
                path.write_text(content)
                with self.assertRaises(RuntimeError):
                    chrome_endpoint({'user_data_dir': directory})

    def test_remote_and_credentialed_endpoints_are_rejected(self):
        for endpoint in ('ws://example.com:9222/devtools/browser/a',
                         'http://user:password@localhost:9222', 'file:///tmp/browser'):
            with self.assertRaises(ValueError):
                chrome_endpoint({'debugger_url': endpoint})

    def test_attachment_does_not_launch_selenium_or_change_doubao(self):
        config = {'twitter_browser': {'mode': 'existing_chrome'}}
        with patch('existing_chrome.ExistingChrome', return_value='attached'), \
             patch('browser.webdriver.Chrome', return_value=Mock()) as selenium:
            self.assertEqual(create_browser(config, 'twitter'), 'attached')
            selenium.assert_not_called()
            with tempfile.TemporaryDirectory() as directory:
                create_browser({**config, '_root': directory}, 'doubao')
            selenium.assert_called_once()


@unittest.skipUnless(os.getenv('RUN_BROWSER_TESTS') == '1', 'Set RUN_BROWSER_TESTS=1 for real Chrome attachment')
class RealAttachmentTests(unittest.TestCase):
    def test_shared_workflow_and_disconnect_preserve_original_browser(self):
        from playwright.sync_api import sync_playwright
        import main

        with chrome_profile_directory() as directory:
            # Separate test profile: never use the user's personal Chrome data here.
            with sync_playwright() as runtime:
                chrome = runtime.chromium.executable_path
            if os.name == 'nt':
                chrome = str(Path(os.environ['PROGRAMFILES']) / 'Google/Chrome/Application/chrome.exe')
            elif not Path(chrome).exists():
                self.skipTest('Install Playwright Chromium for this attachment test')
            process = subprocess.Popen([chrome, '--headless=new', '--remote-debugging-port=0',
                                        '--user-data-dir=' + directory, '--no-first-run',
                                        '--no-default-browser-check', 'about:blank'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            driver = None
            session = requests.Session()
            session.trust_env = False
            try:
                port_file = Path(directory) / 'DevToolsActivePort'
                deadline = time.monotonic() + 15
                while not port_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.1)
                driver = ExistingChrome({'twitter_browser': {'user_data_dir': directory}})
                from continuous import ContinuousRunner
                from activity import ActivityStore, post_id
                from ai_client import ReplyRejected
                from test_continuous import reply_response
                continuous = ContinuousRunner({'_root':directory,'my_username':'owner',
                    'twitter_browser':{'mode':'existing_chrome'}},execute=True)
                continuous.store=ActivityStore(Path(directory)/'continuous.db','owner')
                continuous.network_limit=False
                continuous.ai=Mock()
                continuous.ai.generate_reply.return_value='Specific fixture reply'
                submissions=[]
                fixture='''<a data-testid="AppTabBar_Profile_Link" href="/owner">Profile</a>
                    <article data-testid="tweet"><a href="https://x.com/other/status/123"><time>Now</time></a>
                    <div data-testid="tweetText">A local fixture post</div>
                    <button data-testid="like" onclick="this.dataset.testid='unlike'">Like</button>
                    <button data-testid="reply" onclick="openReply()">Reply</button></article>
                    <script>function openReply(){const d=document.createElement('div');d.setAttribute('role','dialog');
                    document.body.appendChild(d);setTimeout(()=>{const b=document.createElement('div');
                    b.contentEditable='true';b.style.minHeight='30px';b.dataset.testid='tweetTextarea_0';
                    const s=document.createElement('button');s.dataset.testid='tweetButton';s.textContent='Send';
                    s.onclick=async()=>{const parent=location.pathname.split('/').pop();
                    await fetch('/i/api/graphql/test/CreateTweet?parent='+parent,{method:'POST',body:b.innerText});d.remove()};
                    d.append(b,s)},200)}</script>'''
                follow_fixture='''<a data-testid="AppTabBar_Profile_Link" href="/owner">Profile</a>
                    <aside><div data-testid="UserCell"><button data-testid="900-follow"
                    aria-label="回关 @recommendation" onclick="window.bad=true">回关</button></div></aside>
                    <main data-testid="primaryColumn">
                    <div data-testid="UserCell"><a href="/friend">Friend</a>
                    <div role="button" data-testid="100-follow" aria-label="回关 @friend"
                    onclick="this.dataset.testid='100-unfollow';this.innerText='正在关注';window.follows=(window.follows||0)+1;fetch('/i/api/1.1/friendships/create.json?ok=1',{method:'POST'})">回关</div></div>
                    <div data-testid="UserCell"><button data-testid="101-follow"
                    aria-label="关注 @ordinary" onclick="window.bad=true">关注</button></div>
                    <div data-testid="UserCell"><button data-testid="102-unfollow"
                    aria-label="正在关注 @old" onclick="window.bad=true">正在关注</button></div>
                    <div data-testid="UserCell"><button data-testid="103-follow"
                    aria-label="回关 @owner" onclick="window.bad=true">回关</button></div>
                    <div data-testid="UserCell"><button data-testid="104-follow"
                    aria-label="回关 @limited" onclick="this.dataset.testid='104-unfollow';this.innerText='正在关注';fetch('/i/api/1.1/friendships/create.json',{method:'POST'})">回关</button></div>
                    </main>'''
                follow_requests=[]
                def route_fixture(route):
                    if '/verified_followers' in route.request.url:
                        route.fulfill(status=200,content_type='text/html; charset=utf-8',body=follow_fixture)
                    elif '/friendships/create' in route.request.url:
                        if '?ok=1' in route.request.url:
                            route.fulfill(status=200,content_type='application/json',body=json.dumps({'id_str':'100','following':True}))
                        else:
                            follow_requests.append(route.request.url)
                            route.fulfill(status=429,headers={'retry-after':'7200'},content_type='application/json',
                                body=json.dumps({'errors':[{'code':161,'message':'Follow rate limit: too quickly'}]}))
                    elif '/CreateTweet' in route.request.url:
                        submissions.append(route.request.post_data)
                        parent=route.request.url.rsplit('=',1)[-1]
                        if parent=='129':
                            route.abort()
                        else:
                            reply_id='457' if parent=='130' else '456'
                            route.fulfill(status=200, content_type='application/json',
                                          body=json.dumps(reply_response(parent=parent, identity=reply_id)))
                    else:
                        identity=post_id(route.request.url) or '123'
                        if identity=='128':
                            route.fulfill(status=200, content_type='text/html', body='<main>Post unavailable</main>')
                            return
                        html=fixture.replace('/status/123','/status/'+identity)
                        if identity in ('125','126','127'):
                            media='''<div data-testid="videoPlayer"><video></video></div>'''
                            if identity=='125':
                                media='''<div role="link" tabindex="0"><div data-testid="User-Name">Quote author</div>
                                    <a href="/quoted/status/777"><time>Earlier</time></a>
                                    <div data-testid="tweetText">Quoted text only</div>
                                    <div data-testid="tweetPhoto"><img src="https://pbs.twimg.com/media/Fixture.png"></div></div>'''
                            if identity=='127':
                                media+='''<script>
                                    const track=document.querySelector('video').addTextTrack('captions','en');
                                    track.mode='hidden';
                                    track.addCue(new VTTCue(0,2,'Train services resume next Monday.'));
                                    </script>'''
                            html=html.replace('<div data-testid="tweetText">A local fixture post</div>',media)
                        route.fulfill(status=200,content_type='text/html; charset=utf-8',body=html)
                driver.page.route('https://x.com/**',route_fixture)
                # Keep fixture images local. The model attachment download has a separate test.
                driver.page.route('https://pbs.twimg.com/**',lambda route: route.abort())
                try:
                    from follow_back import FollowBackWorker
                    worker=FollowBackWorker(continuous)
                    continuous.follow_back=worker
                    worker.page=driver.page
                    driver.page.on('response',worker.observe)
                    try:
                        worker.load()
                        self.assertTrue(worker.tick(driver.page.context))
                        self.assertEqual(continuous.store.follow_status('100'),'confirmed')
                        self.assertEqual(driver.page.evaluate('window.follows'),1)
                        self.assertFalse(driver.page.evaluate('Boolean(window.bad)'))
                        self.assertFalse(worker.tick(driver.page.context))
                        worker.next_check=0
                        self.assertTrue(worker.tick(driver.page.context))
                        self.assertEqual(continuous.store.follow_status('104'),'limited')
                        self.assertGreater(continuous.store.follow_state()['resume_at'],time.time()+7190)
                        self.assertFalse(worker.tick(driver.page.context))
                        self.assertEqual(len(follow_requests),1)
                        for identity in ('101','102','103','900'):
                            self.assertIsNone(continuous.store.follow_status(identity))
                    finally:
                        driver.page.remove_listener('response',worker.observe)
                    item={'url':'https://x.com/other/status/123','text':'A local fixture post'}
                    with patch.object(continuous,'random_pause'), patch('continuous.POST_RENDER_TIMEOUT_MS', 300):
                        self.assertFalse(continuous.process({'url':'https://x.com/other/status/128'},driver.page))
                        self.assertEqual(continuous.skipped,1)
                        self.assertFalse(continuous.store.contains('128'))
                        continuous.ai.generate_reply.assert_not_called()
                        self.assertEqual(submissions,[])
                        self.assertTrue(continuous.process(item,driver.page))
                        self.assertFalse(continuous.process(item,driver.page))
                    self.assertEqual(submissions,['Specific fixture reply'])
                    continuous.ai.generate_reply.assert_called_once()
                    self.assertTrue(continuous.store.contains('123'))
                    continuous.ai.generate_reply.side_effect=ReplyRejected('包含虚构经历')
                    with patch.object(continuous,'random_pause'):
                        self.assertFalse(continuous.process({'url':'https://x.com/other/status/124',
                            'text':'Another fixture post'},driver.page))
                    self.assertEqual(submissions,['Specific fixture reply'])
                    self.assertEqual(driver.page.locator('[data-testid="unlike"]').count(),0)
                    self.assertEqual(driver.page.locator('[role="dialog"]').count(),0)
                    self.assertFalse(continuous.store.contains('124'))
                    from post_context import READ_POST
                    continuous.ai.generate_reply.reset_mock(side_effect=True)
                    with patch.object(continuous,'random_pause'):
                        self.assertFalse(continuous.process({'url':'https://x.com/other/status/126'},driver.page))
                    continuous.ai.generate_reply.assert_not_called()
                    self.assertEqual(driver.page.locator('[data-testid="unlike"]').count(),0)
                    self.assertEqual(driver.page.locator('[role="dialog"]').count(),0)
                    for identity in ('125','127'):
                        driver.page.goto(f'https://x.com/other/status/{identity}')
                        post=driver.page.locator('[data-testid="tweet"]').evaluate(READ_POST)
                        self.assertTrue(continuous.candidate_is_new(post))
                        self.assertEqual(post_id(post['url']),identity)
                        self.assertEqual(post['text'],'')
                        if identity=='125':
                            self.assertFalse(post['has_photo'])
                            self.assertEqual(post['quote']['text'],'Quoted text only')
                            self.assertEqual(post['quote']['images'],['https://pbs.twimg.com/media/Fixture.png'])
                        else:
                            self.assertTrue(post['has_video'])
                            self.assertEqual(post['captions'],'Train services resume next Monday.')
                    timeout_item={'url':'https://x.com/other/status/129', 'text':'Unconfirmed fixture post'}
                    next_item={'url':'https://x.com/other/status/130', 'text':'Next fixture post'}
                    continuous.ai.generate_reply.side_effect=['Unconfirmed fixture reply', 'Next fixture reply']
                    with patch.object(continuous,'random_pause'), patch('continuous.SEND_CONFIRMATION_TIMEOUT_MS',1800):
                        self.assertFalse(continuous.process(timeout_item,driver.page))
                        self.assertFalse(continuous.candidate_is_new(timeout_item))
                        self.assertTrue(continuous.process(next_item,driver.page))
                    self.assertEqual(submissions,['Specific fixture reply', 'Unconfirmed fixture reply', 'Next fixture reply'])
                finally:
                    driver.page.unroute('https://x.com/**',route_fixture)
                    driver.page.unroute('https://pbs.twimg.com/**')
                    continuous.store.close()
                    for handler in continuous.handlers:
                        continuous.log.removeHandler(handler)
                        handler.close()
                driver.page.set_content('''<article data-testid="tweet">
                    <a href="https://x.com/example/status/123"><time>Post</time></a>
                    <div data-testid="tweetText">Delayed composer test</div>
                    <button data-testid="like" onclick="this.dataset.testid='unlike';window.liked=true">Like</button>
                    <button data-testid="reply" onclick="openReply()">Reply</button>
                    </article><script>
                    window.sends=[];
                    function openReply(){
                        const dialog=document.createElement('div');dialog.setAttribute('role','dialog');
                        document.body.appendChild(dialog);
                        setTimeout(()=>{
                            const box=document.createElement('div');box.contentEditable='true';
                            box.dataset.testid='tweetTextarea_0';box.style.minHeight='30px';
                            const send=document.createElement('button');send.dataset.testid='tweetButton';
                            send.textContent='Send';send.disabled=true;
                            box.oninput=()=>setTimeout(()=>send.disabled=false,200);
                            send.onclick=()=>{window.sends.push(box.innerText);dialog.remove()};
                            dialog.append(box,send);
                        },200);
                    }</script>''')
                execute_ai=Mock()
                execute_ai.generate_reply.return_value='One actual fixture reply'
                with patch('main.create_browser',return_value=driver), \
                     patch('main.create_ai',return_value=execute_ai), \
                     patch.object(driver,'get'),patch.object(driver,'quit'), \
                     patch('builtins.input',return_value=''),patch('main.time.sleep'):
                    main.run({'max_tweets':1,'like_tweets':True},execute=True)
                self.assertTrue(driver.execute_script('window.liked'))
                self.assertEqual(driver.execute_script('window.sends'),['One actual fixture reply'])
                driver.page.set_content('''<article data-testid="tweet">
                    <a href="https://x.com/example/status/123"><time>Post</time></a>
                    <div data-testid="tweetText">Local attachment test</div>
                    <button data-testid="like" onclick="window.clicked=true">Like</button>
                    </article><textarea></textarea>''')
                tweet = WebDriverWait(driver, 1).until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="tweet"]')))
                self.assertEqual(tweet.find_element(By.CSS_SELECTOR, 'a').get_attribute('href'),
                                 'https://x.com/example/status/123')
                driver.find_element(By.CSS_SELECTOR, 'textarea').send_keys('multiline\ntext')
                self.assertEqual(driver.page.locator('textarea').input_value(), 'multiline\ntext')
                with self.assertRaises(NoSuchElementException):
                    driver.find_element(By.CSS_SELECTOR, '.missing')
                ai = Mock()
                ai.generate_reply.return_value = 'A local preview reply'
                with patch('main.create_browser', return_value=driver), \
                     patch('main.create_ai', return_value=ai), \
                     patch.object(driver, 'get'), patch('builtins.input', return_value=''), \
                     patch('main.time.sleep'):
                    # Observe no social clicks before the normal workflow closes its own tab.
                    original_quit = driver.quit
                    def checked_quit():
                        self.assertFalse(driver.execute_script('Boolean(window.clicked)'))
                        original_quit()
                    with patch.object(driver, 'quit', side_effect=checked_quit):
                        main.run({'max_tweets': 1}, execute=False)
                ai.generate_reply.assert_called_once_with('Local attachment test')
                port = port_file.read_text().splitlines()[0]
                pages = session.get(f'http://127.0.0.1:{port}/json/list', timeout=3).json()
                self.assertTrue(any(p.get('url') == 'about:blank' for p in pages))
                self.assertIsNone(process.poll(), 'User-owned browser must stay running')
            finally:
                if driver:
                    driver.quit()
                session.close()
                if os.name == 'nt':
                    # Stop the fixture's renderer children before removing its temp profile.
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    process.terminate()
                process.wait(timeout=10)
