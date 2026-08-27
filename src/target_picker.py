# coding: utf-8
import tkinter as tk
import tkinter.ttk as ttk

from tksheet import Sheet


class TargetPickerDialog(tk.Toplevel):
    """Target selection dialog: fixed size, scrollbar shown as needed."""

    def __init__(self, master, rows, on_pick):
        super().__init__(master)
        self.rows = rows
        self.on_pick = on_pick
        self._sheet_names = []
        self._hl_row = None
        self._filter_after = None

        self.cols = [('vendor', 'Manufacturer', 240), ('device', 'Device', 360), ('flash', 'Flash Size', 240)]

        self.title('Target Device Settings')
        self.transient(master)
        self.resizable(False, False)
        self.withdraw()

        self._build_ui()

        self._apply_target_filter(first=True)
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry('%dx%d+%d+%d' % (w, h,
            master.winfo_rootx() + (master.winfo_width() - w) // 2,
            master.winfo_rooty() + (master.winfo_height() - h) // 2))
        self.deiconify()
        self.gutter()
        self.grab_set()
        self.focus_set()

    def _build_ui(self):
        cols = self.cols

        btn_frame = tk.Frame(self)
        ok_btn = ttk.Button(btn_frame, text='OK', width=10)
        cancel_btn = ttk.Button(btn_frame, text='Cancel', width=10)
        mid = tk.Frame(self, bg='white')
        head_frame = tk.Frame(mid, bg='white')
        filter_frame = tk.Frame(mid, bg='white')
        self.entries = {}
        for i, (key, title, w) in enumerate(cols):
            c = i * 2
            lw = w if i == len(cols) - 1 else w - 1
            head_frame.columnconfigure(c, minsize=lw)
            tk.Label(head_frame, text=title, anchor='w', bg='white').grid(row=0, column=c, sticky='ew')
            if i < len(cols) - 1:
                head_frame.columnconfigure(c + 1, minsize=1)
                tk.Frame(head_frame, width=1, bg='#e1e1e1').grid(row=0, column=c + 1, sticky='ns')
            filter_frame.columnconfigure(i, minsize=w)
            e = tk.Entry(filter_frame, width=8)
            e.grid(row=0, column=i, sticky='ew')
            self.entries[key] = e

        sheet = Sheet(mid, height=720, show_row_index=False, show_header=False,
                      auto_resize_columns=False, auto_resize_rows=False,
                      show_x_scrollbar=False, show_y_scrollbar=False,
                      column_drag_and_drop=False, row_drag_and_drop=False)
        sheet.enable_bindings('mousewheel', 'cell_select', 'row_select', 'single_select',
                             'select', 'deselect', 'arrowkeys', 'copy')
        sheet.set_options(font=('', 8 , ''), empty_vertical=0,
                          table_selected_rows_bg='#cce4f7')
        sheet.default_row_height(36)

        mid.columnconfigure(0, weight=1)
        mid.columnconfigure(1, minsize=20)
        mid.rowconfigure(4, weight=1)

        sep_top = tk.Frame(self, height=1, bg='#e1e1e1')
        sep_top.pack(side='top', fill='x', padx=(6, 0))
        btn_frame.pack(side='bottom', fill='x', padx=(6, 3), pady='3p')
        ok_btn.pack(side='right', padx='3p', pady=0)
        cancel_btn.pack(side='right', padx='3p', pady=0)
        sep_bottom = tk.Frame(self, height=1, bg='#c0c0c0')
        sep_bottom.pack(side='bottom', fill='x', padx=(6, 0))
        mid.pack(fill='both', expand=True, side='top', padx=(6, 0), pady=(4, '4p'))
        sep1 = tk.Frame(mid, height=1, bg='#e1e1e1')
        sep2 = tk.Frame(mid, height=1, bg='#e1e1e1')
        head_frame.grid(row=0, column=0, sticky='ew')
        sep1.grid(row=1, column=0, sticky='ew')
        filter_frame.grid(row=2, column=0, sticky='ew')
        sep2.grid(row=3, column=0, sticky='ew')
        sheet.grid(row=4, column=0, sticky='nsew')

        ext_sb = tk.Scrollbar(mid, orient='vertical', command=sheet.MT._yscrollbar, width="12p")
        sheet.MT.configure(yscrollcommand=ext_sb.set)
        ext_sb.grid(row=0, column=1, rowspan=5, sticky='ns')

        self.sheet = sheet
        self.head_frame = head_frame
        self.filter_frame = filter_frame
        self.ext_sb = ext_sb
        self.mid = mid

        ok_btn.configure(command=self._pick)
        cancel_btn.configure(command=self._cancel)
        for e in self.entries.values():
            e.bind('<KeyRelease>', self._filter)
        sheet.bind('<Double-Button-1>', self._pick)
        self.bind('<ButtonPress-1>', self._on_press)
        self.protocol('WM_DELETE_WINDOW', self._cancel)

    def gutter(self):
        self.update_idletasks()

    def _filter(self, event=None):
        if self._filter_after:
            self.after_cancel(self._filter_after)
        self._filter_after = self.after(50, self._apply_target_filter)

    def _close(self):
        if self._filter_after:
            self.after_cancel(self._filter_after)
        self.destroy()

    def _pick(self, event=None):
        row = self._hl_row
        if row is None:
            sel = self.sheet.get_currently_selected()
            if sel and sel[0] is not None and 0 <= sel[0] < len(self._sheet_names):
                row = sel[0]
        if row is not None and 0 <= row < len(self._sheet_names):
            self.on_pick(self._sheet_names[row])
            self._close()

    def _cancel(self):
        self._close()

    def _gray(self):
        self.sheet.deselect()
        prev = self._hl_row
        if prev is not None:
            self.sheet.dehighlight_all()
            self.sheet.highlight_rows(prev, bg='#e6e6e6')

    def _on_press(self, event=None):
        w = event.widget
        tw = w
        is_sheet = False
        while tw is not None:
            if tw is self.sheet:
                is_sheet = True
                break
            tw = getattr(tw, 'master', None)
        if is_sheet:
            row = self.sheet.identify_row(event)
            if row is not None:
                self.sheet.dehighlight_all()
                self.sheet.highlight_rows(row, bg='#cce4f7')
                self._hl_row = row
            else:
                self._gray()
        else:
            self._gray()

    def _apply_target_filter(self, first=False):
        kws = {k: e.get().strip().lower() for k, e in self.entries.items()}
        widths = {k: w for k, t, w in self.cols}
        data, names = [], []
        for name, vendor, part, flash in self.rows:
            if (kws['vendor'] in vendor.lower() and kws['device'] in part.lower()
                    and kws['flash'] in flash.lower()):
                data.append([
                    self._fit_cell(vendor, widths['vendor']),
                    self._fit_cell(part, widths['device']),
                    self._fit_cell(flash, widths['flash'])])
                names.append(name)
        if not data:
            # Placeholder row so columns keep valid indexes for column_width
            data = [['', '', '']]
        self.sheet.set_sheet_data(data, reset_col_positions=first, reset_row_positions=True)
        for i, (k, t, w) in enumerate(self.cols):
            self.sheet.column_width(i, w)
        self._sheet_names = names
        self.gutter()

    def _fit_cell(self, text, width):
        import tkinter.font as tkfont
        if not hasattr(self, '_cell_font'):
            self._cell_font = tkfont.Font(family='Segoe UI', size=9)
        f = self._cell_font
        s = str(text)
        if f.measure(s) <= width:
            return s
        lo, hi = 0, len(s)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if f.measure(s[:mid] + '...') <= width:
                lo = mid
            else:
                hi = mid - 1
        return s[:lo] + '...' if lo > 0 else '...'
