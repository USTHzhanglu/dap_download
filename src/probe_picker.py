# coding: utf-8
import tkinter as tk
import tkinter.ttk as ttk

from tksheet import Sheet


class ProbePickerDialog(tk.Toplevel):
    """Probe selection dialog: same style as TargetPickerDialog, columns Probe/Board | Unique ID.

    items: list[(board, unique_id)]
    """

    def __init__(self, master, items, on_pick):
        super().__init__(master)
        self.title('Select Probe')
        self.transient(master)
        self.resizable(False, False)
        self.withdraw()
        self._items = items
        self.on_pick = on_pick
        self._hl_row = None

        self.cols = [('board', 'Probe', 360), ('uid', 'Unique ID', 360)]
        self._build_ui()
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry('%dx%d+%d+%d' % (w, h,
            master.winfo_rootx() + (master.winfo_width() - w) // 2,
            master.winfo_rooty() + (master.winfo_height() - h) // 2))
        self.deiconify()
        self.grab_set()

    def _build_ui(self):
        cols = self.cols

        btn_frame = tk.Frame(self)
        ok_btn = ttk.Button(btn_frame, text='OK', width=10)
        cancel_btn = ttk.Button(btn_frame, text='Cancel', width=10)
        mid = tk.Frame(self, bg='white')
        head_frame = tk.Frame(mid, bg='white')
        for i, (key, title, w) in enumerate(cols):
            c = i * 2
            lw = w if i == len(cols) - 1 else w - 1
            head_frame.columnconfigure(c, minsize=lw)
            tk.Label(head_frame, text=title, anchor='w').grid(row=0, column=c, sticky='ew')
            if i < len(cols) - 1:
                head_frame.columnconfigure(c + 1, minsize=1)
                tk.Frame(head_frame, width=1, bg='#e1e1e1').grid(row=0, column=c + 1, sticky='ns')

        sheet = Sheet(mid, height=max(360, 40 * len(self._items) + 20), show_row_index=False,
                      show_header=False, auto_resize_columns=False, auto_resize_rows=False,
                      show_x_scrollbar=False, show_y_scrollbar=False,
                      column_drag_and_drop=False, row_drag_and_drop=False)
        sheet.enable_bindings('mousewheel', 'cell_select', 'row_select', 'single_select',
                             'select', 'deselect', 'arrowkeys', 'copy')
        sheet.set_options(empty_vertical=0, table_selected_rows_bg='#cce4f7')
        data = [[b, u] for b, u in self._items]
        if not data:
            data = [['', '']]
        sheet.set_sheet_data(data, reset_col_positions=True, reset_row_positions=True)
        for i, (key, title, w) in enumerate(cols):
            sheet.column_width(i, w)

        btn_frame.pack(side='bottom', fill='x', padx=(6, 3), pady='3p')
        ok_btn.pack(side='right', padx='3p', pady=0)
        cancel_btn.pack(side='right', padx='3p', pady=0)
        sep_bottom = tk.Frame(self, height=1, bg='#c0c0c0')
        sep_bottom.pack(side='bottom', fill='x')
        mid.pack(fill='both', expand=True, side='top')
        head_frame.grid(row=0, column=0, sticky='ew')
        sheet.grid(row=2, column=0, sticky='nsew')

        self.sheet = sheet

        ok_btn.configure(command=self._pick)
        cancel_btn.configure(command=self.destroy)
        sheet.bind('<Double-Button-1>', lambda e: self._pick())
        self.bind('<ButtonPress-1>', self._on_press)

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

    def _pick(self):
        row = self._hl_row
        if row is None:
            sel = self.sheet.get_currently_selected()
            if sel and sel[0] is not None and 0 <= sel[0] < len(self._items):
                row = sel[0]
        if row is not None and 0 <= row < len(self._items):
            board, uid = self._items[row]
            self.on_pick(board, uid)
        self.destroy()
