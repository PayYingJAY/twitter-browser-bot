import json
import os
import tempfile
import unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch
from contextlib import contextmanager

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from activity import ActivityStore, RunnerLock, own_replies, post_id
from continuous import BEIJING, ContinuousRunner, StopRequested
from settings import daily_work_hours, load_config


def reply_response(parent='123', identity='456', account='owner', text='A specific reply'):
    return {'data': {'create_tweet': {'tweet_results': {'result': {
        'rest_id': identity,
        'legacy': {'in_reply_to_status_id_str': parent, 'user_id_str': '42', 'full_text': text},
        'core': {'user_results': {'result': {'rest_id': '42', 'core': {'screen_name': account}}}}
    }}}}}


class ActivityTests(unittest.TestCase):
    def test_history_survives_restart_and_scopes_accounts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.db'
            first = ActivityStore(path, 'Owner')
            self.assertTrue(first.reserve_send('123', 'uncertain delivery'))
            first.mark_send_pending('123')
            first.close()
            second = ActivityStore(path, '@owner')
            self.assertTrue(second.contains('123'))
            self.assertFalse(second.reserve_send('123', 'must not send again'))
            second.remember('789', '999', 'Confirmed reply')
            self.assertEqual(second.recent_texts(), ['Confirmed reply'])
            other = ActivityStore(path, 'another_account')
            self.assertFalse(other.contains('123'))
            second.close()
            other.close()

    def test_extracts_actual_parent_only_for_account_owner(self):
        data = reply_response()
        self.assertEqual(own_replies(data, 'OWNER'), [('123', '456', 'A specific reply')])
        self.assertEqual(own_replies(data, 'someone_else'), [])
        self.assertEqual(own_replies({'core': None, 'legacy': None}, 'owner'), [])
        data['data']['create_tweet']['tweet_results']['result']['legacy'].pop('in_reply_to_status_id_str')
        self.assertEqual(own_replies(data, 'owner'), [])

    def test_id_ignores_handle_alias_and_tracking_parameters(self):
        self.assertEqual(post_id('https://x.com/someone/status/123?s=20'), '123')
        self.assertEqual(post_id('https://x.com/i/status/123'), '123')
        self.assertIsNone(post_id('https://x.com/home'))

    def test_second_runner_is_rejected_and_lock_released(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'runner.lock'
            first = RunnerLock(path)
            try:
                with self.assertRaises(RuntimeError):
                    RunnerLock(path)
            finally:
                first.close()
            second = RunnerLock(path)
            second.close()


class ContinuousTests(unittest.TestCase):
    @contextmanager
    def make_runner(self, directory, **config):
        runner = ContinuousRunner({'_root': directory, 'my_username': 'owner',
            'twitter_browser': {'mode': 'existing_chrome'}, **config}, execute=True)
        runner.store = ActivityStore(Path(directory) / 'activity.db', 'owner')
        runner.network_limit = False
        try:
            yield runner
        finally:
            runner.store.close()
            for handler in runner.handlers:
                runner.log.removeHandler(handler)
                handler.close()

    def test_beijing_work_hours_include_opening_and_exclude_closing(self):
        hours = {'start': '09:00', 'end': '22:00'}
        with tempfile.TemporaryDirectory() as directory, self.make_runner(directory, work_hours=hours) as runner:
            for instant, expected in [('00:59:59', False), ('01:00:00', True),
                                      ('13:59:59', True), ('14:00:00', False)]:
                with self.subTest(instant=instant):
                    now = datetime.fromisoformat(f'2026-11-18T{instant}+00:00')
                    self.assertEqual(runner.in_work_hours(now), expected)

    def test_off_hours_waits_until_next_morning(self):
        hours = {'start': '09:00', 'end': '22:00'}
        closing = datetime(2026, 11, 18, 22, tzinfo=BEIJING)
        opening = datetime(2026, 11, 19, 9, tzinfo=BEIJING)
        with tempfile.TemporaryDirectory() as directory, self.make_runner(directory, work_hours=hours) as runner:
            page = Mock()
            page.is_closed.return_value = False
            with patch('continuous.datetime', wraps=datetime) as clock, patch.object(runner, 'status') as status:
                clock.now.side_effect = [closing, closing, opening]
                self.assertTrue(runner.wait_for_work_hours(page))
            status.assert_called_once_with('off_hours', resumes_at='2026-11-19T09:00:00+08:00')
            page.wait_for_timeout.assert_called_once_with(1000)

    def test_closing_during_generation_prevents_interaction(self):
        hours = {'start': '09:00', 'end': '22:00'}
        with tempfile.TemporaryDirectory() as directory, self.make_runner(directory, work_hours=hours) as runner:
            url = 'https://x.com/other/status/123'
            page = Mock(url=url)
            page.goto.return_value.status = 200
            target = page.locator.return_value.filter.return_value.first
            target.evaluate.return_value = {'url': url, 'text': 'A test post'}
            control = target.locator.return_value
            control.count.return_value = 1
            runner.ai = Mock()
            with patch('continuous.datetime', wraps=datetime) as clock, \
                 patch.object(runner, 'guard'), patch.object(runner, 'random_pause'), \
                 patch.object(runner, 'visible_own_reply', return_value=False):
                clock.now.return_value = datetime(2026, 11, 18, 21, 59, tzinfo=BEIJING)

                def generate_reply(_):
                    clock.now.return_value = datetime(2026, 11, 18, 22, tzinfo=BEIJING)
                    return 'A test reply'

                runner.ai.generate_reply.side_effect = generate_reply
                self.assertFalse(runner.process({'url': url}, page))
            runner.ai.generate_reply.assert_called_once()
            control.first.click.assert_not_called()
            page.expect_response.assert_not_called()
            self.assertFalse(runner.store.contains('123'))

    def test_work_hours_reject_invalid_ranges(self):
        self.assertIsNone(daily_work_hours({}))
        for hours in [True, {'start': '9:00', 'end': '22:00'}, {'start': '09:00', 'end': '24:00'},
                      {'start': '22:00', 'end': '09:00'}, {'start': '09:00', 'end': '09:00'}]:
            with self.subTest(hours=hours), self.assertRaises(ValueError):
                daily_work_hours({'work_hours': hours})

    def test_own_and_previously_replied_are_filtered_before_model(self):
        with tempfile.TemporaryDirectory() as directory, self.make_runner(directory) as runner:
            runner.store.remember('123', '456', 'old reply', 'imported')
            self.assertFalse(runner.candidate_is_new({'url': 'https://x.com/OWNER/status/789', 'text': 'self'}))
            self.assertFalse(runner.candidate_is_new({'url': 'https://x.com/other/status/123', 'text': 'old'}))
            self.assertTrue(runner.candidate_is_new({'url': 'https://x.com/other/status/777', 'text': 'new'}))

    def test_navigation_timeout_skips_without_generating_a_reply(self):
        with tempfile.TemporaryDirectory() as directory, self.make_runner(directory) as runner:
            page = Mock(url='https://x.com/other/status/123')
            page.goto.side_effect = PlaywrightTimeoutError('navigation timeout')
            page.locator.return_value.count.return_value = 0
            page.locator.return_value.all_text_contents.return_value = []
            runner.ai = Mock()
            self.assertFalse(runner.process({'url': page.url}, page))
            self.assertEqual(runner.skipped, 1)
            runner.ai.generate_reply.assert_not_called()
            self.assertFalse(runner.store.contains('123'))

    def test_navigation_timeout_on_login_page_still_pauses(self):
        with tempfile.TemporaryDirectory() as directory, self.make_runner(directory) as runner:
            page = Mock(url='https://x.com/i/flow/login')
            page.goto.side_effect = PlaywrightTimeoutError('navigation timeout')
            with self.assertRaisesRegex(RuntimeError, '登录'):
                runner.process({'url': 'https://x.com/other/status/123'}, page)
            self.assertEqual(runner.skipped, 0)

    def test_send_confirmation_timeout_preserves_pending_reply(self):
        @contextmanager
        def unconfirmed_response(*args, **kwargs):
            yield
            raise PlaywrightTimeoutError('send confirmation timeout')

        with tempfile.TemporaryDirectory() as directory, self.make_runner(directory) as runner:
            url = 'https://x.com/other/status/123'
            page = Mock(url=url)
            page.goto.return_value.status = 200
            target = page.locator.return_value.filter.return_value.first
            target.evaluate.return_value = {'url': url, 'text': 'A test post'}
            target.locator.return_value.count.return_value = 1
            page.expect_response.side_effect = unconfirmed_response
            runner.ai = Mock()
            runner.ai.generate_reply.return_value = 'A test reply'
            with patch.object(runner, 'guard'), patch.object(runner, 'random_pause'), \
                 patch.object(runner, 'visible_own_reply', return_value=False), \
                 patch('continuous.time.monotonic', return_value=100), \
                 patch('continuous.random.uniform', return_value=75):
                self.assertFalse(runner.process({'url': url}, page))
            page.locator.return_value.last.click.assert_called_once()
            self.assertEqual(runner.skipped, 1)
            self.assertEqual(runner.wait_until, 175)
            self.assertEqual(runner.store.db.execute('SELECT status FROM replies WHERE post_id=?', ('123',)).fetchone(),
                             ('pending',))
            self.assertFalse(runner.candidate_is_new({'url': url, 'text': 'A test post'}))
            self.assertFalse(runner.store.reserve_send('123', 'must not resend'))

    def test_stop_file_and_platform_limit_stop_actions(self):
        with tempfile.TemporaryDirectory() as directory, self.make_runner(directory) as runner:
            runner.stop_file.parent.mkdir(parents=True, exist_ok=True)
            runner.stop_file.touch()
            with self.assertRaises(StopRequested):
                runner.check_stop()
            runner.stop_file.unlink()
            runner.network_limit = True
            with self.assertRaisesRegex(RuntimeError, '限流'):
                runner.guard(Mock())
            runner.network_limit = False
            page = Mock(url='https://x.com/i/flow/login')
            with self.assertRaisesRegex(RuntimeError, '登录'):
                runner.guard(page)

    def test_random_delay_uses_configured_bounds(self):
        with tempfile.TemporaryDirectory() as directory, self.make_runner(directory) as runner:
            with patch('continuous.random.uniform', return_value=91) as uniform, patch.object(runner, 'pause') as pause:
                page = Mock()
                runner.random_pause('interaction_delay_seconds_range', [60,150], page)
            uniform.assert_called_once_with(60,150)
            pause.assert_called_once_with(91,page,'waiting')

    def test_uncertain_send_reservation_is_kept_on_restart(self):
        with tempfile.TemporaryDirectory() as directory, self.make_runner(directory) as runner:
            self.assertTrue(runner.store.reserve_send('123', 'first attempt'))
            response = Mock(url='https://x.com/i/api/graphql/id/TweetDetail', status=200)
            response.json.return_value = reply_response('777', '888')
            runner.observe_response(response)
            self.assertTrue(runner.store.contains('123'))
            self.assertTrue(runner.store.contains('777'))
            self.assertFalse(runner.store.reserve_send('123', 'second attempt'))

    def test_rejects_invalid_random_ranges(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            path = Path(directory) / 'config.json'
            for value in ([150,60],[-1,2],[0,2],[True,3],[1,float('nan')],'60,150'):
                path.write_text(json.dumps({'interaction_delay_seconds_range':value}))
                with self.assertRaises(ValueError):
                    load_config(path)

    def test_history_fallback_resolves_parent_from_actual_conversation(self):
        with tempfile.TemporaryDirectory() as directory, self.make_runner(directory) as runner:
            runner.config['history_sync_scrolls']=1
            page=Mock()
            own={'url':'https://x.com/owner/status/456','text':'Previous reply'}
            original={'url':'https://x.com/owner/status/777','text':'Own original post'}
            page.locator.return_value.evaluate_all.return_value=[own,original]
            resolver=Mock()
            resolver.is_closed.return_value=False
            resolver.locator.return_value.evaluate_all.side_effect=[
                [{'url':'https://x.com/another/status/123','text':'Parent post'},own],[original]]
            with patch.object(runner,'guard'),patch.object(runner,'pause'):
                runner.sync_history(page,resolver)
            self.assertTrue(runner.store.contains('123'))
            self.assertTrue(runner.store.knows_reply('456'))
            self.assertFalse(runner.store.contains('777'))
            self.assertEqual(runner.store.count(),1)
            self.assertTrue(runner.history_is_fresh())
            with patch('continuous.time.time',return_value=99999999999):
                self.assertFalse(runner.history_is_fresh())

    def test_closed_readonly_resolver_is_replaced_before_navigation(self):
        with tempfile.TemporaryDirectory() as directory, self.make_runner(directory) as runner:
            runner.config['history_sync_scrolls']=1
            own={'url':'https://x.com/owner/status/456','text':'Previous reply'}
            page=Mock()
            page.locator.return_value.evaluate_all.return_value=[own]
            closed=Mock()
            closed.is_closed.return_value=True
            replacement=Mock()
            replacement.locator.return_value.evaluate_all.return_value=[
                {'url':'https://x.com/other/status/123','text':'Parent'},own]
            with patch.object(runner,'guard'),patch.object(runner,'pause'), \
                 patch.object(runner,'new_work_page',return_value=replacement) as create:
                self.assertIs(runner.sync_history(page,closed),replacement)
            create.assert_called_once_with(page.context)
            closed.goto.assert_not_called()
            self.assertTrue(runner.store.contains('123'))

    def test_follow_timer_does_not_change_comment_deadline(self):
        with tempfile.TemporaryDirectory() as directory, self.make_runner(directory) as runner:
            runner.follow_back=Mock()
            runner.follow_back.tick.return_value=True
            runner.wait_until=12345
            runner.phase='candidate'
            feed=Mock()
            with patch.object(runner,'status'):
                self.assertTrue(runner.try_follow_back(feed))
            self.assertEqual(runner.wait_until,12345)
            self.assertEqual(runner.phase,'candidate')
            self.assertFalse(runner._following)
            runner.follow_back.tick.assert_called_once_with(feed.context)

    def test_follow_checks_continue_during_comment_wait_not_during_reading(self):
        with tempfile.TemporaryDirectory() as directory, self.make_runner(directory) as runner:
            page=Mock()
            page.is_closed.return_value=False
            with patch.object(runner,'status'),patch.object(runner,'try_follow_back',return_value=False) as follow:
                with patch('continuous.time.monotonic',side_effect=[0,0,0,1,1,2,2,3]):
                    runner.pause(3,page,'waiting')
                self.assertEqual(follow.call_count,3)
                follow.reset_mock()
                with patch('continuous.time.monotonic',side_effect=[0,0,0,1,1,2,2,3]):
                    runner.pause(3,page,'reading')
                follow.assert_not_called()
