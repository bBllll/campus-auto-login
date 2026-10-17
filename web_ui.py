"""Local HTML interface and a narrow native bridge; saved passwords stay in Python."""
import base64
from collections import deque
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import threading
import time

VERSION = '2.0.1'
ROOT = Path(__file__).resolve().parent
OPERATORS = ('', '中国移动', '中国电信', '中国联通', '教师专用')


def system_motion_enabled():
    enabled = wintypes.BOOL(True)
    try:
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
            return bool(enabled.value)
    except OSError:
        pass
    return True


def render_page():
    page = (ROOT / 'webui' / 'index.html').read_text(encoding='utf-8')
    styles = '\n'.join((ROOT / 'webui' / name).read_text(encoding='utf-8') for name in ('style.css', 'motion.css'))
    script = (ROOT / 'webui' / 'app.js').read_text(encoding='utf-8')
    icon = base64.b64encode((ROOT / 'assets' / 'app-icon.png').read_bytes()).decode('ascii')
    return page.replace('__APP_STYLES__', styles).replace('__APP_SCRIPT__', script).replace(
        '__CAMPUS_APP_ICON__', 'data:image/png;base64,' + icon,
    )


class Controller:
    """Native state, disk access and workers. Never expose this object to JavaScript."""
    def __init__(self, core, load_saved=True):
        self._core = core
        self._lock = threading.RLock()
        self._account = None
        self._logs = deque(maxlen=500)
        self._serial = 0
        self._busy = False
        self._closing = False
        self._on_idle = None
        self._notice = None
        self._notice_id = 0
        self._status = {'kind': 'idle', 'title': '等待连接', 'detail': '填写账号后，即可连接校园网络。', 'checked_at': None}
        self._preferences = {'autostart': False, 'show_browser': False, 'motion': system_motion_enabled()}
        if load_saved:
            self._preferences['autostart'] = core.startup_enabled()
            try:
                account = core.load_account()
                if isinstance(account, dict) and all(isinstance(account.get(key), str) for key in ('username', 'password', 'operator')):
                    self._account = account
            except Exception:
                self._tell('已保存的账号暂时无法读取，请重新填写。', 'error')
            try:
                prefs = json.loads((core.DATA / 'ui-preferences.json').read_text(encoding='utf-8'))
                if isinstance(prefs.get('animations'), bool):
                    self._preferences['motion'] = prefs['animations']
                if isinstance(prefs.get('show_browser'), bool):
                    self._preferences['show_browser'] = prefs['show_browser']
            except (OSError, ValueError, AttributeError):
                pass
        if self._account:
            self._status['detail'] = '账号已保存，可以直接连接；留空密码将保留原密码。'

    def _tell(self, message, kind='info'):
        self._notice_id += 1
        self._notice = {'id': self._notice_id, 'message': message, 'kind': kind}

    def _log(self, message):
        with self._lock:
            self._serial += 1
            level = 'warning' if '未通过' in message else 'error' if any(word in message for word in ('失败', '无法', '未完成')) else 'info'
            self._logs.append({'id': self._serial, 'time': time.strftime('%H:%M:%S'), 'message': message, 'level': level})
            try:
                self._core.log_file(message)
            except OSError:
                pass

    def _snapshot(self, after=0):
        with self._lock:
            return {
                'version': VERSION, 'busy': self._busy, 'closing': self._closing,
                'status': dict(self._status), 'notice': dict(self._notice) if self._notice else None,
                'preferences': dict(self._preferences),
                'account': {'username': self._account['username'] if self._account else '',
                            'operator': self._account['operator'] if self._account else '',
                            'has_password': bool(self._account and self._account['password'])},
                'logs': [dict(item) for item in self._logs if item['id'] > after],
                'last_log_id': self._serial,
            }

    def _validate(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('请检查输入内容。')
        username, password, operator = (payload.get(key, '') for key in ('username', 'password', 'operator'))
        if not all(isinstance(value, str) for value in (username, password, operator)):
            raise ValueError('请检查账号和密码。')
        username = username.strip()
        if not username or len(username) > 256:
            raise ValueError('请填写校园网账号。')
        if not password and self._account and username == self._account['username']:
            password = self._account['password']
        if not password or len(password) > 1024:
            raise ValueError('请填写账号对应的密码。')
        if operator not in OPERATORS:
            raise ValueError('请选择列表中的运营商。')
        for key in ('autostart', 'show_browser', 'motion'):
            if not isinstance(payload.get(key), bool):
                raise ValueError('请检查连接偏好。')
        return {'username': username, 'password': password, 'operator': operator}

    def _persist(self, payload, account):
        self._core.save_account(account)
        self._account = account
        self._core.set_startup(payload['autostart'])
        self._preferences = {key: payload[key] for key in ('autostart', 'show_browser', 'motion')}
        self._write_motion(payload['motion'])

    def _write_motion(self, enabled):
        self._core.DATA.mkdir(parents=True, exist_ok=True)
        path = self._core.DATA / 'ui-preferences.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'animations': enabled, 'show_browser': self._preferences['show_browser']}), encoding='utf-8')
        os.replace(temporary, path)

    def _response(self, ok, message='', after=0):
        return {'ok': ok, 'message': message, 'state': self._snapshot(after)}

    def _save(self, payload, connect=False):
        with self._lock:
            if self._busy:
                return self._response(False, '连接任务正在进行，请稍候。')
            try:
                account = self._validate(payload)
                self._persist(payload, account)
            except ValueError as error:
                self._tell(str(error), 'error')
                return self._response(False, str(error))
            except Exception:
                message = '设置未能全部保存，请检查文件权限后重试。'
                self._tell(message, 'error')
                return self._response(False, message)
            self._log('设置已保存。' + ('开机自动连接已开启。' if payload['autostart'] else '开机自动连接已关闭。'))
            if not connect:
                self._tell('设置已保存。', 'success')
                return self._response(True)
            self._busy = True
            self._status = {'kind': 'busy', 'title': '正在连接', 'detail': '正在检查校园认证与网络状态…', 'checked_at': None}
            return self._launch_worker(lambda: self._login(account, payload['show_browser']))

    def _launch_worker(self, target):
        try:
            threading.Thread(target=target, daemon=False, name='campus-web-task').start()
        except Exception:
            self._busy = False
            self._tell('连接任务未能启动，请重试。', 'error')
            return self._response(False, '连接任务未能启动，请重试。')
        return self._response(True)

    def _set_result(self, kind, title, detail):
        with self._lock:
            self._status = {'kind': kind, 'title': title, 'detail': detail, 'checked_at': time.strftime('%H:%M')}

    def _finish(self):
        with self._lock:
            self._busy = False
            callback = self._on_idle if self._closing else None
        if callback:
            callback()

    def _login(self, account, visible):
        last = ['']
        def log(message):
            last[0] = message
            self._log(message)
        try:
            connected = self._core.run_login(account, log, visible=visible)
            if connected:
                campus_only = '外网探测' in last[0] and '未通过' in last[0]
                self._set_result('campus' if campus_only else 'online', '校园网已认证' if campus_only else '已连接互联网',
                                 '校园认证已在线，外网探测尚未通过。' if campus_only else '网络检测通过，可以正常使用。')
                with self._lock:
                    self._tell('校园网已认证。' if campus_only else '连接成功。', 'success')
            else:
                self._set_result('error', '连接未完成', '请查看运行记录，核对账号与运营商。')
        except Exception as error:
            message = str(error) if isinstance(error, RuntimeError) else '连接未完成，请检查网络后重试。'
            self._log(message)
            self._set_result('error', '连接未完成', message)
            with self._lock:
                self._tell(message, 'error')
        finally:
            account = None
            self._finish()

    def _probe(self):
        try:
            if self._core.online():
                self._set_result('online', '已连接互联网', '外网连通性检测通过，可以正常使用。')
                self._log('网络检查：外网连通性验证通过。')
            elif self._core.campus_online():
                self._set_result('campus', '校园网已认证', '校园认证已在线，外网探测尚未通过。')
                self._log('网络检查：校园认证已在线；外网探测暂未通过。')
            else:
                self._set_result('idle', '等待连接', '尚未检测到在线认证，保存账号后可连接校园网。')
                self._log('网络检查：尚未检测到在线认证。')
        except Exception:
            self._set_result('error', '暂时无法检测', '请确认已连接校园 Wi-Fi 或网线。')
        finally:
            self._finish()

    def _check(self):
        with self._lock:
            if self._busy:
                return self._response(False, '连接任务正在进行，请稍候。')
            self._busy = True
            self._status = {'kind': 'busy', 'title': '正在检查网络', 'detail': '正在读取网络与校园认证状态…', 'checked_at': None}
            return self._launch_worker(self._probe)

    def _clear(self):
        with self._lock:
            if self._busy:
                return self._response(False, '连接任务正在进行，请稍候。')
            try:
                self._core.set_startup(False)
                self._core.VAULT.unlink(missing_ok=True)
                self._account = None
                self._preferences['autostart'] = False
                self._set_result('idle', '等待配置', '填写账号后可以重新连接。')
                self._log('已清除本机账号密码，并关闭开机自动连接。')
                self._tell('本机账号已清除。', 'success')
                return self._response(True)
            except Exception:
                self._tell('账号暂时无法清除，请稍后重试。', 'error')
                return self._response(False, '账号暂时无法清除，请稍后重试。')

    def _motion(self, enabled):
        with self._lock:
            if not isinstance(enabled, bool):
                return self._response(False, '动效设置无效。')
            try:
                self._write_motion(enabled)
                self._preferences['motion'] = enabled
                return self._response(True)
            except OSError:
                return self._response(False, '动效设置未能保存。')

    def _request_close(self):
        with self._lock:
            if not self._busy:
                return True
            self._closing = True
            self._tell('连接仍在进行，完成后会自动关闭窗口。')
            return False


class Bridge:
    """Only these six functions are available to the packaged local page."""
    def __init__(self, controller, guard=None):
        self._controller = controller
        self._guard = guard or (lambda: True)

    def _check(self):
        if not self._guard():
            raise RuntimeError('本机界面保护尚未就绪。')

    def get_state(self, after_log_id=0):
        self._check()
        if not isinstance(after_log_id, int) or after_log_id < 0:
            after_log_id = 0
        return self._controller._snapshot(after_log_id)

    def save_settings(self, payload):
        self._check()
        return self._controller._save(payload)

    def connect(self, payload):
        self._check()
        return self._controller._save(payload, connect=True)

    def check_status(self):
        self._check()
        return self._controller._check()

    def clear_settings(self):
        self._check()
        return self._controller._clear()

    def set_motion(self, enabled):
        self._check()
        return self._controller._motion(enabled)


def launch(core, check_report=None):
    import webview
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('CampusAutoLogin.Desktop')
    controller = Controller(core, load_saved=not bool(check_report))
    html = render_page()
    guarded = threading.Event()
    allowed_documents = {'about:blank', 'data:text/html;charset=utf-8;base64,' + base64.b64encode(html.encode('utf-8')).decode('ascii')}
    window = webview.create_window('校园网 · Campus Auto Login', html=html, js_api=Bridge(controller, guarded.is_set),
                                   width=1100, height=800, min_size=(880, 690),
                                   hidden=bool(check_report), background_color='#F6F7F9', text_select=True)
    controller._on_idle = window.destroy
    window.events.closing += controller._request_close
    def guard_navigation():
        def block_external_navigation(sender, event):
            if str(event.Uri) not in allowed_documents:
                event.Cancel = True
        # Only this exact packaged inline document can navigate with the native bridge.
        try:
            window.native.webview.NavigationStarting += block_external_navigation
            guarded.set()
        except Exception:
            # The bridge remains disabled if the pinned native renderer changes.
            window.destroy()
            raise RuntimeError('无法建立本地页面导航保护。')
    window.events.before_show += guard_navigation
    webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False
    webview.settings['ALLOW_DOWNLOADS'] = False
    webview.settings['ALLOW_FILE_URLS'] = False
    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = False
    if check_report:
        check_started = threading.Lock()
        def check():
            try:
                deadline = time.monotonic() + 25
                while time.monotonic() < deadline:
                    ready = window.evaluate_js('Boolean(window.campusApp && window.campusApp.ready)')
                    if ready:
                        break
                    time.sleep(.1)
                else:
                    raise RuntimeError('Web UI bridge did not become ready')
                report = window.evaluate_js('window.campusApp.inspect()')
                report.update({'version': VERSION, 'renderer': 'edgechromium'})
                report['saved_password_exposed'] = 'password' in controller._snapshot()['account']
                window.evaluate_js('location.href="https://example.invalid/campus-ui-navigation-test"')
                time.sleep(.25)
                report['navigation_blocked'] = bool(window.evaluate_js('Boolean(window.campusApp?.ready && document.getElementById("account-form"))'))
                report['navigation_guard_installed'] = guarded.is_set()
                assert all(report[key] for key in ('ui_loaded', 'icon_loaded', 'web_frontend', 'bridge_ready',
                                                    'motion_loaded', 'password_is_masked', 'navigation_blocked', 'navigation_guard_installed'))
                assert not report['saved_password_exposed'] and not report['horizontal_overflow']
                Path(check_report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            except Exception as error:
                diagnostics = window.evaluate_js('({app:typeof window.campusApp,ready:window.campusApp?.ready,api:Object.keys(window.pywebview?.api||{}),platform:window.pywebview?.platform})')
                Path(check_report).write_text(json.dumps({'ui_loaded': False, 'error': type(error).__name__, 'diagnostics': diagnostics}), encoding='utf-8')
            finally:
                window.destroy()
        def start_check_once():
            if check_started.acquire(blocking=False):
                threading.Thread(target=check, daemon=True).start()
        window.events.loaded += start_check_once
    webview.start(gui='edgechromium', private_mode=True, icon=str(ROOT / 'assets' / 'app-icon.ico'))
    if not guarded.is_set():
        raise RuntimeError('本地页面保护未能初始化。')
    if check_report:
        result = json.loads(Path(check_report).read_text(encoding='utf-8'))
        if not result.get('ui_loaded'):
            raise RuntimeError('Web interface validation failed')
