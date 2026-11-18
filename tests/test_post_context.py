import json
import unittest
from unittest.mock import Mock, patch

from ai_client import APIClient, ReplyRejected, generate_post_reply
from post_context import prepare_context, public_photo_url


class PostContextTests(unittest.TestCase):
    def client(self, reply='The blue header stands out.', protocol='openai_chat'):
        session = Mock()
        session.post.return_value.status_code = 200
        session.post.return_value.json.return_value = {'choices': [{'message': {'content': reply}}]}
        provider = 'ark_coding' if protocol == 'openai_chat' else 'openai_responses'
        with patch.dict('os.environ', {'LLM_API_KEY': 'fixture-key'}, clear=True):
            return APIClient({'api': {'provider': provider, 'model': 'fixture-model', 'protocol': protocol}}, session)

    def test_image_only_post_and_quoted_photo_are_separate_in_the_model_request(self):
        photo = 'https://pbs.twimg.com/media/fixture.png?name=small'
        post = {'text': '', 'has_photo': True, 'images': [photo],
                'quote': {'text': 'Quoted author describes the old layout', 'has_photo': True, 'images': [photo]}}
        client = self.client()
        with patch('post_context.download_photo', return_value='data:image/png;base64,abcd') as fetch:
            self.assertEqual(generate_post_reply(client, post), 'The blue header stands out.')
        fetch.assert_called_once_with('https://pbs.twimg.com/media/fixture.png?name=large')
        content = client.session.post.call_args.kwargs['json']['messages'][1]['content']
        payload = json.loads(content[0]['text'].split('<post_context>\n')[1].split('\n</post_context>')[0])
        self.assertEqual(payload['target']['text'], '')
        self.assertIn('Quoted author', payload['quoted']['text'])
        self.assertEqual([part['text'] for part in content[1:] if part['type']=='text'],
                         ['Image from target', 'Image from quoted'])
        self.assertEqual(sum(part['type']=='image_url' for part in content), 2)

    def test_video_passes_only_text_and_captions(self):
        post = {'text': 'Service update', 'has_video': True, 'captions': 'Trains resume Monday',
                'has_photo': True, 'images': ['https://pbs.twimg.com/media/fixture.png']}
        client = self.client(reply='Good to know the trains resume Monday.')
        with patch('post_context.download_photo') as fetch:
            generate_post_reply(client, post)
        fetch.assert_not_called()
        content = client.session.post.call_args.kwargs['json']['messages'][1]['content']
        self.assertIsInstance(content, str)
        self.assertIn('Trains resume Monday', content)
        self.assertIn('"has_video": true', content)

    def test_missing_media_or_model_skip_does_not_yield_a_draft(self):
        client = self.client(reply='[[SKIP_REPLY]]')
        for post in ({'has_video': True}, {'has_photo': True, 'images': ['https://example.com/photo.png']}):
            with self.assertRaises(ReplyRejected):
                generate_post_reply(client, post)
        client.session.post.assert_not_called()
        with self.assertRaises(ReplyRejected):
            generate_post_reply(client, {'text': 'What do you think of this?', 'has_video': True})
        client.session.post.assert_called_once()

    def test_only_public_photo_cdn_urls_are_fetched(self):
        for url in ('https://pbs.twimg.com.evil.com/media/a', 'https://key@pbs.twimg.com/media/a',
                    'http://pbs.twimg.com/media/a', 'https://pbs.twimg.com/profile_images/a'):
            self.assertIsNone(public_photo_url(url))
        self.assertEqual(public_photo_url('https://pbs.twimg.com/media/a?format=png&token=secret'),
                         'https://pbs.twimg.com/media/a?name=large&format=png')
        with patch('post_context.download_photo', return_value=None):
            context, images = prepare_context({'text': 'An update', 'has_photo': True,
                'images':['https://pbs.twimg.com/media/a']}, include_images=True)
        self.assertTrue(context['target']['some_images_unavailable'])
        self.assertEqual(images, [])

    def test_responses_adapter_builds_input_image(self):
        client = self.client(protocol='openai_responses')
        _, _, body = client.request('', post_context={'target': {'text': ''}},
                                    images=[('target', 'data:image/png;base64,abcd')])
        self.assertEqual(body['input'][0]['content'][-1], {
            'type': 'input_image', 'image_url': 'data:image/png;base64,abcd', 'detail': 'auto'})
