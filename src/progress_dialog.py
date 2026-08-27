# coding: utf-8
"""Standalone progress dialog for flash/erase (J-Flash style, simplified).

Single green bar + elapsed time on the right, no extra buttons, same width as the
main window. Closes automatically on success/failure; the result is shown in the
main LOG area.
"""

import time
import tkinter as tk

_BAR_COLOR = '#4CAF50'


class ProgressDialog(tk.Toplevel):
    def __init__(self, master, title='Programming', op_text='Program:'):
        super().__init__(master)
        self.title(title)
        self.transient(master)
        self.resizable(False, False)
        self.withdraw()
        self._finished = False
        self._start = time.time()
        self._op_text = op_text

        w = master.winfo_width() or 480
        self._build_ui()
        self.update_idletasks()
        h = self.winfo_reqheight()
        self.geometry('%dx%d+%d+%d' % (w, h,
            master.winfo_rootx() + (master.winfo_width() - w) // 2,
            master.winfo_rooty() + (master.winfo_height() - h) // 2))
        self.deiconify()
        self.grab_set()
        self.update_idletasks()
        self._draw(0.0)

    def _build_ui(self):
        body = tk.Frame(self)
        body.pack(fill='both', expand=True)
        body.columnconfigure(1, weight=1)  # bar column expands with the window
        self.op_lbl = tk.Label(body, text=self._op_text, font=('Segoe UI', 8))
        self.op_lbl.grid(row=0, column=0, padx=(20, 12), pady=24, sticky='w')
        self.canvas = tk.Canvas(body, height=34, bg='#f5f5f5', highlightthickness=0)
        self.canvas.grid(row=0, column=1, sticky='ew', padx=(0, 12), pady=24)
        self.info_lbl = tk.Label(body, text='00:00.000', font=('Segoe UI', 8), anchor='e')
        self.info_lbl.grid(row=0, column=2, padx=(0, 20), pady=24, sticky='e')
        self.protocol('WM_DELETE_WINDOW', self._on_close)

    def set_op(self, text):
        self.op_lbl.configure(text=text)

    def set_progress(self, frac, state, msg=''):
        self._finished = state in ('ok', 'fail')
        if state == 'fail':
            frac = 1.0
        self._draw(frac)
        # Show elapsed time (mm:ss.mmm) on the right
        elapsed = time.time() - self._start
        self.info_lbl.configure(text=self._fmt_time(elapsed), fg='#000000')
        if state == 'ok':
            self.after(700, self.destroy)
        elif state == 'fail':
            self.after(1200, self.destroy)

    @staticmethod
    def _fmt_time(seconds):
        seconds = max(0, seconds)
        m, rem = divmod(seconds, 60)
        s = int(rem)
        ms = int(round((rem - s) * 1000))
        if ms >= 1000:
            ms -= 1000
            s += 1
        return '%02d:%02d.%03d' % (int(m), s, ms)

    def _on_close(self):
        # Cannot close while an op runs; closes itself when finished
        if self._finished:
            self.destroy()

    def _draw(self, frac):
        c = self.canvas
        w = c.winfo_width() or 1
        h = c.winfo_height() or 1
        c.delete('all')
        c.create_rectangle(0, 0, w, h, fill='#e8e8e8', outline='')
        frac = min(1.0, max(0.0, frac))
        fw = int(w * frac)
        if fw > 0:
            c.create_rectangle(0, 0, fw, h, fill=_BAR_COLOR, outline='')
        # Percent in the bar centre; contrast adapts to progress
        text = '%d%%' % int(frac * 100)
        font = ('Segoe UI', 9)
        if fw >= w / 2:
            fg, shadow = '#ffffff', '#000000'  # on bar: white text, dark shadow
        else:
            fg, shadow = '#404040', '#ffffff'  # on track: dark text, white shadow
        c.create_text(w / 2 + 1, h / 2 + 1, text=text, fill=shadow, font=font)
        c.create_text(w / 2, h / 2, text=text, fill=fg, font=font)
