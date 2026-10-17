import unittest
from unittest.mock import patch

import campus_auto_login as app


class StartupWatchTests(unittest.TestCase):
    def setUp(self):
        host_patcher = patch.object(app, 'HOST', 'portal.example.invalid')
        host_patcher.start()
        self.addCleanup(host_patcher.stop)
        self.now = 0
        self.logs = []
        for target, replacement in (
            ('monotonic', lambda: self.now),
            ('sleep', self.advance),
        ):
            patcher = patch.object(app.time, target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.campus = patch.object(app, 'campus_online', return_value=False).start()
        self.portal = patch.object(app, 'portal_reachable', return_value=True).start()
        self.addCleanup(patch.stopall)

    def advance(self, seconds):
        self.now += seconds

    def test_online_at_boot_then_auth_required_submits_once(self):
        def internet():
            return self.now < 45 or self.now >= 60

        with patch.object(app, 'Browser') as browser_class:
            browser = browser_class.return_value.__enter__.return_value
            browser.evaluate.side_effect = [
                {'status': 'ready'}, {'status': 'carrier-ready'}, {'status': 'submitted'},
            ]
            result = app.run_login(
                {'username': 'fake', 'password': 'fake', 'operator': ''},
                self.logs.append, auto=True, internet_check=internet,
            )
            self.assertTrue(result)
            actions = [call.args[0] for call in browser.evaluate.call_args_list]
            self.assertEqual(sum('"action": "submit"' in script for script in actions), 1)
            self.assertGreaterEqual(self.now, 60)

    def test_continuously_online_watches_full_window_without_browser(self):
        with patch.object(app, 'Browser') as browser:
            self.assertTrue(app.run_login({}, self.logs.append, auto=True, internet_check=lambda: True))
            browser.assert_not_called()
        self.assertEqual(self.now, 600)
        self.assertEqual(len(self.logs), 3)
        self.portal.assert_not_called()
        self.campus.assert_not_called()

    def test_campus_authentication_avoids_duplicate_submission(self):
        self.campus.return_value = True
        with patch.object(app, 'Browser') as browser:
            self.assertTrue(app.run_login({}, self.logs.append, auto=True, internet_check=lambda: False))
            browser.assert_not_called()
        self.assertEqual(self.now, 600)
        self.portal.assert_not_called()

    def test_unavailable_network_times_out_without_browser(self):
        self.portal.return_value = False
        with patch.object(app, 'Browser') as browser:
            self.assertFalse(app.run_login({}, self.logs.append, auto=True, internet_check=lambda: False))
            browser.assert_not_called()
        self.assertEqual(self.now, 600)

    def test_network_becomes_ready_after_wait(self):
        self.portal.side_effect = lambda: self.now >= 30
        self.assertIsNone(app.watch_startup_network(self.logs.append, lambda: False))
        self.assertEqual(self.now, 30)

    def test_campus_authentication_expires_during_watch(self):
        self.campus.side_effect = lambda: self.now < 45
        self.assertIsNone(app.watch_startup_network(self.logs.append, lambda: False))
        self.assertEqual(self.now, 45)

    def test_bad_password_still_submits_only_once(self):
        with patch.object(app, 'Browser') as browser_class:
            browser = browser_class.return_value.__enter__.return_value
            browser.evaluate.side_effect = [
                {'status': 'ready'}, {'status': 'carrier-ready'}, {'status': 'submitted'},
            ]
            with self.assertRaisesRegex(RuntimeError, '已提交一次'):
                app.run_login({}, self.logs.append, auto=True, internet_check=lambda: False)
            self.assertEqual(len(browser.evaluate.call_args_list), 3)

    def test_watch_uses_remaining_time_and_rejects_invalid_intervals(self):
        self.assertTrue(app.watch_startup_network(self.logs.append, lambda: True, timeout=20, interval=15))
        self.assertEqual(self.now, 20)
        with self.assertRaises(ValueError):
            app.watch_startup_network(self.logs.append, lambda: True, interval=0)
        with self.assertRaises(ValueError):
            app.watch_startup_network(self.logs.append, lambda: True, timeout=0)

    def test_last_probe_detects_auth_expiry_at_deadline(self):
        result = app.watch_startup_network(
            self.logs.append, lambda: self.now < 20, timeout=20, interval=15,
        )
        self.assertIsNone(result)
        self.assertEqual(self.now, 20)

    def test_internet_recovers_during_portal_probe(self):
        recovered = False

        def portal():
            nonlocal recovered
            recovered = True
            return True

        self.portal.side_effect = portal
        self.assertTrue(app.watch_startup_network(
            self.logs.append, lambda: recovered, timeout=20,
        ))
        self.assertNotIn('检测到需要校园网认证，开始一次登录。', self.logs)

    def test_submission_is_skipped_if_network_recovers_in_browser(self):
        with patch.object(app, 'Browser') as browser_class:
            browser = browser_class.return_value.__enter__.return_value
            browser.evaluate.side_effect = [{'status': 'ready'}, {'status': 'carrier-ready'}]
            self.assertTrue(app.run_login({}, self.logs.append, internet_check=lambda: self.now >= .5))
            self.assertEqual(len(browser.evaluate.call_args_list), 2)

    def test_manual_login_obeys_shared_submission_lock(self):
        handle = app.exclusive_run(scope='login')
        self.assertIsNotNone(handle)
        try:
            with patch.object(app, 'Browser') as browser:
                with self.assertRaisesRegex(RuntimeError, '已有连接任务'):
                    app.run_login({}, self.logs.append, internet_check=lambda: False)
                browser.assert_not_called()
        finally:
            app.release_run(handle)

    def test_failed_login_releases_submission_lock(self):
        with patch.object(app, 'Browser') as browser_class:
            browser_class.return_value.__enter__.side_effect = RuntimeError('synthetic browser failure')
            with self.assertRaisesRegex(RuntimeError, 'synthetic browser failure'):
                app.run_login({}, self.logs.append, internet_check=lambda: False)
        handle = app.exclusive_run(scope='login')
        self.assertIsNotNone(handle)
        app.release_run(handle)

    def test_campus_only_final_log_does_not_claim_internet(self):
        self.campus.return_value = True
        self.assertTrue(app.watch_startup_network(self.logs.append, lambda: False, timeout=1))
        self.assertIn('外网探测暂未通过', self.logs[-1])


if __name__ == '__main__':
    unittest.main()
