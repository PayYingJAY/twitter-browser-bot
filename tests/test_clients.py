import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import requests
from ai_client import APIClient, AIError
from settings import load_config

class ProtocolTests(unittest.TestCase):
    def client(self, protocol='openai_chat', data=None, status=200, **api):
        c = {'ai_mode': 'api', 'api': {'provider': 'custom', 'protocol': protocol,
             'base_url': 'https://example.com/v1', 'model': 'test-model', **api}}
        session = Mock()
        session.post.return_value.status_code = status
        session.post.return_value.json.return_value = data
        with patch.dict(os.environ, {'LLM_API_KEY':'test-key'}, clear=True):
            return APIClient(c, session=session)

    def test_four_protocols(self):
        cases = [
            ('openai_chat', {'choices':[{'message':{'content':'Hello'},'finish_reason':'stop'}]}, '/chat/completions','Authorization'),
            ('openai_responses', {'output':[{'type':'message','content':[{'type':'output_text','text':'Hello'}]}]}, '/responses','Authorization'),
            ('anthropic', {'content':[{'type':'thinking','text':'private'},{'type':'text','text':'Hello'}]}, '/messages','x-api-key'),
            ('gemini', {'candidates':[{'content':{'parts':[{'thought':True,'text':'private'},{'text':'Hello'}]}}]}, ':generateContent','x-goog-api-key')]
        for protocol, data, suffix, header in cases:
            with self.subTest(protocol=protocol):
                c=self.client(protocol,data)
                self.assertEqual(c.generate_reply('test post'),'Hello')
                args,kw=c.session.post.call_args
                self.assertTrue(args[0].endswith(suffix))
                self.assertIn(header,kw['headers'])
                self.assertFalse(kw['allow_redirects'])
                self.assertNotIn('test-key',args[0])
                self.assertEqual(c.session.post.call_count,1)

    def test_http_error_redacts_body(self):
        c=self.client(status=401)
        c.session.post.return_value.text='test-key and private provider details'
        with self.assertRaisesRegex(AIError,'HTTP 401') as error:
            c.generate_reply('post')
        self.assertNotIn('test-key',str(error.exception))
        c.session.post.return_value.json.assert_not_called()

    def test_network_failure_redacts_and_does_not_retry(self):
        c=self.client()
        c.session.post.side_effect=requests.Timeout('test-key')
        with self.assertRaises(AIError) as e:c.generate_reply('post')
        self.assertNotIn('test-key',str(e.exception))
        self.assertEqual(c.session.post.call_count,1)

    def test_invalid_empty_and_truncated(self):
        for data in ({}, {'choices':[{'message':{'content':''}}]},
                     {'choices':[{'message':{'content':'partial'},'finish_reason':'length'}]}):
            with self.assertRaises(AIError):self.client(data=data).generate_reply('post')

    def test_compatibility_max_tokens(self):
        c=self.client(extra_body={'max_tokens':800,'thinking':{'type':'disabled'}})
        body=c.request('post')[2]
        self.assertNotIn('max_completion_tokens',body)
        self.assertEqual(body['max_tokens'],800)

    def test_no_prompt_override(self):
        with self.assertRaises(ValueError):self.client(extra_body={'messages':[]}).request('post')

    def test_reject_credentials_in_url(self):
        for base in ('https://key@example.com/v1','https://example.com/v1?key=test-key','http://example.com/v1'):
            with self.assertRaises(ValueError):self.client(base_url=base)

    def test_missing_key(self):
        with patch.dict(os.environ,{},clear=True), self.assertRaises(ValueError):
            APIClient({'api':{'provider':'openai','model':'test'}})

class ConfigTests(unittest.TestCase):
    def test_dotenv_and_secret_rejection(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{},clear=True):
            p=Path(d)
            (p/'config.json').write_text(json.dumps({'api_key':'private','password':'private','my_username':'private'}))
            (p/'.env').write_text('LLM_API_KEY=local-test-key\nTWITTER_MY_USERNAME=own_handle\n')
            c=load_config(p/'config.json')
            self.assertNotIn('api_key',c)
            self.assertNotIn('password',c)
            self.assertEqual(c['my_username'],'own_handle')
            self.assertEqual(os.environ['LLM_API_KEY'],'local-test-key')
            os.environ['LLM_API_KEY']='terminal-key'
            load_config(p/'config.json')
            self.assertEqual(os.environ['LLM_API_KEY'],'terminal-key')

class WebsiteTests(unittest.TestCase):
    def test_default_selector_covers_current_contenteditable(self):
        from doubao_web import DEFAULT_SELECTORS
        self.assertIn('[contenteditable="true"]',DEFAULT_SELECTORS['input'])

    def test_fresh_message_only(self):
        from doubao_web import DoubaoWebClient
        c=object.__new__(DoubaoWebClient)
        c.config={'doubao':{'timeout_seconds':15}}
        c.selectors={'stop':'stop'}
        c.driver=Mock()
        c.driver.find_elements.return_value=[]
        c._input=Mock(return_value=Mock())
        c._messages=Mock(side_effect=[ [('old','Old reply')], [('old','Old reply')],
                                      [('old','Old reply'),('new','Fresh reply')],
                                      [('old','Old reply'),('new','Fresh reply')] ])
        with patch('doubao_web.time.sleep'),patch('doubao_web.time.monotonic',side_effect=[0,0,1,2,3,4,9,10]):
            self.assertEqual(c.generate_reply('post'),'Fresh reply')


class WorkflowTests(unittest.TestCase):
    def setup_workflow(self):
        import main
        driver=Mock()
        tweet=Mock()
        link=Mock();link.get_attribute.return_value='https://x.com/example/status/123'
        content=Mock();content.text='A sample post'
        def elements(by,selector):
            if selector=='a[href*="/status/"]': return [link]
            if selector=='[data-testid="tweetText"]': return [content]
            return [Mock()]
        tweet.find_elements.side_effect=elements
        driver.find_elements.return_value=[tweet]
        ai=Mock();ai.generate_reply.return_value='Relevant reply'
        return main,driver,tweet,ai

    def test_preview_never_clicks(self):
        main,driver,tweet,ai=self.setup_workflow()
        with patch('main.create_browser',return_value=driver),patch('main.create_ai',return_value=ai), \
             patch('main.WebDriverWait'),patch('builtins.input',return_value=''),patch('main.time.sleep'):
            main.run({'max_tweets':1},execute=False)
        tweet.find_element.assert_not_called()
        self.assertEqual(ai.generate_reply.call_count,1)
        driver.quit.assert_called_once()
        ai.close.assert_called_once()

    def test_generation_failure_precedes_social_actions(self):
        main,driver,tweet,ai=self.setup_workflow()
        ai.generate_reply.side_effect=AIError('generation failed')
        with patch('main.create_browser',return_value=driver),patch('main.create_ai',return_value=ai), \
             patch('main.WebDriverWait'),patch('builtins.input',return_value=''),patch('main.time.sleep'), \
             self.assertRaises(AIError):
            main.run({'max_tweets':1},execute=True)
        tweet.find_element.assert_not_called()
        self.assertEqual(tweet.find_elements.call_count,2)

if __name__ == '__main__':
    unittest.main()
