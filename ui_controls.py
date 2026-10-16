"""Motion-aware controls sharing the app's keyed animation scheduler."""
import tkinter as tk
import customtkinter as ctk
from ui_fx import mix_color

BLUE = '#1A73E8'
INK = '#202124'
WHITE = '#FFFFFF'
FONT = 'Microsoft YaHei UI'


class MotionButton(ctk.CTkButton):
    def __init__(self, parent, motion, **kwargs):
        self.motion = motion
        self.rest_color = kwargs.get('fg_color', WHITE)
        self.over_color = kwargs.pop('hover_color', '#E8F0FE')
        self.pressed_color = mix_color(self.over_color, INK, .1)
        self.inside = False
        self.keyboard_focus = False
        self.rest_border = kwargs.get('border_width', 0)
        super().__init__(parent, hover=False, **kwargs)
        tk.Frame.configure(self, takefocus=1)
        tk.Frame.bind(self, '<FocusIn>', self._focus_in, add='+')
        tk.Frame.bind(self, '<FocusOut>', self._focus_out, add='+')
        tk.Frame.bind(self, '<space>', self._key_click, add='+')
        tk.Frame.bind(self, '<Return>', self._key_click, add='+')

    def focus_set(self):
        tk.Frame.focus_set(self)

    def _focus_in(self, event=None):
        self.keyboard_focus = True
        self.configure(border_width=2, border_color='#8AB4F8')
        self._paint()

    def _focus_out(self, event=None):
        self.keyboard_focus = False
        self.configure(border_width=self.rest_border, border_color='#CAD2DE')
        self._paint()

    def _paint(self):
        if self.cget('state') == 'disabled':
            color = mix_color(self.rest_color, '#F4F6F9', .6)
        else:
            color = self.over_color if self.inside or self.keyboard_focus else self.rest_color
        self.motion.color(self, 'fg_color', color, 120)

    def _on_enter(self, event=None):
        self.inside = True
        self._paint()

    def _on_leave(self, event=None):
        self.inside = False
        self._paint()

    def _clicked(self, event=None):
        if self.cget('state') != 'disabled':
            self.motion.color(self, 'fg_color', self.pressed_color, 65)
            self.motion.later(('release', str(self)), 85, self._paint)
            if self._command:
                self._command()

    def _key_click(self, event=None):
        self._clicked()
        return 'break'

    def set_enabled(self, enabled):
        self.configure(state='normal' if enabled else 'disabled')
        self._paint()


class MotionSwitch(ctk.CTkFrame):
    def __init__(self, parent, motion, text, variable):
        super().__init__(parent, fg_color='#FFFFFF', corner_radius=6, height=30,
                         border_width=0, border_color='#8AB4F8')
        self.motion = motion
        self.variable = variable
        self.enabled = True
        self.position = float(bool(variable.get()))
        self.grid_columnconfigure(1, weight=1)
        self.track = ctk.CTkFrame(self, width=40, height=22, corner_radius=11,
                                fg_color='#DADCE0', border_width=0)
        self.track.grid(row=0, column=0, padx=(2, 12), pady=4)
        self.track.grid_propagate(False)
        self.knob = ctk.CTkFrame(self.track, width=16, height=16, corner_radius=8, fg_color=WHITE)
        self.text_label = ctk.CTkLabel(self, text=text, font=(FONT, 13), text_color=INK, anchor='w')
        self.text_label.grid(row=0, column=1, sticky='ew', padx=(0, 3))
        for widget in (self, self.track, self.knob, self.text_label):
            widget.bind('<Button-1>', self.toggle, add='+')
        tk.Frame.configure(self, takefocus=1)
        tk.Frame.bind(self, '<space>', self.toggle, add='+')
        tk.Frame.bind(self, '<Return>', self.toggle, add='+')
        tk.Frame.bind(self, '<FocusIn>', lambda _: self.configure(border_width=1), add='+')
        tk.Frame.bind(self, '<FocusOut>', lambda _: self.configure(border_width=0), add='+')
        self.trace = variable.trace_add('write', self._changed)
        self._frame(self.position)

    def _frame(self, position):
        self.position = position
        color = mix_color('#DADCE0', BLUE, position)
        if not self.enabled:
            color = mix_color(color, '#FFFFFF', .55)
        self.track.configure(fg_color=color)
        self.knob.place(x=3 + 18 * position, y=3)

    def _changed(self, *_):
        start = self.position
        end = float(bool(self.variable.get()))
        self.motion.animate(('switch', str(self)), lambda t: self._frame(start + (end - start) * t), 160)

    def toggle(self, event=None):
        if self.enabled:
            tk.Frame.focus_set(self)
            self.variable.set(not self.variable.get())
        return 'break'

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.text_label.configure(text_color=INK if enabled else '#9AA0A6')
        self._frame(self.position)

    def destroy(self):
        self.motion.cancel(('switch', str(self)))
        self.variable.trace_remove('write', self.trace)
        super().destroy()
