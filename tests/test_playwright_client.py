"""Opt-in real Chrome tests against a local HTML fixture; no login/network required."""
import os
import tempfile
import unittest
from unittest.mock import patch
from ai_client import AIError
from doubao_web import DoubaoWebClient, create_doubao_client

HTML = '''<div contenteditable="true" role="textbox"></div>
<div id="messages"><div data-testid="receive_message"><div data-testid="message_text_content" data-streaming="false">Old answer</div><button>Like</button></div></div>
<script>
window.sent=[];
document.querySelector('[contenteditable]').addEventListener('keydown',e=>{
 if(e.key!=='Enter'||e.shiftKey)return;
 e.preventDefault(); sent.push(e.target.innerText); e.target.innerText='';
 const wrapper=document.createElement('div');wrapper.dataset.testid='receive_message';
 wrapper.innerHTML='<div data-testid="message_text_content" data-streaming="true">Partial</div><button>Like</button><span>Suggested question and timestamp</span>';
 document.querySelector('#messages').appendChild(wrapper);
 const body=wrapper.firstChild; const n=sent.length;
 setTimeout(()=>body.innerText='Final answer '+n,600);
 setTimeout(()=>body.dataset.streaming='false',1200);
});</script>'''

class FactoryTests(unittest.TestCase):
    def test_default_is_playwright(self):
        with patch('doubao_web.DoubaoWebClient',return_value='modern') as cls:
            self.assertEqual(create_doubao_client({}),'modern');cls.assert_called_once()

    def test_explicit_legacy_backend(self):
        with patch('doubao_selenium.DoubaoWebClient',return_value='legacy'):
            self.assertEqual(create_doubao_client({'doubao':{'backend':'selenium'}}),'legacy')

    def test_unknown_backend_rejected(self):
        with self.assertRaises(ValueError):create_doubao_client({'doubao':{'backend':'unknown'}})

@unittest.skipUnless(os.getenv('RUN_BROWSER_TESTS')=='1','Set RUN_BROWSER_TESTS=1 for isolated real Chrome tests')
class RealChromeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        # Constructor still launches actual persistent Chrome. Navigation is local fixture only.
        with patch('playwright.sync_api.Page.goto'):
            self.client=DoubaoWebClient({'_root':self.tmp.name,'headless':True,
                                        'doubao':{'timeout_seconds':10}})
        self.client.page.set_content(HTML)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def test_two_requests_wait_for_completion_and_exclude_metadata(self):
        self.assertEqual(self.client.generate_reply('First post\nsecond line'),'Final answer 1')
        self.assertEqual(self.client.generate_reply('Different post'),'Final answer 2')
        prompts=self.client.page.evaluate('window.sent')
        self.assertEqual(len(prompts),2)
        self.assertIn('First post\nsecond line',prompts[0])
        self.assertIn('Different post',prompts[1])

    def test_active_generation_prevents_new_submit(self):
        self.client.page.locator('[data-testid="message_text_content"]').evaluate("x => x.setAttribute('data-streaming','true')")
        with self.assertRaises(AIError):self.client.generate_reply('do not submit')
        self.assertEqual(self.client.page.evaluate('window.sent.length'),0)

    def test_timeout_never_resends(self):
        self.client.options['timeout_seconds']=0.2
        with self.assertRaises(AIError):self.client.generate_reply('one post')
        self.assertEqual(self.client.page.evaluate('window.sent.length'),1)

if __name__=='__main__':unittest.main()
