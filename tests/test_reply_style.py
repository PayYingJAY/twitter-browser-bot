import unittest
from unittest.mock import Mock, patch
import os

from ai_client import APIClient, ReplyRejected, clean_reply, prompt_for
from reply_style import reply_issue, normalize_reply, SKIP_REPLY


class ReplyStyleTests(unittest.TestCase):
    def test_blocks_real_examples_of_invented_experience(self):
        for reply in ('我这边反过来，刷到的蓝V含量很高。',
                      '我发完会顺手点，算个标记。', 'I usually like my own posts.'):
            with self.subTest(reply=reply):
                self.assertIsNotNone(reply_issue(reply, '你会给自己点赞吗？'))

    def test_does_not_block_personal_opinion(self):
        self.assertIsNone(reply_issue('我觉得不用太纠结', '自己的帖子能点赞吗？'))
        self.assertIsNone(reply_issue('自己的帖子，点个赞也没啥', '你们发完会给自己点赞吗？'))

    def test_direct_habit_answers_are_not_invented(self):
        self.assertIsNotNone(reply_issue('会啊，顺手给自己点一个','你们发完会给自己点赞吗？'))
        self.assertIsNotNone(reply_issue('会顺手点一下，也算给自己捧场。','你们发完会给自己点赞吗？'))
        self.assertIsNotNone(reply_issue('想得美，我也想冲第一呢','今天想冲第一，大家让让？'))

    def test_missing_image_explanation_is_skipped_instead_of_posted(self):
        self.assertIsNotNone(reply_issue('没看到图，不好判断具体是哪里','看这张图是不是处理错了？'))
        self.assertIsNotNone(reply_issue('没说具体是哪个工具，我也不好乱讲经历','你用过这个工具吗？'))

    def test_no_unverified_platform_diagnosis(self):
        for reply in ('6分钟破百主要看冷启动。', '蓝V不进互动池，系统也不一定会推。',
                      '像是被系统限流了。'):
            self.assertIsNotNone(reply_issue(reply, '流量到100就不动了'))
        self.assertIsNone(reply_issue('先等等看，六分钟还太早', '六分钟100浏览，正常吗？'))

    def test_blocks_placeholders_and_allows_skip(self):
        self.assertIsNotNone(reply_issue('@currentuser 先报个到', '大家好'))
        self.assertIsNotNone(reply_issue(SKIP_REPLY, '说说你真实的使用经历'))

    def test_routing_mentions_do_not_defeat_duplicate_check(self):
        self.assertEqual(normalize_reply('@someone @another 这也太整齐了'), '这也太整齐了')
        self.assertIsNotNone(reply_issue('这也太整齐了', '刚好400', ['@someone 这也太整齐了']))
        self.assertIsNone(reply_issue('还好不是写了三个月才发现', '发现开源项目做过了', ['这也太整齐了']))

    def test_overlong_text_is_not_cut_mid_sentence(self):
        with self.assertRaises(ReplyRejected):
            clean_reply('这句话还没有说完就会超过限制', 10)

    def test_history_context_does_not_import_mentions_or_full_bad_examples(self):
        prompt=prompt_for('刚好都是400',100,['@someone 核心在于账号的底层逻辑应该如何理解'])
        self.assertNotIn('@someone',prompt)
        self.assertNotIn('应该如何理解',prompt)
        self.assertIn('<post>\n刚好都是400\n</post>',prompt)

    def test_quality_rejection_never_retries_request(self):
        session=Mock()
        session.post.return_value.status_code=200
        session.post.return_value.json.return_value={
            'choices':[{'message':{'content':'我发完会顺手点'},'finish_reason':'stop'}]}
        config={'api':{'provider':'custom','base_url':'https://example.com/v1','model':'test'}}
        with patch.dict(os.environ,{'LLM_API_KEY':'local-test-key'},clear=True):
            client=APIClient(config,session=session)
        with self.assertRaises(ReplyRejected):
            client.generate_reply('你会给自己点赞吗？')
        session.post.assert_called_once()
