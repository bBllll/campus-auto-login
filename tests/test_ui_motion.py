import unittest
from unittest.mock import patch

import campus_auto_login as api
from ui_fx import Motion


class ClockRoot:
    def __init__(self):
        self.time = 0
        self.counter = 0
        self.queue = {}

    def after(self, delay, callback):
        self.counter += 1
        self.queue[self.counter] = (self.time + delay / 1000, callback)
        return self.counter

    def after_cancel(self, job):
        self.queue.pop(job, None)

    def advance(self, milliseconds):
        end = self.time + milliseconds / 1000
        while self.queue:
            job, (at, callback) = min(self.queue.items(), key=lambda item: item[1][0])
            if at > end:
                break
            self.time = at
            self.queue.pop(job)
            callback()
        self.time = end


class MotionTests(unittest.TestCase):
    def test_retarget_does_not_finish_replaced_animation(self):
        root = ClockRoot()
        motion = Motion(root, reduced=False, clock=lambda: root.time)
        frames, completions = [], []
        motion.animate('switch', frames.append, 160, lambda: completions.append('old'))
        root.advance(50)
        self.assertTrue(0 < frames[-1] < 1)
        motion.animate('switch', frames.append, 160, lambda: completions.append('new'))
        self.assertEqual(len(root.queue), 1)
        root.advance(200)
        self.assertEqual(completions, ['new'])
        self.assertEqual(frames[-1], 1)
        self.assertFalse(root.queue)

    def test_reduced_motion_is_immediate_but_notification_timeout_is_not(self):
        root = ClockRoot()
        motion = Motion(root, reduced=True, clock=lambda: root.time)
        frames, calls = [], []
        motion.animate('badge', frames.append)
        self.assertEqual(frames, [1])
        self.assertFalse(root.queue)
        motion.later('notice', 6000, lambda: calls.append('dismiss'))
        root.advance(5999)
        self.assertEqual(calls, [])
        root.advance(2)
        self.assertEqual(calls, ['dismiss'])

    def test_shutdown_cancels_all_callbacks(self):
        root = ClockRoot()
        motion = Motion(root, reduced=False, clock=lambda: root.time)
        frames = []
        motion.animate('hover', frames.append)
        motion.later('password', 1000, lambda: frames.append('late'))
        motion.shutdown()
        root.advance(3000)
        self.assertEqual(frames, [0])
        self.assertFalse(root.queue)

    def test_disabling_motion_settles_active_animation_and_preserves_timers(self):
        root = ClockRoot()
        motion = Motion(root, reduced=False, clock=lambda: root.time)
        frames, calls = [], []
        motion.animate('hover', frames.append)
        motion.later('notice', 6000, lambda: calls.append('dismiss'))
        root.advance(40)
        motion.set_reduced(True)
        self.assertEqual(frames[-1], 1)
        self.assertEqual(len(root.queue), 1)
        root.advance(6000)
        self.assertEqual(calls, ['dismiss'])


class InteractionTests(unittest.TestCase):
    def make_window(self):
        from desktop_ui import CampusWindow
        window = CampusWindow(api, load_saved=False)
        self.addCleanup(window.destroy)
        return window

    def test_fast_switch_toggles_settle_and_disabled_switch_ignores_input(self):
        window = self.make_window()
        for _ in range(15):
            window.autostart_switch.toggle()
        window.after(220, window.quit)
        window.mainloop()
        self.assertFalse(window.autostart.get())
        self.assertAlmostEqual(window.autostart_switch.position, 0)
        window.autostart_switch.set_enabled(False)
        window.autostart_switch.toggle()
        self.assertFalse(window.autostart.get())

    def test_app_motion_switch_can_override_system_preference(self):
        window = self.make_window()
        window.animations.set(True)
        self.assertFalse(window.motion.reduced)
        window.set_busy(True)
        self.assertTrue(window.progress._loop_running)
        window.animations.set(False)
        self.assertTrue(window.motion.reduced)
        self.assertFalse(window.progress._loop_running)
        window.set_busy(False)

    def test_busy_blocks_duplicate_login_and_close_waits_for_task_cleanup(self):
        window = self.make_window()
        with patch.object(api, 'run_login') as login:
            window.set_busy(True)
            window.test()
            login.assert_not_called()
            self.assertEqual(window.account_entry.cget('state'), 'disabled')
            window.close()
            self.assertTrue(window.closing_after_task)
            self.assertTrue(window.winfo_exists())
            window.closing_after_task = False
            window.set_busy(False)
            self.assertEqual(window.account_entry.cget('state'), 'normal')
            self.assertFalse(window.progress._loop_running)

    def test_default_operator_and_validation_do_not_save_blank_credentials(self):
        window = self.make_window()
        with patch.object(api, 'save_account') as save:
            self.assertIsNone(window.save())
            save.assert_not_called()
            self.assertIn('username', window.invalid_fields)
        window.username.set('fake-user')
        window.password.set('fake-password')
        from desktop_ui import DEFAULT_OPERATOR
        window.operator.set(DEFAULT_OPERATOR)
        self.assertEqual(window.read_fields()['operator'], '')

    def test_failure_hides_password_and_campus_only_status_is_precise(self):
        window = self.make_window()
        window.password.set('fake-secret')
        window.toggle_password()
        window.present_result(False, '账号或运营商需要核对')
        self.assertEqual(window.password_entry.cget('show'), '●')
        window.present_result(True, '校园认证显示已登录；外网探测未通过，跳过重复认证。')
        self.assertEqual(window.state_badge.cget('text'), '校园网已认证')
        self.assertIn('尚未通过', window.state_hint.cget('text'))

    def test_logs_are_bounded_and_do_not_steal_scroll_position(self):
        window = self.make_window()
        window.after(50, window.quit)
        window.mainloop()
        for i in range(550):
            window.append_log(f'fake log {i}')
        window.update_idletasks()
        self.assertLessEqual(int(window.status.index('end-1c').split('.')[0]), 501)
        window.status.yview_moveto(0)
        window.update_idletasks()
        window.append_log('new log while reading history')
        window.update_idletasks()
        self.assertLess(window.status.yview()[1], .5)
        self.assertTrue(window.new_logs.winfo_manager())


if __name__ == '__main__':
    unittest.main(verbosity=2)
