import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from activity import ActivityStore
from settings import load_config
from follow_back import FollowBackWorker, limit_kind, retry_delay


class FollowBackTests(unittest.TestCase):
    def test_limit_types_have_different_recovery(self):
        self.assertEqual(limit_kind('关注操作过于频繁，请稍后再试'),'temporary')
        self.assertEqual(limit_kind('You are unable to follow more people at this time'),'temporary')
        self.assertEqual(limit_kind('You have reached the daily follow limit'),'daily')
        self.assertEqual(limit_kind('关注比例限制，需要更多粉丝'),'ratio')
        self.assertEqual(limit_kind('Your account is locked'),'account')
        self.assertIsNone(limit_kind('正在关注'))

    def test_cooldown_honors_server_and_backs_off(self):
        self.assertEqual([retry_delay('temporary',{},index,1000) for index in range(7)],
                         [300,600,1800,3600,43200,43200,43200])
        self.assertEqual(retry_delay('daily',{},0,1000),86400)
        self.assertEqual(retry_delay('temporary',{'retry-after':'14400'},0,1000),14400)
        self.assertEqual(retry_delay('temporary',{'x-rate-limit-reset':'10000'},0,1000),9000)

    def test_follow_and_cooldown_records_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'history.db'
            store=ActivityStore(path,'owner')
            self.assertTrue(store.reserve_follow('100','friend'))
            self.assertFalse(store.reserve_follow('100','friend'))
            store.mark_follow('100','limited')
            self.assertTrue(store.reserve_follow('100','friend'))
            store.mark_follow('100','confirmed')
            store.set_follow_state(9000,'频率限制',2)
            store.close()
            reopened=ActivityStore(path,'owner')
            self.assertEqual(reopened.follow_status('100'),'confirmed')
            self.assertFalse(reopened.reserve_follow('100','friend'))
            self.assertEqual(reopened.follow_state()['resume_at'],9000)
            self.assertEqual(reopened.follow_state()['failures'],2)
            other=ActivityStore(path,'another')
            self.assertIsNone(other.follow_status('100'))
            other.close();reopened.close()

    def test_no_ui_requests_during_cooldown_or_manual_block(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ActivityStore(Path(directory)/'history.db','owner')
            runner=Mock(store=store,account='owner',config={})
            worker=FollowBackWorker(runner)
            store.set_follow_state(9000,'频率限制',1)
            with patch('follow_back.time.time',return_value=1000):
                self.assertFalse(worker.tick(Mock()))
            runner.new_work_page.assert_not_called()
            store.set_follow_state(0,'比例限制',1,True)
            self.assertFalse(worker.tick(Mock()))
            runner.new_work_page.assert_not_called()
            store.close()

    def test_expired_cooldown_rechecks_once_and_does_not_reload_each_tick(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ActivityStore(Path(directory)/'history.db','owner')
            runner=Mock(store=store,account='owner',config={})
            worker=FollowBackWorker(runner)
            worker.page=Mock(url='https://x.com/owner/verified_followers')
            worker.page.is_closed.return_value=False
            worker.page.locator.return_value.all_text_contents.return_value=[]
            worker.page.locator.return_value.evaluate_all.return_value=[]
            store.set_follow_state(900,'频率限制',1)
            with patch('follow_back.time.time',return_value=1000),patch.object(worker,'load') as load:
                self.assertFalse(worker.tick(Mock()))
                self.assertFalse(worker.tick(Mock()))
            load.assert_called_once()
            self.assertEqual(store.follow_state()['resume_at'],0)
            self.assertEqual(store.follow_state()['failures'],1)
            store.close()

    def test_known_limit_is_retryable_after_cooldown_unknown_is_not(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ActivityStore(Path(directory)/'history.db','owner')
            runner=Mock(store=store,account='owner',config={})
            worker=FollowBackWorker(runner)
            store.reserve_follow('100','friend')
            with patch('follow_back.time.time',return_value=1800000000):
                worker.cooldown('temporary',{'retry-after':'7200'},'100')
            self.assertEqual(store.follow_status('100'),'limited')
            self.assertEqual(store.follow_state()['resume_at'],1800007200)
            self.assertTrue(store.reserve_follow('100','friend'))
            worker.cooldown('unknown',pending_id='100')
            self.assertEqual(store.follow_status('100'),'pending')
            self.assertFalse(store.reserve_follow('100','friend'))
            store.close()

    def test_pending_result_is_reconciled_by_reload_without_another_click(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ActivityStore(Path(directory)/'history.db','owner')
            runner=Mock(store=store,account='owner',config={'follow_back':{'check_interval_seconds':300}})
            worker=FollowBackWorker(runner)
            worker.page=Mock(url='https://x.com/owner/verified_followers')
            worker.page.is_closed.return_value=False
            control=worker.page.locator.return_value
            control.count.return_value=1
            control.first.is_visible.return_value=True
            control.first.inner_text.return_value='正在关注'
            store.reserve_follow('100','friend')
            store.set_follow_state(1800003600,'回关结果待核实',1)
            with patch('follow_back.time.time',return_value=1800000000):
                self.assertFalse(worker.tick(Mock()))
            worker.page.goto.assert_called_once_with('https://x.com/owner/verified_followers',
                wait_until='domcontentloaded',timeout=60000)
            control.click.assert_not_called()
            control.first.click.assert_not_called()
            self.assertEqual(store.follow_status('100'),'confirmed')
            self.assertEqual(store.follow_state()['resume_at'],0)
            self.assertEqual(store.follow_state()['failures'],0)
            store.close()

    def test_random_interval_is_measured_from_click_not_late_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ActivityStore(Path(directory)/'history.db','owner')
            runner=Mock(store=store,account='owner',config={'follow_back':{'interval_seconds':[30,60]}})
            worker=FollowBackWorker(runner)
            worker.page=Mock()
            worker.page.locator.return_value.count.return_value=1
            worker.page.locator.return_value.first.is_visible.return_value=True
            worker.page.locator.return_value.first.inner_text.return_value='正在关注'
            store.reserve_follow('100','friend')
            worker.last_attempt_at=1800000000
            with patch('follow_back.time.time',return_value=1800000015),patch('follow_back.random.uniform',return_value=45) as uniform:
                self.assertTrue(worker.confirm_visible('100','friend'))
            uniform.assert_called_once_with(30,60)
            self.assertEqual(worker.next_check,1800000045)
            store.close()

    def test_follow_schedule_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.json'
            for settings in ({'interval_seconds':[60,30]}, {'interval_seconds':[0,30]},
                             {'cooldown_seconds':[]},{'cooldown_seconds':[600,300]},
                             {'cooldown_seconds':[True,300]}):
                path.write_text(json.dumps({'follow_back':settings}),encoding='utf-8')
                with self.assertRaises(ValueError):
                    load_config(path)
            path.write_text(json.dumps({'follow_back':{'interval_seconds':[30,60],
                'cooldown_seconds':[300,600,1800,3600,43200]}}),encoding='utf-8')
            self.assertEqual(load_config(path)['follow_back']['interval_seconds'],[30,60])
