"""Quiet, light desktop UI inspired by Material's spacing and controls."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import queue
import threading
import time
import tkinter as tk

import customtkinter as ctk
from PIL import Image
from ui_fx import Motion
from ui_controls import MotionButton, MotionSwitch

BG = '#F4F6F9'
SURFACE = '#FFFFFF'
INK = '#202124'
SECONDARY = '#5F6368'
BLUE = '#1A73E8'
BLUE_HOVER = '#1765CC'
LINE = '#CAD2DE'
PALE_BLUE = '#E8F0FE'
FONT = 'Microsoft YaHei UI'
ERROR = '#B3261E'
DEFAULT_OPERATOR = '使用网页默认'


class CampusWindow(ctk.CTk):
    def __init__(self, api, load_saved=True):
        ctk.set_appearance_mode('light')
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('CampusAutoLogin.Desktop')
        super().__init__(fg_color=BG)
        self.motion = Motion(self)
        assets = Path(__file__).resolve().parent / 'assets'
        self.icon_path = str(assets / 'app-icon.ico')
        self.iconbitmap(default=self.icon_path)
        self.api = api
        self.title('校园网自动登录')
        area = wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(area), 0)
        scale = self._get_window_scaling()
        x = max(area.left, round(area.left + (area.right - area.left - 880 * scale) / 2))
        y = max(area.top + 8, round(area.top + (area.bottom - area.top - 720 * scale - 30) / 2))
        self.geometry(f'880x720+{x}+{y}')
        self.minsize(840, 720)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.messages = queue.Queue()
        self.busy = False
        self.closing_after_task = False
        self.invalid_fields = set()
        self.revealed = False
        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.operator = tk.StringVar(value='中国移动')
        self.autostart = tk.BooleanVar(value=(api.startup_enabled() or not api.VAULT.exists()) if load_saved else True)
        self.show_browser = tk.BooleanVar(value=False)

        header = ctk.CTkFrame(self, fg_color='transparent')
        header.grid(row=0, column=0, sticky='ew', padx=28, pady=(22, 18))
        header.grid_columnconfigure(1, weight=1)
        self.brand_image = ctk.CTkImage(Image.open(assets / 'app-icon.png'), size=(48, 48))
        icon = ctk.CTkLabel(header, text='', image=self.brand_image, width=48, height=48)
        icon.grid(row=0, column=0, rowspan=2, padx=(0, 14))
        self.label(header, '校园网', 24, INK).grid(row=0, column=1, sticky='w')
        self.label(header, '自动登录与开机连接', 13).grid(row=1, column=1, sticky='w', pady=(3, 0))
        ctk.CTkLabel(header, text='仅在本机保存', font=(FONT, 12), text_color=SECONDARY,
                     fg_color='#E9EDF3', corner_radius=5, height=28, width=116).grid(row=0, column=2, rowspan=2, sticky='e')

        surface = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=8, border_width=1, border_color=LINE)
        surface.grid(row=1, column=0, sticky='nsew', padx=28)
        surface.grid_columnconfigure(0, weight=115)
        surface.grid_columnconfigure(2, weight=100)
        surface.grid_rowconfigure(0, weight=1)
        form = ctk.CTkFrame(surface, fg_color='transparent')
        form.grid(row=0, column=0, sticky='nsew', padx=24, pady=22)
        form.grid_columnconfigure(0, weight=1)
        self.label(form, '登录信息', 16, INK).grid(row=0, column=0, sticky='w')
        self.form_hint = self.label(form, '填写校园网账号，选择对应运营商', 12)
        self.form_hint.grid(row=1, column=0, sticky='w', pady=(3, 13))
        self.label(form, '账号', 13, INK).grid(row=2, column=0, sticky='w', pady=(0, 7))
        self.account_entry = self.entry(form, self.username, 'username', placeholder='输入校园网账号')
        self.account_entry.grid(row=3, column=0, sticky='ew')
        self.label(form, '密码', 13, INK).grid(row=4, column=0, sticky='w', pady=(17, 7))
        password_box = ctk.CTkFrame(form, fg_color=SURFACE, corner_radius=6, border_width=1, border_color=LINE)
        password_box.grid(row=5, column=0, sticky='ew')
        password_box.grid_columnconfigure(0, weight=1)
        self.password_entry = ctk.CTkEntry(password_box, textvariable=self.password, show='●',
                                         font=(FONT, 14), height=38, border_width=0,
                                         fg_color=SURFACE, text_color=INK, corner_radius=6)
        self.password_entry.grid(row=0, column=0, sticky='ew', padx=(3, 0), pady=1)
        self.reveal_button = MotionButton(password_box, self.motion, text='显示', command=self.toggle_password,
                                         width=52, height=30, corner_radius=6, fg_color=SURFACE,
                                         text_color=BLUE, hover_color=PALE_BLUE, font=(FONT, 12))
        self.reveal_button.grid(row=0, column=1, padx=(0, 7))
        self.password_box = password_box
        self.bind_field_focus(self.password_entry, password_box, 'password')
        self.label(form, '运营商', 13, INK).grid(row=6, column=0, sticky='w', pady=(17, 7))
        self.operator_entry = ctk.CTkComboBox(form, variable=self.operator,
                values=['中国移动', '中国电信', '中国联通', '教师专用', '校园网', DEFAULT_OPERATOR],
                height=40, corner_radius=6, border_width=1, border_color=LINE,
                fg_color=SURFACE, text_color=INK, button_color='#F1F3F4', button_hover_color=PALE_BLUE,
                dropdown_fg_color=SURFACE, dropdown_text_color=INK, dropdown_hover_color=PALE_BLUE,
                font=(FONT, 14), dropdown_font=(FONT, 13))
        self.operator_entry.grid(row=7, column=0, sticky='ew')
        self.bind_field_focus(self.operator_entry, self.operator_entry, 'operator')
        self.label(form, '也可手动输入；留空使用网页默认选项', 11).grid(row=8, column=0, sticky='w', pady=(9, 0))

        ctk.CTkFrame(surface, width=1, fg_color='#ECEEF1', corner_radius=0).grid(row=0, column=1, sticky='ns', pady=27)
        settings = ctk.CTkFrame(surface, fg_color='transparent')
        settings.grid(row=0, column=2, sticky='nsew', padx=24, pady=22)
        settings.grid_columnconfigure(0, weight=1)
        self.label(settings, '连接偏好', 16, INK).grid(row=0, column=0, sticky='w', pady=(0, 23))
        self.autostart_switch = MotionSwitch(settings, self.motion, '开机自动连接', self.autostart)
        self.autostart_switch.grid(row=1, column=0, sticky='ew')
        self.label(settings, '登录 Windows 后在后台运行', 11).grid(row=2, column=0, sticky='w', pady=(7, 23))
        self.browser_switch = MotionSwitch(settings, self.motion, '显示登录浏览器', self.show_browser)
        self.browser_switch.grid(row=3, column=0, sticky='ew')
        self.label(settings, '测试时查看校园网页面提示', 11).grid(row=4, column=0, sticky='w', pady=(7, 24))
        ctk.CTkFrame(settings, height=1, fg_color='#ECEEF1').grid(row=5, column=0, sticky='ew', pady=(0, 21))
        self.state_badge = ctk.CTkLabel(settings, text='等待配置', text_color=SECONDARY,
                                      fg_color='#EDF1F6', corner_radius=4, height=28, width=116, font=(FONT, 12))
        self.state_badge.grid(row=6, column=0, sticky='w')
        self.state_hint = self.label(settings, '填好账号后，点击下方按钮测试连接。', 12, wraplength=228, justify='left')
        self.state_hint.grid(row=7, column=0, sticky='w', pady=(10, 0))
        self.progress = ctk.CTkProgressBar(settings, mode='indeterminate', height=3, corner_radius=0,
                                        fg_color='#E8EDF4', progress_color=BLUE, indeterminate_speed=1.1)
        self.progress.grid(row=8, column=0, sticky='ew', pady=(13, 0))
        self.progress.grid_remove()

        activity = ctk.CTkFrame(self, fg_color='transparent')
        activity.grid(row=2, column=0, sticky='ew', padx=30, pady=(15, 0))
        activity.grid_columnconfigure(0, weight=1)
        self.label(activity, '运行记录', 12, SECONDARY).grid(row=0, column=0, sticky='w')
        self.new_logs = MotionButton(activity, self.motion, text='查看新记录', command=self.show_latest_logs,
                fg_color=BG, text_color=BLUE, hover_color=PALE_BLUE, height=24, width=90, corner_radius=5, font=(FONT, 11))
        self.new_logs.grid(row=0, column=1, sticky='e')
        self.new_logs.grid_remove()
        self.status = ctk.CTkTextbox(activity, height=68, fg_color='#EDF1F6', text_color=SECONDARY,
                                     font=(FONT, 12), wrap='word', border_width=1, border_color='#DBE1EA', corner_radius=6,
                                     scrollbar_button_color='#DADCE0', scrollbar_button_hover_color='#BDC1C6')
        self.status.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(4, 0))
        self.status.tag_config('success', foreground='#137333')
        self.status.tag_config('warning', foreground='#8B5C00')
        self.status.tag_config('error', foreground=ERROR)
        self.status.configure(state='disabled')

        footer = ctk.CTkFrame(self, fg_color='transparent')
        footer.grid(row=3, column=0, sticky='ew', padx=28, pady=(14, 20))
        footer.grid_columnconfigure(1, weight=1)
        self.clear_button = MotionButton(footer, self.motion, text='清除配置', command=self.remove, height=40, width=96,
                        corner_radius=8, fg_color=BG, text_color=SECONDARY,
                        hover_color='#EDF0F5', font=(FONT, 13))
        self.clear_button.grid(row=0, column=0, sticky='w')
        self.save_button = MotionButton(footer, self.motion, text='保存设置', command=self.save, width=130, height=40,
                        corner_radius=8, fg_color=SURFACE, text_color=BLUE, border_width=1,
                        border_color=LINE, hover_color=PALE_BLUE, font=(FONT, 13))
        self.save_button.grid(row=0, column=2, padx=(0, 10))
        self.test_button = MotionButton(footer, self.motion, text='保存并连接', command=self.test, width=130, height=40,
                        corner_radius=8, fg_color=BLUE, hover_color=BLUE_HOVER, text_color=SURFACE,
                        font=(FONT, 13))
        self.test_button.grid(row=0, column=3)

        self.notice = ctk.CTkFrame(self, fg_color='#FCE8E6', border_color='#F3C7C3', border_width=1, corner_radius=8)
        self.notice.grid_columnconfigure(0, weight=1)
        self.notice_text = self.label(self.notice, '', 12, ERROR, wraplength=690, justify='left')
        self.notice_text.grid(row=0, column=0, sticky='ew', padx=(15, 5), pady=12)
        self.notice_close = MotionButton(self.notice, self.motion, text='×', command=self.hide_notice,
                width=28, height=28, fg_color='#FCE8E6', hover_color='#F7D5D1', text_color=ERROR,
                corner_radius=5, font=(FONT, 18))
        self.notice_close.grid(row=0, column=1, padx=(0, 9))

        if load_saved:
            try:
                old = api.load_account()
                if old:
                    self.username.set(old.get('username', ''))
                    self.password.set(old.get('password', ''))
                    self.operator.set(old.get('operator', '') or DEFAULT_OPERATOR)
                    self.set_state('就绪', '设置已载入，可以直接连接。')
            except Exception:
                self.messages.put('原配置无法解密，请重新填写账号密码。')
        self.messages.put('请先连接校园 Wi-Fi，或插入校园网网线。')
        self.username.trace_add('write', lambda *_: self.clear_field_error('username'))
        self.password.trace_add('write', lambda *_: self.clear_field_error('password'))
        self.bind('<Return>', lambda _: self.test())
        self.bind('<Escape>', lambda _: self.hide_notice())
        self.bind('<FocusOut>', self.on_window_blur, add='+')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(250, self.style_native_frame)
        self.after(300, lambda: self.iconbitmap(default=self.icon_path))
        self._pump_job = self.after(120, self.pump)

    @staticmethod
    def label(parent, text, size=13, color=SECONDARY, **kwargs):
        return ctk.CTkLabel(parent, text=text, font=(FONT, size), text_color=color, anchor='w', **kwargs)

    def entry(self, parent, variable, name, placeholder=''):
        entry = ctk.CTkEntry(parent, textvariable=variable, placeholder_text=placeholder,
                            font=(FONT, 14), height=40, corner_radius=6, border_width=1,
                            border_color=LINE, fg_color=SURFACE, text_color=INK)
        self.bind_field_focus(entry, entry, name)
        return entry

    def bind_field_focus(self, entry, border, name):
        entry.bind('<FocusIn>', lambda _: self.motion.color(border, 'border_color', ERROR if name in self.invalid_fields else BLUE, 140))
        entry.bind('<FocusOut>', lambda _: self.motion.color(border, 'border_color', ERROR if name in self.invalid_fields else LINE, 140))

    def clear_field_error(self, name):
        if name in self.invalid_fields:
            self.invalid_fields.discard(name)
            target = self.account_entry if name == 'username' else self.password_box
            self.motion.color(target, 'border_color', LINE, 140)
            if not self.invalid_fields:
                self.form_hint.configure(text='填写校园网账号，选择对应运营商', text_color=SECONDARY)

    def toggle_password(self):
        self.set_revealed(bool(self.password_entry.cget('show')))

    def set_revealed(self, shown):
        self.revealed = shown
        self.motion.cancel('hide-password')
        insertion = self.password_entry.index('insert')
        self.password_entry.configure(show='' if self.revealed else '●')
        self.password_entry.icursor(insertion)
        self.reveal_button.configure(text='隐藏' if self.revealed else '显示')
        if shown:
            self.motion.later('hide-password', 15000, lambda: self.set_revealed(False))

    def on_window_blur(self, event):
        # Moving between fields must not hide the password; leaving this window must.
        self.motion.later('check-window-focus', 30, self.hide_password_if_unfocused)

    def hide_password_if_unfocused(self):
        focus = self.focus_displayof()
        if focus is None or focus.winfo_toplevel() is not self:
            self.set_revealed(False)

    def style_native_frame(self):
        """Keep system resize/drag behavior with a crisp Windows 11 frame."""
        try:
            user = ctypes.WinDLL('user32')
            user.GetParent.argtypes = [wintypes.HWND]
            user.GetParent.restype = wintypes.HWND
            hwnd = user.GetParent(self.winfo_id())
            dwm = ctypes.WinDLL('dwmapi').DwmSetWindowAttribute
            dwm.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            for attribute, value in [(33, 1), (34, 0xB8A999), (35, 0xF3EDE9), (36, 0x242120)]:
                color = wintypes.DWORD(value)
                dwm(hwnd, attribute, ctypes.byref(color), ctypes.sizeof(color))
        except OSError:
            # Unsupported DWM attributes leave the standard Windows frame intact.
            pass

    def set_state(self, title, hint, success=False, error=False):
        color, background = (('#137333', '#E6F4EA') if success else
                             ('#B3261E', '#FCE8E6') if error else (SECONDARY, '#F1F3F4'))
        self.state_badge.configure(text=title)
        self.motion.color(self.state_badge, 'text_color', color, 180)
        self.motion.color(self.state_badge, 'fg_color', background, 180)
        self.state_hint.configure(text=hint)

    def show_notice(self, message, error=True):
        self.notice_text.configure(text=message, text_color=ERROR if error else '#31537B')
        self.notice.place(relx=.5, rely=1, y=-82, anchor='s', relwidth=.91)
        self.notice.lift()
        self.motion.color(self.notice, 'fg_color', '#FCE8E6' if error else '#E8F0FE', 160)
        self.motion.later('notice', 6500, self.hide_notice)

    def hide_notice(self):
        self.motion.cancel('notice')
        self.notice.place_forget()

    def show_latest_logs(self):
        self.status.see('end')
        self.new_logs.grid_remove()

    def append_log(self, message):
        bottom = self.status.yview()[1] >= .999
        style = ('warning' if '未通过' in message else 'error' if any(s in message for s in ('失败', '无法', '未完成', '不可用'))
                 else 'success' if any(s in message for s in ('成功', '已登录', '已连接')) else '')
        self.status.configure(state='normal')
        self.status.insert('end', time.strftime('%H:%M  ') + message + '\n', (style,) if style else ())
        excess = int(self.status.index('end-1c').split('.')[0]) - 501
        if excess > 0:
            self.status.delete('1.0', f'{excess + 1}.0')
        self.status.configure(state='disabled')
        if bottom:
            self.status.see('end')
        else:
            self.new_logs.grid()

    def log(self, message):
        self.messages.put(message)
        self.api.log_file(message)

    def read_fields(self):
        if not self.username.get().strip():
            self.invalid_fields.add('username')
            self.account_entry.focus_set()
            self.motion.color(self.account_entry, 'border_color', ERROR, 120)
            raise ValueError('请先填写校园网账号。')
        if not self.password.get():
            self.invalid_fields.add('password')
            self.password_entry.focus_set()
            self.motion.color(self.password_box, 'border_color', ERROR, 120)
            raise ValueError('请填写账号对应的密码。')
        operator = self.operator.get().strip()
        return dict(username=self.username.get().strip(), password=self.password.get(),
                    operator='' if operator == DEFAULT_OPERATOR else operator)

    def save(self):
        if self.busy:
            return None
        try:
            account = self.read_fields()
            self.api.save_account(account)
            self.api.set_startup(self.autostart.get())
            self.hide_notice()
            self.log('设置已保存。' + ('开机自动连接已开启。' if self.autostart.get() else '开机自动连接已关闭。'))
            self.set_state('设置已保存', '下次登录 Windows 时自动连接。' if self.autostart.get() else '需要时可在这里手动连接。')
            return account
        except Exception as error:
            message = str(error) if isinstance(error, ValueError) else '设置暂时无法保存，请稍后重试。'
            self.form_hint.configure(text=message, text_color=ERROR)
            self.show_notice(message)

    def set_busy(self, busy):
        self.busy = busy
        for button in (self.test_button, self.save_button, self.clear_button, self.reveal_button):
            button.set_enabled(not busy)
        self.autostart_switch.set_enabled(not busy)
        self.browser_switch.set_enabled(not busy)
        for field in (self.account_entry, self.password_entry, self.operator_entry):
            field.configure(state='disabled' if busy else 'normal')
        self.test_button.configure(text='正在连接…' if busy else '保存并连接')
        if busy and not self.motion.reduced:
            self.progress.grid()
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.grid_remove()

    def test(self):
        if self.busy:
            return
        account = self.save()
        if not account:
            return
        visible = self.show_browser.get()
        self.set_revealed(False)
        self.set_busy(True)
        self.set_state('正在连接', '正在检查网络，请稍候。')
        def worker():
            handle = None
            last_message = ['']
            def task_log(message):
                last_message[0] = message
                self.log(message)
            try:
                handle = self.api.exclusive_run()
                if handle is None:
                    raise RuntimeError('已有登录任务正在运行，请稍后重试。')
                connected = self.api.run_login(account, task_log, visible=visible)
                self.messages.put(('result', bool(connected), last_message[0]))
            except Exception as error:
                self.log(str(error) if isinstance(error, RuntimeError) else '操作失败，请关闭测试浏览器后重试。')
                self.messages.put(('result', False, str(error) if isinstance(error, RuntimeError) else '连接未完成，请稍后重试。'))
            finally:
                if handle:
                    ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(handle))
                self.messages.put(None)
        threading.Thread(target=worker, daemon=True).start()

    def remove(self):
        if self.busy:
            return
        try:
            self.api.set_startup(False)
            self.api.VAULT.unlink(missing_ok=True)
            self.autostart.set(False)
            self.password.set('')
            self.set_revealed(False)
            self.log('已清除本机账号密码，并关闭开机自动连接。')
            self.set_state('等待配置', '填写账号后可以重新连接。')
        except Exception:
            self.show_notice('配置暂时无法删除，请稍后重试。')

    def present_result(self, connected, detail=''):
        self.set_revealed(False)
        if connected:
            if '外网探测' in detail and '未通过' in detail:
                self.set_state('校园网已认证', '校园认证在线，外网探测尚未通过。', success=True)
            else:
                self.set_state('已连接', '网络检测通过，可以正常使用。', success=True)
        else:
            self.set_state('连接未完成', '请查看运行记录，核对账号和运营商。', error=True)
            self.show_notice(detail or '连接未完成，请查看运行记录。')

    def pump(self):
        while True:
            try:
                item = self.messages.get_nowait()
            except queue.Empty:
                break
            if item is None:
                self.set_busy(False)
                if self.closing_after_task:
                    self.destroy()
                    return
            elif isinstance(item, tuple):
                self.present_result(item[1], item[2] if len(item) > 2 else '')
            else:
                self.append_log(item)
        self._pump_job = self.after(120, self.pump)

    def destroy(self):
        self.motion.shutdown()
        self.progress.stop()
        # Cancel pending Tcl callbacks before a second window is constructed in tests.
        for job in self.tk.call('after', 'info'):
            self.tk.call('after', 'cancel', job)
        self._pump_job = None
        super().destroy()

    def close(self):
        if self.busy:
            self.closing_after_task = True
            self.show_notice('连接仍在进行，结束后将自动关闭窗口。', error=False)
        else:
            self.destroy()


def launch(api):
    CampusWindow(api).mainloop()
