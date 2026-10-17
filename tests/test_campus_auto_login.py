import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import campus_auto_login as app


class HelperTests(unittest.TestCase):
    def setUp(self):
        host_patcher = patch.object(app, 'HOST', 'portal.example.invalid')
        host_patcher.start()
        self.addCleanup(host_patcher.stop)
        patcher = patch.object(app, 'campus_online', return_value=False)
        self.campus = patcher.start()
        self.addCleanup(patcher.stop)

    def test_campus_authenticated_does_not_submit(self):
        self.campus.return_value = True
        with patch.object(app, 'Browser') as browser:
            self.assertTrue(app.run_login({}, lambda s:None, internet_check=lambda:False))
            browser.assert_not_called()

    def test_dpapi_roundtrip(self):
        raw = 'fake-password-测试-<&"\\'.encode()
        encrypted = app.protect(raw)
        self.assertNotIn(raw, encrypted)
        self.assertEqual(app.protect(encrypted, decrypt=True), raw)

    def test_saved_account_is_encrypted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(app, 'DATA', root), patch.object(app, 'VAULT', root / 'account.dat'):
                account = {'username':'fake-account','password':'fake-passphrase','operator':'中国移动'}
                app.save_account(account)
                self.assertNotIn(b'fake-passphrase', app.VAULT.read_bytes())
                self.assertEqual(account, app.load_account())

    def test_disconnected_does_not_submit(self):
        with patch.object(app, 'portal_reachable', return_value=False), patch.object(app, 'Browser') as browser:
            with self.assertRaisesRegex(RuntimeError, '无法访问'):
                app.run_login({}, lambda s:None, internet_check=lambda:False)
            browser.assert_not_called()

    def test_already_online_does_not_submit(self):
        with patch.object(app, 'Browser') as browser:
            self.assertTrue(app.run_login({}, lambda s:None, internet_check=lambda:True))
            browser.assert_not_called()

    def test_failed_login_submits_only_once(self):
        with patch.object(app, 'Browser') as browser_class, patch.object(app, 'portal_reachable', return_value=True), patch.object(app.time, 'sleep'):
            browser = browser_class.return_value.__enter__.return_value
            browser.evaluate.side_effect = [{'status':'ready'}, {'status':'carrier-ready'}, {'status':'submitted'}]
            with self.assertRaisesRegex(RuntimeError, '已提交一次'):
                app.run_login({'username':'fake','password':'fake','operator':''},lambda s:None,internet_check=lambda:False)
            actions = [call.args[0] for call in browser.evaluate.call_args_list]
            self.assertEqual(sum('"action": "submit"' in js for js in actions), 1)

    def test_gui_constructs_with_configuration_controls(self):
        from web_ui import render_page
        page = render_page()
        self.assertIn('保存并连接', page)
        self.assertIn('中国移动', page)
        self.assertIn('id="password" name="password" type="password"', page)
        self.assertNotIn('__APP_SCRIPT__', page)

    def test_password_visibility_and_saving_preferences(self):
        from web_ui import Controller, Bridge
        with tempfile.TemporaryDirectory() as temporary, patch.object(app, 'DATA', Path(temporary)), patch.object(app, 'save_account') as save, patch.object(app, 'set_startup') as startup, patch.object(app, 'log_file'):
            bridge = Bridge(Controller(app, load_saved=False))
            result = bridge.save_settings({'username': 'fake-ui-user', 'password': 'fake-ui-password', 'operator': '中国联通',
                                           'autostart': False, 'show_browser': False, 'motion': True})
            self.assertTrue(result['ok'])
            save.assert_called_once_with({'username':'fake-ui-user','password':'fake-ui-password','operator':'中国联通'})
            startup.assert_called_once_with(False)
            self.assertNotIn('fake-ui-password', json.dumps(bridge.get_state()))


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name) / 'portal.html'
        cls.browser = app.Browser().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.temp.cleanup()

    def load(self, body):
        self.path.write_text('<!DOCTYPE html><meta charset="UTF-8">'+body,encoding='utf-8')
        self.browser.call('Page.navigate', {'url':self.path.as_uri()})
        import time
        for _ in range(100):
            if self.browser.evaluate('document.readyState') == 'complete':
                break
            time.sleep(.05)
        self.browser.evaluate('window.result = null')

    def js(self, action, account=None):
        return self.browser.evaluate(app.dom_script(action, account, allowed_host=''))

    def test_select_carrier_and_special_password(self):
        self.load('''<input name="DDDDD"><input name="upass" type="password">
        <select id="carrier"><option value="t">中国电信</option><option value="u">中国联通</option></select>
        <input type="button" value="登录" onclick="window.result={username:document.querySelector('[name=DDDDD]').value,password:document.querySelector('[name=upass]').value,carrier:document.querySelector('select').value}">''')
        a = {'username':'fake <& account','password':"fake ' \\ \" </script> 口令",'operator':'联通'}
        self.assertEqual(self.js('inspect')['status'],'ready')
        self.assertEqual(self.js('carrier',a)['status'],'carrier-ready')
        self.assertEqual(self.js('submit',a)['status'],'submitted')
        actual = self.browser.evaluate('window.result')
        self.assertEqual(actual,dict(username=a['username'],password=a['password'],carrier='u'))

    def test_captcha_stops(self):
        self.load('<input name="username"><input type="password"><input placeholder="验证码"><button onclick="result=true">登录</button>')
        self.assertEqual(self.js('submit',{'username':'fake','password':'fake'})['status'],'captcha')
        self.assertIsNone(self.browser.evaluate('window.result'))
        self.assertEqual(self.browser.evaluate('document.querySelector("input[type=password]").value'),'')

    def test_wrong_origin_stops(self):
        self.load('<input name="username"><input type="password"><button>登录</button>')
        result = self.browser.evaluate(app.dom_script('submit',{'username':'fake','password':'fake'}, allowed_host='portal.example.invalid'))
        self.assertEqual(result['status'],'wrong-origin')
        self.assertEqual(self.browser.evaluate('document.querySelector("input[type=password]").value'),'')

    def test_missing_carrier_stops(self):
        self.load('<input name="username"><input type="password"><select><option>中国电信</option></select><button>登录</button>')
        self.assertEqual(self.js('carrier',{'operator':'中国移动'})['status'],'carrier-missing')

    def test_radio_carrier(self):
        self.load('<input name="username"><input type="password"><label><input type="radio" name="carrier" value="u">中国联通</label><button>登录</button>')
        self.assertEqual(self.js('carrier',{'operator':'联通'})['status'],'carrier-ready')
        self.assertTrue(self.browser.evaluate('document.querySelector("input[type=radio]").checked'))

    def test_custom_dropdown(self):
        self.load('''<input name="username"><input type="password"><button onclick="document.querySelector('ul').style.display='block'">中国电信</button>
        <ul style="display:none"><li onclick="window.result='cmcc'">中国移动</li></ul><button>登录</button>''')
        self.assertEqual(self.js('carrier',{'operator':'中国移动'})['status'],'carrier-opened')
        self.assertEqual(self.js('carrier',{'operator':'中国移动','opened':True})['status'],'carrier-ready')
        self.assertEqual(self.browser.evaluate('window.result'),'cmcc')

    def test_observed_drcom_form_structure(self):
        # Synthetic fixture based on observed field names; no campus account data or assets.
        self.load('''<div style="display:none"><form name="f0"><input type="hidden" name="DDDDD"><input type="hidden" name="upass"></form></div>
        <form name="f3" onsubmit="window.result={user:this.DDDDD.value,password:this.upass.value,isp:document.querySelector('[name=ISP_select]').value};return false">
        <input type="submit" name="0MKKey" value="登录"><input name="DDDDD" placeholder="账号"><input name="upass" type="password">
        <input name="captcha" placeholder="随机验证码" style="display:none"></form>
        <select name="ISP_select"><option value="-1">请选择运营商</option><option value="1">中国移动</option><option value="2">中国电信</option><option value="3">中国联通</option><option value="0">教师专用</option></select>''')
        account = {'username':'fake-campus-user','password':'fake-campus-pass','operator':'中国移动'}
        self.assertEqual(self.js('carrier',account)['status'],'carrier-ready')
        self.assertEqual(self.js('submit',account)['status'],'submitted')
        self.assertEqual(self.browser.evaluate('window.result'),{'user':account['username'],'password':account['password'],'isp':'1'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
