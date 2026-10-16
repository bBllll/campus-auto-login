"""Main-thread motion primitives, reviewed with the local DeepSeek Harness."""
import ctypes
from ctypes import wintypes
import time
import tkinter as tk


def system_animations_enabled():
    enabled = wintypes.BOOL(True)
    try:
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
            return bool(enabled.value)
    except OSError:
        pass
    return True


def mix_color(start, end, amount):
    a = tuple(int(start[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(end[i:i + 2], 16) for i in (1, 3, 5))
    return '#' + ''.join(f'{round(x + (y - x) * amount):02X}' for x, y in zip(a, b))


class Motion:
    def __init__(self, root, reduced=None, clock=time.monotonic):
        self.root = root
        self.reduced = not system_animations_enabled() if reduced is None else reduced
        self.clock = clock
        self.jobs = {}
        self.closed = False

    def cancel(self, key):
        job = self.jobs.pop(key, None)
        if job and job['after'] is not None:
            try:
                self.root.after_cancel(job['after'])
            except tk.TclError:
                pass

    def animate(self, key, frame, duration=160, done=None):
        self.cancel(key)
        if self.closed:
            return
        started = self.clock()
        job = {'after': None, 'finish': lambda: (frame(1), done() if done else None)}
        self.jobs[key] = job
        def tick():
            if self.closed or self.jobs.get(key) is not job:
                return
            job['after'] = None
            raw = 1.0 if self.reduced or duration <= 0 else min(1, (self.clock() - started) * 1000 / duration)
            try:
                frame(1 - (1 - raw) ** 3)
            except tk.TclError:
                self.cancel(key)
                return
            # A frame is allowed to replace/cancel its own animation.
            if self.jobs.get(key) is not job or self.closed:
                return
            if raw >= 1:
                self.jobs.pop(key, None)
                if done:
                    done()
            else:
                job['after'] = self.root.after(16, tick)
        tick()

    def later(self, key, delay, callback):
        self.cancel(key)
        if self.closed:
            return
        job = {'after': None}
        self.jobs[key] = job
        def run():
            if self.closed or self.jobs.get(key) is not job:
                return
            self.jobs.pop(key, None)
            callback()
        job['after'] = self.root.after(delay, run)

    def color(self, widget, option, target, duration=160):
        key = ('color', str(widget), option)
        try:
            start = widget.cget(option)
            if not isinstance(start, str) or len(start) != 7 or not start.startswith('#'):
                self.cancel(key)
                widget.configure(**{option: target})
                return
            self.animate(key, lambda t: widget.configure(**{option: mix_color(start, target, t)}), duration)
        except tk.TclError:
            self.cancel(key)

    def shutdown(self):
        self.closed = True
        for key in list(self.jobs):
            self.cancel(key)

    def set_reduced(self, reduced):
        self.reduced = bool(reduced)
        if self.reduced:
            for key, job in list(self.jobs.items()):
                if job.get('finish'):
                    self.cancel(key)
                    try:
                        job['finish']()
                    except tk.TclError:
                        pass
