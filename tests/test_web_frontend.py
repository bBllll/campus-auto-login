import json
from pathlib import Path
import tempfile
import time
import unittest

import campus_auto_login as core
from web_ui import render_page


STUB = r'''
window.__calls = [];
window.__state = {version:'2.0.0',busy:false,closing:false,
  account:{username:'demo_student',operator:'中国移动',has_password:true},
  preferences:{autostart:true,show_browser:false,motion:true},
  status:{kind:'idle',title:'等待连接',detail:'账号已保存，可以直接连接。',checked_at:null},
  notice:null,logs:[],last_log_id:0};
const response = () => ({ok:true,state:structuredClone(window.__state)});
window.pywebview = {api:{
  get_state: async()=>structuredClone(window.__state),
  save_settings: async(data)=>{window.__calls.push({method:'save',data});return response()},
  connect: async(data)=>{window.__calls.push({method:'connect',data});window.__state.busy=true;window.__state.status.kind='busy';return response()},
  clear_settings:async()=>{window.__calls.push({method:'clear'});window.__state.account={username:'',operator:'',has_password:false};return response()},
  check_status:async()=>response(),
  set_motion:async(enabled)=>{window.__state.preferences.motion=enabled;return response()}
}};
'''


class WebFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name) / 'ui.html'
        cls.browser = core.Browser().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.temp.cleanup()

    def setUp(self):
        page = render_page().replace('<script>', '<script>' + STUB + '</script><script>', 1)
        self.path.write_text(page, encoding='utf-8')
        self.browser.call('Page.navigate', {'url': self.path.as_uri()})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.js('Boolean(window.campusApp && window.campusApp.ready)'):
                break
            time.sleep(.03)
        else:
            self.fail('Web frontend did not initialize')

    def js(self, expression):
        return self.browser.evaluate(expression)

    def test_boot_and_narrow_window_have_no_horizontal_overflow(self):
        self.assertTrue(self.js('window.campusApp.inspect().ui_loaded'))
        self.browser.call('Emulation.setDeviceMetricsOverride', {'width': 880, 'height': 690, 'deviceScaleFactor': 1, 'mobile': False})
        self.assertFalse(self.js('window.campusApp.inspect().horizontal_overflow'))
        self.browser.call('Emulation.clearDeviceMetricsOverride')

    def test_saved_password_stays_empty_and_save_uses_blank_sentinel(self):
        self.assertEqual(self.js('document.getElementById("password").value'), '')
        self.assertTrue(self.js('!document.getElementById("password-saved").hidden'))
        self.js('document.getElementById("save-button").click()')
        self.assertEqual(self.js('window.__calls[0].data.password'), '')

    def test_changed_account_without_password_is_rejected_before_bridge(self):
        self.js('document.getElementById("username").value="another";document.getElementById("save-button").click()')
        self.assertEqual(self.js('window.__calls.length'), 0)
        self.assertFalse(self.js('document.getElementById("form-error").hidden'))

    def test_password_reveal_is_reset_when_window_blurs(self):
        self.js('document.getElementById("password").value="fake";document.getElementById("reveal-password").click()')
        self.assertEqual(self.js('document.getElementById("password").type'), 'text')
        self.js('window.dispatchEvent(new Event("blur"))')
        self.assertEqual(self.js('document.getElementById("password").type'), 'password')

    def test_tabs_motion_override_and_busy_controls(self):
        self.js('document.querySelector("[data-view=preferences]").click()')
        self.assertFalse(self.js('document.getElementById("view-preferences").hidden'))
        self.js('document.getElementById("motion").click()')
        self.assertEqual(self.js('document.body.dataset.motion'), 'off')
        self.assertEqual(self.js('getComputedStyle(document.querySelector(".button")).transitionDuration'), '0s')
        self.js('document.querySelector("[data-view=connection]").click();document.getElementById("connect-button").click()')
        self.assertTrue(self.js('document.getElementById("connect-button").disabled'))
        self.assertFalse(self.js('document.getElementById("motion").disabled'))

    def test_log_text_is_not_interpreted_as_html(self):
        self.js('window.__state.logs=[{id:1,time:"12:00:00",level:"info",message:"<img src=x onerror=alert(1)>"}]')
        time.sleep(.8)
        self.assertEqual(self.js('document.querySelectorAll("#log-list img").length'), 0)
        self.assertIn('<img src=x', self.js('document.getElementById("log-list").textContent'))


if __name__ == '__main__':
    unittest.main()
