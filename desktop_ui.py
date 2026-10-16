"""Quiet, light desktop UI inspired by Material's spacing and controls."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image

BG = '#F4F6F9'
SURFACE = '#FFFFFF'
INK = '#202124'
SECONDARY = '#5F6368'
BLUE = '#1A73E8'
BLUE_HOVER = '#1765CC'
LINE = '#CAD2DE'
PALE_BLUE = '#E8F0FE'
FONT = 'Microsoft YaHei UI'


class CampusWindow(ctk.CTk):
    def __init__(self, api, load_saved=True):
        ctk.set_appearance_mode('light')
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('CampusAutoLogin.Desktop')
        super().__init__(fg_color=BG)
        assets = Path(__file__).resolve().parent / 'assets'
        self.iconbitmap(default=str(assets / 'app-icon.ico'))
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
        self.label(form, '填写校园网账号，选择对应运营商', 12).grid(row=1, column=0, sticky='w', pady=(3, 13))
        self.label(form, '账号', 13, INK).grid(row=2, column=0, sticky='w', pady=(0, 7))
        self.account_entry = self.entry(form, self.username, placeholder='输入校园网账号')
        self.account_entry.grid(row=3, column=0, sticky='ew')
        self.label(form, '密码', 13, INK).grid(row=4, column=0, sticky='w', pady=(17, 7))
        password_box = ctk.CTkFrame(form, fg_color=SURFACE, corner_radius=6, border_width=1, border_color=LINE)
        password_box.grid(row=5, column=0, sticky='ew')
        password_box.grid_columnconfigure(0, weight=1)
        self.password_entry = ctk.CTkEntry(password_box, textvariable=self.password, show='●',
                                         font=(FONT, 14), height=38, border_width=0,
                                         fg_color=SURFACE, text_color=INK, corner_radius=6)
        self.password_entry.grid(row=0, column=0, sticky='ew', padx=(3, 0), pady=1)
        self.reveal_button = ctk.CTkButton(password_box, text='显示', command=self.toggle_password,
                                         width=52, height=30, corner_radius=6, fg_color=SURFACE,
                                         text_color=BLUE, hover_color=PALE_BLUE, font=(FONT, 12))
        self.reveal_button.grid(row=0, column=1, padx=(0, 7))
        self.password_entry.bind('<FocusIn>', lambda _: password_box.configure(border_color=BLUE))
        self.password_entry.bind('<FocusOut>', lambda _: password_box.configure(border_color=LINE))
        self.label(form, '运营商', 13, INK).grid(row=6, column=0, sticky='w', pady=(17, 7))
        self.operator_entry = ctk.CTkComboBox(form, variable=self.operator,
                values=['中国移动', '中国电信', '中国联通', '教师专用', '校园网', ''],
                height=40, corner_radius=6, border_width=1, border_color=LINE,
                fg_color=SURFACE, text_color=INK, button_color=SURFACE, button_hover_color='#F1F3F4',
                dropdown_fg_color=SURFACE, dropdown_text_color=INK, dropdown_hover_color=PALE_BLUE,
                font=(FONT, 14), dropdown_font=(FONT, 13))
        self.operator_entry.grid(row=7, column=0, sticky='ew')
        self.label(form, '也可手动输入；留空使用网页默认选项', 11).grid(row=8, column=0, sticky='w', pady=(9, 0))

        ctk.CTkFrame(surface, width=1, fg_color='#ECEEF1', corner_radius=0).grid(row=0, column=1, sticky='ns', pady=27)
        settings = ctk.CTkFrame(surface, fg_color='transparent')
        settings.grid(row=0, column=2, sticky='nsew', padx=24, pady=22)
        settings.grid_columnconfigure(0, weight=1)
        self.label(settings, '连接偏好', 16, INK).grid(row=0, column=0, sticky='w', pady=(0, 23))
        self.switch(settings, '开机自动连接', self.autostart).grid(row=1, column=0, sticky='ew')
        self.label(settings, '登录 Windows 后在后台运行', 11).grid(row=2, column=0, sticky='w', pady=(7, 23))
        self.switch(settings, '显示登录浏览器', self.show_browser).grid(row=3, column=0, sticky='ew')
        self.label(settings, '测试时查看校园网页面提示', 11).grid(row=4, column=0, sticky='w', pady=(7, 24))
        ctk.CTkFrame(settings, height=1, fg_color='#ECEEF1').grid(row=5, column=0, sticky='ew', pady=(0, 21))
        self.state_badge = ctk.CTkLabel(settings, text='等待配置', text_color=SECONDARY,
                                      fg_color='#EDF1F6', corner_radius=4, height=26, width=90, font=(FONT, 12))
        self.state_badge.grid(row=6, column=0, sticky='w')
        self.state_hint = self.label(settings, '填好账号后，点击下方按钮测试连接。', 12, wraplength=228, justify='left')
        self.state_hint.grid(row=7, column=0, sticky='w', pady=(10, 0))

        activity = ctk.CTkFrame(self, fg_color='transparent')
        activity.grid(row=2, column=0, sticky='ew', padx=30, pady=(15, 0))
        activity.grid_columnconfigure(0, weight=1)
        self.label(activity, '运行记录', 12, SECONDARY).grid(row=0, column=0, sticky='w')
        self.status = ctk.CTkTextbox(activity, height=68, fg_color='#EDF1F6', text_color=SECONDARY,
                                     font=(FONT, 12), wrap='word', border_width=1, border_color='#DBE1EA', corner_radius=6,
                                     scrollbar_button_color='#DADCE0', scrollbar_button_hover_color='#BDC1C6')
        self.status.grid(row=1, column=0, sticky='ew', pady=(4, 0))
        self.status.configure(state='disabled')

        footer = ctk.CTkFrame(self, fg_color='transparent')
        footer.grid(row=3, column=0, sticky='ew', padx=28, pady=(14, 20))
        footer.grid_columnconfigure(1, weight=1)
        self.clear_button = ctk.CTkButton(footer, text='清除配置', command=self.remove, height=40, width=90,
                        corner_radius=6, fg_color='transparent', text_color=SECONDARY,
                        hover_color='#EDF0F5', font=(FONT, 13))
        self.clear_button.grid(row=0, column=0, sticky='w')
        self.save_button = ctk.CTkButton(footer, text='保存设置', command=self.save, width=130, height=40,
                        corner_radius=8, fg_color=SURFACE, text_color=BLUE, border_width=1,
                        border_color=LINE, hover_color=PALE_BLUE, font=(FONT, 13))
        self.save_button.grid(row=0, column=2, padx=(0, 10))
        self.test_button = ctk.CTkButton(footer, text='保存并连接', command=self.test, width=130, height=40,
                        corner_radius=8, fg_color=BLUE, hover_color=BLUE_HOVER, text_color=SURFACE,
                        font=(FONT, 13))
        self.test_button.grid(row=0, column=3)

        if load_saved:
            try:
                old = api.load_account()
                if old:
                    self.username.set(old.get('username', ''))
                    self.password.set(old.get('password', ''))
                    self.operator.set(old.get('operator', ''))
                    self.set_state('就绪', '设置已载入，可以直接连接。')
            except Exception:
                self.messages.put('原配置无法解密，请重新填写账号密码。')
        self.messages.put('请先连接校园 Wi-Fi，或插入校园网网线。')
        self.bind('<Return>', lambda _: self.test())
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(250, self.style_native_frame)
        self._pump_job = self.after(120, self.pump)

    @staticmethod
    def label(parent, text, size=13, color=SECONDARY, **kwargs):
        return ctk.CTkLabel(parent, text=text, font=(FONT, size), text_color=color, anchor='w', **kwargs)

    @staticmethod
    def entry(parent, variable, placeholder=''):
        entry = ctk.CTkEntry(parent, textvariable=variable, placeholder_text=placeholder,
                            font=(FONT, 14), height=40, corner_radius=6, border_width=1,
                            border_color=LINE, fg_color=SURFACE, text_color=INK)
        entry.bind('<FocusIn>', lambda _: entry.configure(border_color=BLUE))
        entry.bind('<FocusOut>', lambda _: entry.configure(border_color=LINE))
        return entry

    @staticmethod
    def switch(parent, text, variable):
        return ctk.CTkSwitch(parent, text=text, variable=variable, font=(FONT, 13), text_color=INK,
                             switch_width=38, switch_height=22, progress_color=BLUE,
                             fg_color='#DADCE0', button_color=SURFACE, button_hover_color='#F1F3F4')

    def toggle_password(self):
        self.revealed = not self.revealed
        self.password_entry.configure(show='' if self.revealed else '●')
        self.reveal_button.configure(text='隐藏' if self.revealed else '显示')

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
        self.state_badge.configure(text=title, text_color=color, fg_color=background)
        self.state_hint.configure(text=hint)

    def log(self, message):
        self.messages.put(message)
        self.api.log_file(message)

    def read_fields(self):
        if not self.username.get().strip() or not self.password.get():
            raise ValueError('请填写账号和密码。')
        return dict(username=self.username.get().strip(), password=self.password.get(), operator=self.operator.get().strip())

    def save(self):
        if self.busy:
            return None
        try:
            account = self.read_fields()
            self.api.save_account(account)
            self.api.set_startup(self.autostart.get())
            self.log('设置已保存。' + ('开机自动连接已开启。' if self.autostart.get() else '开机自动连接已关闭。'))
            self.set_state('设置已保存', '下次登录 Windows 时自动连接。' if self.autostart.get() else '需要时可在这里手动连接。')
            return account
        except Exception as error:
            messagebox.showerror('未能保存', str(error), parent=self)

    def test(self):
        if self.busy:
            return
        account = self.save()
        if not account:
            return
        visible = self.show_browser.get()
        self.busy = True
        for button in (self.test_button, self.save_button, self.clear_button):
            button.configure(state='disabled')
        self.test_button.configure(text='正在连接…')
        self.set_state('正在连接', '正在检查网络，请稍候。')
        def worker():
            handle = None
            try:
                handle = self.api.exclusive_run()
                if handle is None:
                    raise RuntimeError('已有登录任务正在运行，请稍后重试。')
                connected = self.api.run_login(account, self.log, visible=visible)
                self.messages.put(('result', bool(connected)))
            except Exception as error:
                self.log(str(error) if isinstance(error, RuntimeError) else '操作失败，请关闭测试浏览器后重试。')
                self.messages.put(('result', False))
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
            if self.revealed:
                self.toggle_password()
            self.log('已清除本机账号密码，并关闭开机自动连接。')
            self.set_state('等待配置', '填写账号后可以重新连接。')
        except Exception:
            messagebox.showerror('未能清除', '配置暂时无法删除，请稍后重试。', parent=self)

    def pump(self):
        while True:
            try:
                item = self.messages.get_nowait()
            except queue.Empty:
                break
            if item is None:
                self.busy = False
                for button in (self.test_button, self.save_button, self.clear_button):
                    button.configure(state='normal')
                self.test_button.configure(text='保存并连接')
            elif isinstance(item, tuple):
                if item[1]:
                    self.set_state('已连接', '网络检测通过，详细结果见运行记录。', success=True)
                else:
                    self.set_state('连接未完成', '请查看运行记录，核对账号和运营商。', error=True)
            else:
                self.status.configure(state='normal')
                self.status.insert('end', time.strftime('%H:%M  ') + item + '\n')
                self.status.see('end')
                self.status.configure(state='disabled')
        self._pump_job = self.after(120, self.pump)

    def destroy(self):
        # Cancel pending Tcl callbacks before a second window is constructed in tests.
        for job in self.tk.call('after', 'info'):
            self.tk.call('after', 'cancel', job)
        self._pump_job = None
        super().destroy()

    def close(self):
        if self.busy:
            messagebox.showinfo('正在连接', '请等待连接结束后再关闭窗口。', parent=self)
        else:
            self.destroy()


def launch(api):
    CampusWindow(api).mainloop()
