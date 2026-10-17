import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from web_ui import Bridge, Controller, render_page


class WebBridgeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.saved = {'username': 'fake-user', 'password': 'fake-secret', 'operator': '中国移动'}
        self.core = SimpleNamespace(DATA=root, VAULT=root / 'account.dat', load_account=Mock(return_value=self.saved.copy()),
                                    startup_enabled=Mock(return_value=True), save_account=Mock(), set_startup=Mock(),
                                    log_file=Mock(), run_login=Mock(return_value=True), online=Mock(return_value=False),
                                    campus_online=Mock(return_value=False))
        self.controller = Controller(self.core)
        self.bridge = Bridge(self.controller)

    def payload(self, **overrides):
        return dict(username='fake-user', password='', operator='中国移动', autostart=True,
                    show_browser=False, motion=True, **overrides)

    def wait_idle(self):
        deadline = time.monotonic() + 3
        while self.bridge.get_state()['busy'] and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(self.bridge.get_state()['busy'])

    def test_saved_password_never_returned_to_page(self):
        state = self.bridge.get_state()
        self.assertTrue(state['account']['has_password'])
        self.assertNotIn('password', state['account'])
        self.assertNotIn('fake-secret', json.dumps(state))

    def test_blank_password_preserves_same_account_secret(self):
        self.assertTrue(self.bridge.save_settings(self.payload())['ok'])
        self.core.save_account.assert_called_once_with(self.saved)

    def test_new_username_requires_new_password(self):
        payload = self.payload()
        payload['username'] = 'different-user'
        self.assertFalse(self.bridge.save_settings(payload)['ok'])
        self.core.save_account.assert_not_called()

    def test_password_whitespace_is_preserved(self):
        payload = self.payload()
        payload['password'] = '  fake new password  '
        self.assertTrue(self.bridge.save_settings(payload)['ok'])
        self.assertEqual(self.core.save_account.call_args.args[0]['password'], payload['password'])

    def test_invalid_payload_cannot_mutate_native_settings(self):
        for bad in (None, [], {}, {'username': 42}, dict(self.payload(), operator='untrusted'), dict(self.payload(), autostart='yes')):
            self.assertFalse(self.bridge.save_settings(bad)['ok'])
        self.core.save_account.assert_not_called()
        self.core.set_startup.assert_not_called()

    def test_save_updates_startup_and_existing_motion_file(self):
        self.assertTrue(self.bridge.save_settings(self.payload())['ok'])
        self.core.set_startup.assert_called_once_with(True)
        self.assertEqual(json.loads((self.core.DATA / 'ui-preferences.json').read_text())['animations'], True)

    def test_browser_preference_survives_restart_and_motion_changes(self):
        payload = self.payload()
        payload['show_browser'] = True
        self.assertTrue(self.bridge.save_settings(payload)['ok'])
        self.assertTrue(self.bridge.set_motion(False)['ok'])
        fresh = Bridge(Controller(self.core))
        self.assertTrue(fresh.get_state()['preferences']['show_browser'])
        self.assertFalse(fresh.get_state()['preferences']['motion'])

    def test_uninitialized_navigation_guard_disables_all_native_methods(self):
        guarded = Bridge(self.controller, lambda: False)
        for method, args in ((guarded.get_state, ()), (guarded.connect, (self.payload(),)),
                             (guarded.save_settings, (self.payload(),)), (guarded.clear_settings, ()),
                             (guarded.set_motion, (True,)), (guarded.check_status, ())):
            with self.assertRaises(RuntimeError):
                method(*args)
        self.core.run_login.assert_not_called()
        self.core.save_account.assert_not_called()

    def test_probe_does_not_save_or_submit(self):
        self.core.campus_online.return_value = True
        self.assertTrue(self.bridge.check_status()['ok'])
        self.wait_idle()
        self.assertEqual(self.bridge.get_state()['status']['kind'], 'campus')
        self.core.run_login.assert_not_called()
        self.core.save_account.assert_not_called()

    def test_successful_connection_hides_password_in_every_response(self):
        self.assertTrue(self.bridge.connect(self.payload())['ok'])
        self.wait_idle()
        self.assertEqual(self.bridge.get_state()['status']['kind'], 'online')
        self.assertNotIn('fake-secret', json.dumps(self.bridge.get_state()))
        self.core.run_login.assert_called_once()

    def test_campus_only_connection_does_not_claim_internet(self):
        def login(account, log, visible):
            log('登录成功：校园认证显示已在线；外网探测暂未通过。')
            return True
        self.core.run_login.side_effect = login
        self.bridge.connect(self.payload())
        self.wait_idle()
        self.assertEqual(self.bridge.get_state()['status']['kind'], 'campus')

    def test_failed_connection_restores_busy_and_reports_error(self):
        self.core.run_login.side_effect = RuntimeError('synthetic failure')
        self.bridge.connect(self.payload())
        self.wait_idle()
        self.assertEqual(self.bridge.get_state()['status']['kind'], 'error')

    def test_busy_blocks_duplicate_actions_and_defers_close(self):
        entered, finish = threading.Event(), threading.Event()
        self.addCleanup(finish.set)
        def login(*args, **kwargs):
            entered.set()
            finish.wait(2)
            return True
        self.core.run_login.side_effect = login
        on_idle = Mock()
        self.controller._on_idle = on_idle
        self.assertTrue(self.bridge.connect(self.payload())['ok'])
        self.assertTrue(entered.wait(1))
        self.assertFalse(self.bridge.connect(self.payload())['ok'])
        self.assertFalse(self.bridge.clear_settings()['ok'])
        self.assertFalse(self.bridge.save_settings(self.payload())['ok'])
        self.assertFalse(self.controller._request_close())
        finish.set()
        self.wait_idle()
        self.assertTrue(on_idle.called)
        self.core.run_login.assert_called_once()

    def test_clear_removes_secret_and_disables_startup(self):
        self.core.VAULT.write_bytes(b'fake encrypted data')
        self.assertTrue(self.bridge.clear_settings()['ok'])
        self.assertFalse(self.core.VAULT.exists())
        self.core.set_startup.assert_called_once_with(False)
        self.assertFalse(self.bridge.get_state()['account']['has_password'])

    def test_motion_can_change_without_saving_account(self):
        self.assertTrue(self.bridge.set_motion(False)['ok'])
        self.assertFalse(self.bridge.get_state()['preferences']['motion'])
        self.core.save_account.assert_not_called()
        self.assertFalse(self.bridge.set_motion('false')['ok'])

    def test_logs_are_bounded_incremental_and_copied(self):
        for index in range(550):
            self.controller._log('synthetic log ' + str(index))
        state = self.bridge.get_state()
        self.assertEqual(len(state['logs']), 500)
        self.assertEqual(len(self.bridge.get_state(548)['logs']), 2)
        state['logs'][0]['message'] = 'modified in client'
        self.assertNotEqual(self.bridge.get_state()['logs'][0]['message'], 'modified in client')

    def test_disk_error_does_not_crash_bridge(self):
        self.core.save_account.side_effect = OSError('synthetic disk failure')
        self.assertFalse(self.bridge.save_settings(self.payload())['ok'])
        self.assertFalse(self.bridge.get_state()['busy'])

    def test_check_mode_can_avoid_all_saved_account_reads(self):
        self.core.load_account.reset_mock()
        fresh = Controller(self.core, load_saved=False)
        self.core.load_account.assert_not_called()
        self.assertFalse(Bridge(fresh).get_state()['account']['has_password'])

    def test_page_resources_are_local_and_bridge_surface_is_limited(self):
        page = render_page()
        self.assertNotIn('__APP_', page)
        self.assertNotIn('<script src=', page)
        self.assertNotIn('fonts.googleapis', page)
        exposed = [name for name in dir(self.bridge) if not name.startswith('_') and callable(getattr(self.bridge, name))]
        self.assertEqual(sorted(exposed), ['check_status', 'clear_settings', 'connect', 'get_state', 'save_settings', 'set_motion'])


if __name__ == '__main__':
    unittest.main()
