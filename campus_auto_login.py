"""Windows campus portal helper. Credentials stay in Windows DPAPI storage."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import winreg

import websocket

PORTAL = 'http://10.0.253.14/?url=http://www.msftconnecttest.com/redirect'
HOST = '10.0.253.14'
APP_ID = 'CampusAutoLogin_10_0_253_14'
DATA = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / APP_ID
VAULT = DATA / 'account.dat'
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
CREATE_NO_WINDOW = 0x08000000


def http_json(url):
    with OPENER.open(url, timeout=3) as response:
        return json.load(response)


class Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]


def protect(raw, decrypt=False):
    buf = ctypes.create_string_buffer(raw)
    incoming = Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        func = crypt.CryptUnprotectData
        func.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = func(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing))
    else:
        func = crypt.CryptProtectData
        func.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = func(ctypes.byref(incoming), APP_ID, None, None, None, 1, ctypes.byref(outgoing))
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        kernel.LocalFree(outgoing.pbData)


def save_account(account):
    DATA.mkdir(parents=True, exist_ok=True)
    encrypted = protect(json.dumps(account, ensure_ascii=False).encode('utf-8'))
    temp = VAULT.with_suffix('.tmp')
    temp.write_bytes(encrypted)
    os.replace(temp, VAULT)


def load_account():
    if not VAULT.exists():
        return None
    return json.loads(protect(VAULT.read_bytes(), decrypt=True).decode('utf-8'))


def launch_command():
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--auto']
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    return [str(pythonw if pythonw.exists() else sys.executable), str(Path(__file__).resolve()), '--auto']


def startup_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return bool(winreg.QueryValueEx(key, APP_ID)[0])
    except OSError:
        return False


def set_startup(enabled):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, subprocess.list2cmdline(launch_command()))
        else:
            try:
                winreg.DeleteValue(key, APP_ID)
            except FileNotFoundError:
                pass


def browser_path():
    for env, rel in [('ProgramFiles(x86)', r'Microsoft\Edge\Application\msedge.exe'),
                     ('ProgramFiles', r'Microsoft\Edge\Application\msedge.exe'),
                     ('ProgramFiles', r'Google\Chrome\Application\chrome.exe'),
                     ('LOCALAPPDATA', r'Google\Chrome\Application\chrome.exe')]:
        candidate = Path(os.environ.get(env, '')) / rel
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError('没有找到 Edge 或 Chrome，请先安装其中一个浏览器。')


def portal_reachable():
    try:
        with socket.create_connection((HOST, 80), timeout=3):
            return True
    except OSError:
        return False


def online():
    # A redirected captive page is never accepted as a successful internet check.
    try:
        with OPENER.open('http://www.msftconnecttest.com/connecttest.txt', timeout=4) as r:
            return (urllib.parse.urlsplit(r.url).hostname == 'www.msftconnecttest.com'
                    and r.status == 200 and r.read(128).strip() == b'Microsoft Connect Test')
    except (OSError, urllib.error.URLError):
        return False


def campus_online():
    """Read-only status endpoint observed in the campus portal's a41.js."""
    try:
        with OPENER.open('http://' + HOST + '/drcom/chkstatus?callback=campusStatus', timeout=3) as r:
            if urllib.parse.urlsplit(r.url).hostname != HOST:
                return False
            text = r.read(65536).decode('utf-8', errors='replace')
        match = re.search(r'\{.*\}', text, re.S)
        return bool(match and json.loads(match.group()).get('result') == 1)
    except (OSError, ValueError, urllib.error.URLError):
        return False


class Browser:
    """One isolated browser instance; never touches the user's regular profile."""
    def __init__(self, visible=False, executable=None):
        self.profile = Path(tempfile.mkdtemp(prefix='campus-login-'))
        self.process = None
        self.ws = None
        self.seq = 0
        self.visible = visible
        self.executable = executable

    def __enter__(self):
        try:
            args = [self.executable or browser_path(), '--remote-debugging-port=0',
                    '--remote-debugging-address=127.0.0.1', '--user-data-dir=' + str(self.profile),
                    '--no-first-run', '--no-default-browser-check', '--disable-sync', '--no-proxy-server',
                    '--disable-extensions', '--window-size=1050,800', 'about:blank']
            if not self.visible:
                args.insert(-1, '--headless=new')
            self.process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                            creationflags=CREATE_NO_WINDOW)
            deadline = time.monotonic() + 25
            port_file = self.profile / 'DevToolsActivePort'
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError('浏览器未能启动。')
                if port_file.exists():
                    try:
                        port = int(port_file.read_text().splitlines()[0])
                        pages = http_json(f'http://127.0.0.1:{port}/json/list')
                        page = next((p for p in pages if p.get('type') == 'page'), None)
                        if page:
                            self.ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=15,
                                                                  suppress_origin=True, http_proxy_host=None)
                            return self
                    except (OSError, ValueError, IndexError, urllib.error.URLError):
                        pass
                time.sleep(.2)
            raise RuntimeError('浏览器启动超时。')
        except Exception:
            self.close()
            raise

    def call(self, method, params=None):
        self.seq += 1
        request_id = self.seq
        self.ws.send(json.dumps({'id': request_id, 'method': method, 'params': params or {}}))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            msg = json.loads(self.ws.recv())
            if msg.get('id') == request_id:
                if 'error' in msg:
                    raise RuntimeError('浏览器操作失败。')
                return msg.get('result', {})
        raise RuntimeError('浏览器操作超时。')

    def evaluate(self, js):
        result = self.call('Runtime.evaluate', {'expression': js, 'returnByValue': True, 'awaitPromise': True})
        if 'exceptionDetails' in result:
            raise RuntimeError('登录页面脚本暂不可用，请打开可见浏览器重试。')
        return result.get('result', {}).get('value')

    def close(self):
        if self.ws:
            try:
                self.call('Browser.close')
            except Exception:
                pass
            self.ws.close()
            self.ws = None
        if self.process:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=CREATE_NO_WINDOW, timeout=10)
        for _ in range(5):
            try:
                shutil.rmtree(self.profile)
                break
            except OSError:
                time.sleep(.3)

    def __exit__(self, *args):
        self.close()


# This runs only inside the approved portal origin, using the page's own controls.
DOM_HELPERS = r"""
const visible = e => !!(e && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden'
    && !e.disabled && e.type !== 'hidden');
const text = e => (e.innerText || e.value || e.textContent || '').trim();
const docs = [];
function collect(d) {
  if (d.location.hostname !== allowedHost || d.location.port && d.location.port !== '80') return;
  docs.push(d);
  for (const f of d.querySelectorAll('iframe,frame')) { try { collect(f.contentDocument); } catch (_) {} }
}
collect(document);
const norm = s => s.replace(/\s/g,'').toLowerCase();
const sameCarrier = (s, desired) => {
  s = norm(s); desired = norm(desired);
  if (!s || !desired) return false;
  if (s === desired) return true;
  for (const group of [['移动','中国移动','校园移动','cmcc'],['联通','中国联通','校园联通','unicom'],
                        ['电信','中国电信','校园电信','telecom'],['校园网','校园','教育网','校园用户']]) {
    if (group.includes(desired) && group.includes(s)) return true;
  }
  return false;
};
const setValue = (e,v) => {
  const proto = e.tagName === 'SELECT' ? e.ownerDocument.defaultView.HTMLSelectElement.prototype
                                      : e.ownerDocument.defaultView.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto,'value').set.call(e,v);
  e.dispatchEvent(new Event('input',{bubbles:true}));
  e.dispatchEvent(new Event('change',{bubbles:true}));
};
"""


def dom_script(action, account=None, allowed_host=HOST):
    config = json.dumps({'action': action, 'account': account or {}, 'allowedHost': allowed_host}, ensure_ascii=True)
    return '(async () => { const {action,account,allowedHost} = ' + config + ';' + DOM_HELPERS + r"""
if (!docs.length) return {status:'wrong-origin'};
for (const d of docs) {
  const password = [...d.querySelectorAll('input[type=password]')].find(visible);
  if (!password) continue;
  if (action === 'inspect') {
    const choices = [...d.querySelectorAll('select option')].map(text).filter(Boolean);
    return {status:'ready', choices};
  }
  if (action === 'carrier') {
    if (!account.operator) return {status:'carrier-ready'};
    for (const s of [...d.querySelectorAll('select')].filter(visible)) {
      const o = [...s.options].find(o => sameCarrier(text(o),account.operator));
      if (o) { setValue(s,o.value); return {status:'carrier-ready'}; }
    }
    for (const r of d.querySelectorAll('input[type=radio]')) {
      const labels = [...(r.labels || [])].map(text).join('') || text(r.parentElement);
      if (visible(r) && sameCarrier(labels, account.operator)) {
        r.click(); return {status:'carrier-ready'};
      }
    }
    const label = [...d.querySelectorAll('label,button,a,li,span,div')]
      .filter(visible).filter(e => sameCarrier(text(e),account.operator))
      .sort((a,b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length)[0];
    if (label) {
      const control = label.closest('label,button,a,li,[onclick],[role=option],[role=radio]');
      if (control) { control.click(); return {status:'carrier-ready'}; }
    }
    // Common custom dropdowns need to be opened before their options become visible.
    if (!account.opened) {
      const toggler = [...d.querySelectorAll('input,button,[role=combobox],[onclick],div,span')]
        .filter(visible).find(e => /^(中国)?(移动|联通|电信)$|^校园网$|^请选择(运营商|服务)$/.test(text(e)));
      if (toggler) { toggler.click(); return {status:'carrier-opened'}; }
    }
    return {status:'carrier-missing'};
  }
  if (action !== 'submit') return {status:'unsupported'};
  const inputs = [...d.querySelectorAll('input')].filter(visible);
  const captcha = inputs.some(e => /captcha|verify|验证码|校验码/i.test(
    [e.name,e.id,e.placeholder].join(' ')) && e.type !== 'hidden');
  if (captcha) return {status:'captcha'};
  const users = inputs.filter(e => ['text','tel','email','number',''].includes(e.type));
  const username = users.find(e => /user|account|ddddd|账号|帐号|学号|用户名/i.test(
    [e.name,e.id,e.placeholder].join(' '))) || (users.length === 1 ? users[0] : null);
  if (!username) return {status:'username-missing'};
  const buttons = [...d.querySelectorAll('button,input[type=submit],input[type=button],a,[role=button],[onclick]')]
    .filter(visible).filter(e => /^(登\s*[录陆]|登\s*[录陆]上网|立即登录|连接|连接网络|上网|login|sign in)$/i.test(text(e)));
  const button = buttons.find(e => /^(BUTTON|INPUT)$/.test(e.tagName)) || buttons[0];
  const form = password.form;
  if (!button && !form) return {status:'button-missing'};
  setValue(username,account.username);
  setValue(password,account.password);
  if (button) button.click();
  else if (form.requestSubmit) form.requestSubmit();
  else return {status:'button-missing'};
  return {status:'submitted'};
}
return {status:'not-ready'};
})()
"""


ERRORS = {
    'wrong-origin': '页面跳转到了其他地址，已停止填写密码。',
    'not-ready': '没有识别到登录表单，请选择“显示登录浏览器”后测试。',
    'carrier-missing': '没有找到所填运营商。请填写网页上的完整名称；若网页已默认选择，可将运营商留空。',
    'captcha': '检测到验证码，需要手动登录。',
    'username-missing': '无法确定账号输入框，需要按实际登录页适配。',
    'button-missing': '无法确定登录按钮，需要按实际登录页适配。',
}


def run_login(account, log, auto=False, visible=False, internet_check=online):
    if internet_check():
        log('当前已能访问互联网，无需重复登录。')
        return True
    if campus_online():
        log('校园认证显示已登录；外网探测未通过，跳过重复认证。')
        return True
    if auto:
        log('等待校园网络就绪，最长 10 分钟。')
        deadline = time.monotonic() + 600
        while not portal_reachable():
            if time.monotonic() >= deadline:
                log('未连接到校园登录服务器，本次自动登录结束。')
                return False
            time.sleep(15)
            if internet_check():
                log('网络已连接。')
                return True
    elif not portal_reachable():
        raise RuntimeError('无法访问 10.0.253.14，请先连接校园 Wi-Fi 或校园网网线，并检查 VPN/代理。')
    log('正在打开校园网登录页……')
    with Browser(visible=visible) as browser:
        browser.call('Page.enable')
        # No raw server errors or page contents are logged; these can contain credentials.
        browser.call('Page.navigate', {'url': PORTAL})
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            try:
                result = browser.evaluate(dom_script('inspect'))
                if result and result.get('status') == 'ready':
                    break
            except (RuntimeError, websocket.WebSocketException):
                pass
            if internet_check():
                log('网络已连接。')
                return True
            time.sleep(1)
        else:
            if campus_online():
                log('校园认证显示已登录，跳过重复认证。')
                return True
            raise RuntimeError('登录页没有就绪。请勾选“显示登录浏览器”查看页面，或发送登录页截图以便适配。')
        result = browser.evaluate(dom_script('carrier', account))
        if result.get('status') == 'carrier-opened':
            time.sleep(.8)
            result = browser.evaluate(dom_script('carrier', dict(account, opened=True)))
        if result.get('status') != 'carrier-ready':
            raise RuntimeError(ERRORS.get(result.get('status'), '无法选择运营商。'))
        time.sleep(.8)
        log('正在填写账号并提交登录……')
        result = browser.evaluate(dom_script('submit', account))
        if result.get('status') != 'submitted':
            raise RuntimeError(ERRORS.get(result.get('status'), '无法提交登录。'))
        # At most ONE submission each run, preventing repeated bad-password attempts.
        for _ in range(10):
            time.sleep(2)
            if internet_check():
                log('登录成功：已通过外网连通性验证。')
                return True
            if campus_online():
                log('登录成功：校园认证显示已在线；外网探测暂未通过。')
                return True
        if visible:
            log('尚未验证联网。浏览器保留 60 秒，请查看页面提示。')
            time.sleep(60)
        raise RuntimeError('已提交一次登录，但未验证联网。请核对账号、密码、运营商，或查看登录页提示；程序不会反复提交。')


def log_file(message):
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / 'status.log'
    if path.exists() and path.stat().st_size > 128 * 1024:
        path.write_text('', encoding='utf-8')
    with path.open('a', encoding='utf-8') as f:
        f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + message + '\n')


def exclusive_run():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    username = os.environ.get('USERNAME', '')
    name = APP_ID + '_' + hashlib.sha256(username.encode()).hexdigest()[:12]
    handle = kernel.CreateMutexW(None, False, 'Local\\' + name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(handle)
        return None
    return handle


def gui():
    import tkinter as tk
    from tkinter import ttk, messagebox
    root = tk.Tk()
    root.title('校园网自动登录')
    root.geometry('620x570')
    root.minsize(600, 550)
    root.option_add('*Font', ('Microsoft YaHei UI', 10))
    frame = ttk.Frame(root, padding=22)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='校园网自动登录', font=('Microsoft YaHei UI', 18, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='配置一次，登录 Windows 后自动连接校园网。').pack(anchor='w', pady=(5,15))
    fields = ttk.Frame(frame)
    fields.pack(fill='x')
    fields.columnconfigure(1, weight=1)
    user = tk.StringVar()
    password = tk.StringVar()
    operator = tk.StringVar(value='中国移动')
    start = tk.BooleanVar(value=startup_enabled() or not VAULT.exists())
    show = tk.BooleanVar(value=False)
    for row, (label, variable) in enumerate([('账号', user), ('密码', password), ('运营商', operator)]):
        ttk.Label(fields, text=label).grid(row=row,column=0,sticky='w',padx=(0,15),pady=7)
        if row == 2:
            entry = ttk.Combobox(fields, textvariable=variable, values=['中国移动','中国电信','中国联通','教师专用','校园网',''])
        else:
            entry = ttk.Entry(fields, textvariable=variable, show='●' if row == 1 else '')
        entry.grid(row=row,column=1,sticky='ew',pady=7)
    ttk.Label(frame,text='运营商按网页名称填写；留空表示保留网页默认选择。', foreground='#555555').pack(anchor='w',pady=(3,9))
    ttk.Checkbutton(frame,text='登录 Windows 后自动连接（无需管理员）',variable=start).pack(anchor='w')
    ttk.Checkbutton(frame,text='测试时显示登录浏览器，便于查看网页提示',variable=show).pack(anchor='w',pady=5)
    buttons = ttk.Frame(frame)
    buttons.pack(fill='x',pady=12)
    status = tk.Text(frame,height=8,wrap='word',state='disabled',font=('Microsoft YaHei UI',9))
    status.pack(fill='both',expand=True)
    ttk.Label(frame,text='账号密码仅在本机加密保存。自动登录每次最多提交一次。',foreground='#555555').pack(anchor='w',pady=(10,0))
    messages = queue.Queue()
    busy = [False]
    def log(message):
        messages.put(message)
        log_file(message)
    try:
        old = load_account()
        if old:
            user.set(old.get('username',''))
            password.set(old.get('password',''))
            operator.set(old.get('operator',''))
    except Exception:
        messages.put('原配置无法解密，请重新填写账号密码。')
    def read_fields():
        if not user.get().strip() or not password.get():
            raise ValueError('请填写账号和密码。')
        return {'username': user.get().strip(), 'password': password.get(), 'operator':operator.get().strip()}
    def save():
        try:
            account = read_fields()
            save_account(account)
            set_startup(start.get())
            log('配置已加密保存。' + ('已开启开机登录。' if start.get() else '开机登录未开启。'))
            return account
        except Exception as e:
            messagebox.showerror('未能保存', str(e))
    def test():
        if busy[0]:
            return
        account = save()
        if not account:
            return
        visible = show.get()
        busy[0] = True
        test_button.config(state='disabled')
        def worker():
            handle = None
            try:
                handle = exclusive_run()
                if handle is None:
                    log('已有登录任务正在运行，请稍后重试。')
                    return
                run_login(account, log, visible=visible)
            except Exception as e:
                # Exceptions from the network/debug socket may include data. Only use our safe messages.
                log(str(e) if isinstance(e, RuntimeError) else '操作失败，请关闭测试浏览器后重试。')
            finally:
                if handle:
                    ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(handle))
                messages.put(None)
        threading.Thread(target=worker,daemon=True).start()
    def remove():
        if busy[0]:
            messagebox.showinfo('请稍候','请等待当前登录测试结束，再删除配置。')
            return
        set_startup(False)
        start.set(False)
        VAULT.unlink(missing_ok=True)
        password.set('')
        log('已删除本机账号密码，并关闭开机登录。')
    ttk.Button(buttons,text='保存配置',command=save).pack(side='left')
    test_button = ttk.Button(buttons,text='保存并测试登录',command=test)
    test_button.pack(side='left',padx=8)
    ttk.Button(buttons,text='删除配置 / 关闭自启',command=remove).pack(side='right')
    def pump():
        while True:
            try:
                item = messages.get_nowait()
            except queue.Empty:
                break
            if item is None:
                busy[0] = False
                test_button.config(state='normal')
            else:
                status.config(state='normal')
                status.insert('end', time.strftime('%H:%M:%S ') + item + '\n')
                status.see('end')
                status.config(state='disabled')
        root.after(150,pump)
    def close():
        if busy[0]:
            messagebox.showinfo('正在测试','请等待登录测试结束后关闭窗口，以便程序清理临时浏览器。')
        else:
            root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    messages.put('请先连接校园网络。账号写法与手动登录时一致。')
    root.after(150,pump)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--auto',action='store_true')
    args = parser.parse_args()
    if not args.auto:
        gui()
        return
    handle = exclusive_run()
    if handle is None:
        return
    try:
        account = load_account()
        if not account:
            log_file('尚未配置账号，请先打开程序完成设置。')
            return
        run_login(account, log_file, auto=True)
    except Exception as e:
        log_file(str(e) if isinstance(e, RuntimeError) else '自动登录未完成，请打开程序测试。')
    finally:
        ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(handle))


if __name__ == '__main__':
    main()
