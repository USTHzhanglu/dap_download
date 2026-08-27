# coding: utf-8
import os
import tkinter as tk
import tkinter.ttk as ttk

from tksheet import Sheet
from pack_manager import BUILTIN_REF


class PackManagerDialog(tk.Toplevel):
    """Pack manager dialog: lists installed packs, allows removal.

    library: PackLibrary instance.
    on_removed: optional callable(removed_device_names) after each removal.
    """

    def __init__(self, master, library, on_removed=None, on_added=None, on_toggled=None):
        super().__init__(master)
        self.title('Pack Manager')
        self.transient(master)
        self.resizable(False, False)
        self.withdraw()
        self._library = library
        self.on_removed = on_removed
        self.on_added = on_added
        self.on_toggled = on_toggled
        self._hl_row = None

        self.cols = [('vendor', 'Vendor', 360), ('pack', 'Pack', 360),
                     ('version', 'Version', 160), ('status', 'Status', 120)]
        self._refresh()
        self._build_ui()

        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry('%dx%d+%d+%d' % (w, h,
            master.winfo_rootx() + (master.winfo_width() - w) // 2,
            master.winfo_rooty() + (master.winfo_height() - h) // 2))
        self.deiconify()
        self.grab_set()

    def _refresh(self):
        # Re-read installed packs; prepend the builtin pseudo-pack
        packs = self._library.list_packs()
        builtin = (BUILTIN_REF, 'pyocd', 'Builtin algorithms',
                   self._library.builtin_version(), self._library.builtin_enabled())
        self._list = [builtin] + packs

    def _build_ui(self):
        cols = self.cols

        btn_frame = tk.Frame(self)
        add_btn = ttk.Button(btn_frame, text='Add', width=10, command=self._add)
        toggle_btn = ttk.Button(btn_frame, text='Enable/Disable', width=14, command=self._toggle)
        remove_btn = ttk.Button(btn_frame, text='Remove', width=10, command=self._remove)
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

        h = max(360, 40 * max(1, len(self._list)) + 20)
        sheet = Sheet(mid, height=h, show_row_index=False, show_header=False,
                      auto_resize_columns=False, auto_resize_rows=False,
                      show_x_scrollbar=False, show_y_scrollbar=False,
                      column_drag_and_drop=False, row_drag_and_drop=False)
        sheet.enable_bindings('mousewheel', 'cell_select', 'row_select', 'single_select',
                             'select', 'deselect', 'arrowkeys', 'copy')
        sheet.set_options(font=('', 8, ''), empty_vertical=0,
                          table_selected_rows_bg='#cce4f7')
        sheet.default_row_height(36)
        self._fill(sheet, reset_cols=True)

        btn_frame.pack(side='bottom', fill='x', padx=(6, 3), pady='3p')
        remove_btn.pack(side='right', padx='3p', pady=0)
        toggle_btn.pack(side='right', padx='3p', pady=0)
        add_btn.pack(side='right', padx='3p', pady=0)
        sep_bottom = tk.Frame(self, height=1, bg='#c0c0c0')
        sep_bottom.pack(side='bottom', fill='x')
        mid.pack(fill='both', expand=True, side='top')
        head_frame.grid(row=0, column=0, sticky='ew')
        sheet.grid(row=2, column=0, sticky='nsew')

        self.sheet = sheet
        self.bind('<ButtonPress-1>', self._on_press)
        sheet.bind('<Double-Button-1>', self._on_double)

    def _fill(self, sheet, reset_cols=False):
        cols = self.cols
        data = [[v, p, ver, 'Enabled' if en else 'Disabled']
                for ref, v, p, ver, en in self._list]
        if not data:
            data = [['', '', '', '']]
        sheet.set_sheet_data(data, reset_col_positions=reset_cols, reset_row_positions=True)
        for i, (key, title, w) in enumerate(cols):
            sheet.column_width(i, w)

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

    def _remove(self):
        row = self._hl_row
        if row is None:
            sel = self.sheet.get_currently_selected()
            if sel and sel[0] is not None and 0 <= sel[0] < len(self._list):
                row = sel[0]
        if row is None or not (0 <= row < len(self._list)):
            return
        ref = self._list[row][0]
        if ref == BUILTIN_REF:
            # Builtin pseudo-pack cannot be removed
            return
        try:
            removed = self._library.remove(ref)
        except Exception as e:
            tk.messagebox.showwarning('Remove Pack', 'Failed to remove pack:\n%s' % e)
            return
        self._refresh()
        self._fill(self.sheet)
        self._hl_row = None
        if self.on_removed:
            self.on_removed(removed)

    def _on_double(self, event=None):
        row = self.sheet.identify_row(event)
        if row is None:
            return
        self._hl_row = row
        self._toggle()

    def _toggle(self):
        row = self._hl_row
        if row is None:
            sel = self.sheet.get_currently_selected()
            if sel and sel[0] is not None and 0 <= sel[0] < len(self._list):
                row = sel[0]
        if row is None or not (0 <= row < len(self._list)):
            return
        ref = self._list[row][0]
        try:
            if ref == BUILTIN_REF:
                enabled, dev_names = self._library.toggle_builtin_enabled()
            else:
                enabled, dev_names = self._library.toggle_enabled(ref)
        except Exception as e:
            tk.messagebox.showwarning('Toggle Pack', 'Failed to toggle pack:\n%s' % e)
            return
        self._refresh()
        self._fill(self.sheet)
        self._hl_row = None
        if self.on_toggled:
            self.on_toggled(ref, enabled, dev_names)

    def _add(self):
        try:
            from tkinter import filedialog
        except Exception:
            import tkinter.filedialog as filedialog
        paths = filedialog.askopenfilenames(title='Add pack files',
                                            filetypes=[('CMSIS Pack', '*.pack'), ('All files', '*.*')])
        if not paths:
            return
        successes = []
        failures = []
        for p in paths:
            try:
                ref, count, already = self._library.install(p)
                successes.append((ref, count, already))
            except Exception as e:
                failures.append((os.path.basename(p), str(e)))
        self._refresh()
        self._fill(self.sheet)
        self._hl_row = None
        for ref, count, already in successes:
            if self.on_added:
                self.on_added(ref, count, already)
        if failures:
            msg = 'Failed to add %d pack(s):\n' % len(failures)
            msg += '\n'.join('  %s: %s' % (n, e) for n, e in failures[:5])
            tk.messagebox.showwarning('Add Pack', msg)
