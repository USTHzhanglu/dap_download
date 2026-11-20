# coding: utf-8
"""Option-byte writer window: YAML flow + per-field program fragments."""

import os
import queue
import threading
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as messagebox

from .writer import (WriterError, WriterSpec, load_writer, run_action,
                     run_writer)

FONT = ('', 8)
FONT_BOLD = ('', 8, 'bold')
FONT_MONO = ('Consolas', 8)
COLUMNS = 2
HINT_IMPORT = ('Edit the generated descriptor to enable writing;\n'
               'Import loads a descriptor file from someone else.')
MIN_WIDTH = 720
MIN_HEIGHT = 480
WINDOW_WIDTH = 720


class OptionWriterDialog(tk.Toplevel):
    """Write option bytes using a writer YAML (flow + field fragments)."""

    def __init__(self, master, programmer, descriptor, spec=None,
                 template_created=''):
        super().__init__(master)
        self._template_created = template_created or ''
        self.title('Option Bytes - %s' % descriptor.device.lstrip('-_'))
        self.transient(master)
        self.withdraw()
        self._programmer = programmer
        self._descriptor = descriptor
        if spec is None:
            spec = WriterSpec(device=descriptor.device,
                              from_pack=descriptor.from_pack,
                              flow={}, fields={}, auto={})
        self._spec = spec
        self._can_write = bool(spec.fields)
        self._spec_mtime = self._file_mtime(spec.path)
        self._closed = False
        self._value_vars = {}
        self._choice_vars = {}
        self._initial_choices = {}
        self._widgets = {}
        self._initial = {}
        self._queue = queue.Queue()
        self._build_ui()
        self.update_idletasks()
        self.update_idletasks()
        w = WINDOW_WIDTH
        h = self._content_height()
        self.geometry('%dx%d+%d+%d' % (
            w, h,
            master.winfo_rootx() + (master.winfo_width() - w) // 2,
            master.winfo_rooty() + (master.winfo_height() - h) // 2))
        self.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.deiconify()
        self.grab_set()
        self.after(50, self._start_read)

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        fields = self._descriptor.fields or []
        by_register = {}
        for field in fields:
            by_register.setdefault(field['register'], []).append(field)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        probe = ttk.Combobox(self)
        self.update_idletasks()
        self._row_height = max(probe.winfo_reqheight(), 24) + 2
        probe.destroy()
        body = tk.Frame(self)
        body.grid(row=0, column=0, sticky='nsew', padx=6, pady=(6, 0))
        body.columnconfigure(0, weight=1)

        for register, items in by_register.items():
            section = ttk.Labelframe(body, text=register, padding=(6, 3))
            section.pack(fill='x', padx=1, pady=(0, 5))
            for column in range(COLUMNS):
                section.columnconfigure(column, weight=1, uniform='field')
            for index, field in enumerate(items):
                row, column = divmod(index, COLUMNS)
                cell = self._build_cell(section, field)
                cell.grid(row=row, column=column, sticky='ew',
                          padx=6, pady=2)

        if not self._can_write:
            hint = HINT_IMPORT
            if self._template_created:
                hint = ('A default descriptor template was created:\n%s\n'
                        % self._template_created) + HINT_IMPORT
            tk.Label(body, text=hint, font=FONT, fg='#666666', anchor='w',
                     justify='left',
                     wraplength=WINDOW_WIDTH - 30).pack(
                         fill='x', padx=3, pady=(0, 6))

        if getattr(self._spec, 'pack_mismatch', False):
            tk.Label(
                body,
                text=('Note: descriptor targets pack %s; installed pack is %s. '
                      'Verify the register layout before writing.'
                      % (self._spec.from_pack, self._descriptor.from_pack)),
                font=FONT, fg='#a05200', anchor='w', justify='left',
                wraplength=WINDOW_WIDTH - 30).pack(
                    fill='x', padx=3, pady=(0, 6))

        # Fixed AUTO actions: own section, max 4 per row, equal widths.
        self._action_btns = []
        if self._spec.auto:
            section = ttk.Labelframe(body, text='AUTO', padding=(6, 3))
            section.pack(fill='x', padx=1, pady=(0, 5))
            for column in range(4):
                section.columnconfigure(column, weight=1, uniform='auto')
            single = len(self._spec.auto) == 1
            for index, name in enumerate(self._spec.auto):
                label = str(name).replace('_', ' ').title()
                button = ttk.Button(
                    section, text=label, width=14 if single else 0,
                    command=lambda n=name: self._run_auto(n))
                button.grid(row=index // 4, column=index % 4,
                            sticky='w' if single else 'ew',
                            padx=3, pady=3)
                self._action_btns.append(button)

        ttk.Separator(self, orient='horizontal').grid(
            row=1, column=0, sticky='ew', padx=8, pady=(4, 0))
        footer = tk.Frame(self)
        footer.grid(row=2, column=0, sticky='ew', padx=10, pady=(4, 8))
        ttk.Button(footer, text='Close', width=8,
                   command=self._close).pack(side='right')
        self._apply_btn = ttk.Button(footer, text='Apply', width=8,
                                     command=self._apply, state='disabled')
        self._apply_btn.pack(side='right', padx=(0, 4))
        ttk.Button(footer, text='Read', width=8,
                   command=self._start_read).pack(side='right', padx=(0, 4))
        self._read_btn = footer.winfo_children()[-1]
        self._import_btn = ttk.Button(footer, text='Import...', width=11,
                                      command=self._load_yaml)
        self._import_btn.pack(side='left')
        self._import_btn.bind('<Enter>',
                              lambda e: self._tip(HINT_IMPORT))
        self._import_btn.bind('<Leave>', lambda e: self._untip())

    def _build_cell(self, parent, field):
        name = str(field.get('name', ''))
        width = int(field.get('width', 1))
        cell = tk.Frame(parent, height=self._row_height)
        cell.grid_propagate(False)
        cell.columnconfigure(1, weight=1)
        label = tk.Label(cell, text=name, font=FONT_BOLD, anchor='w')
        label.grid(row=0, column=0, sticky='w', padx=(0, 6))
        writable = name in self._spec.fields
        entry = self._spec.fields.get(name) or {}
        enum = entry.get('enum') or {} if writable else {}
        if enum:
            var = tk.StringVar(value=next(iter(enum)))
            widget = ttk.Combobox(cell, textvariable=var, state='readonly',
                                  width=12, values=list(enum.keys()))
            self._choice_vars[name] = var
        elif width == 1:
            var = tk.IntVar(value=0)
            widget = ttk.Checkbutton(cell, variable=var)
        else:
            var = tk.StringVar(value='-')
            widget = ttk.Entry(cell, textvariable=var, width=10, font=FONT_MONO)
        if enum:
            self._widgets[name] = widget
        elif not writable:
            widget.configure(state='disabled')
        widget.grid(row=0, column=1, sticky='e')
        if not enum:
            self._value_vars[name] = (var, width)
        self._widgets[name] = widget
        if field.get('desc'):
            widget.bind('<Enter>', lambda e, text=str(field['desc']): self._tip(text))
            widget.bind('<Leave>', lambda e: self._untip())
        return cell

    def _tip(self, text):
        self._tip_win = tk.Toplevel(self)
        self._tip_win.wm_overrideredirect(True)
        x = self.winfo_pointerx() + 12
        y = self.winfo_pointery() + 8
        self._tip_win.wm_geometry('+%d+%d' % (x, y))
        tk.Label(self._tip_win, text=text, font=FONT, background='#ffffe0',
                 relief='solid', borderwidth=1, padx=3, pady=1).pack()

    def _untip(self):
        win = getattr(self, '_tip_win', None)
        if win is not None:
            win.destroy()
            self._tip_win = None

    # ---------------------------------------------------------------- read
    def _set_busy(self, busy):
        state = 'disabled' if busy else 'normal'
        self._read_btn.configure(state=state)
        for btn in self._action_btns:
            btn.configure(state=state)
        if busy or not self._can_write:
            self._apply_btn.configure(state='disabled')
        else:
            self._apply_btn.configure(state='normal')

    @staticmethod
    def _file_mtime(path):
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0.0

    def _reload_spec(self):
        """Reload the current YAML if the user edited it on disk."""
        path = getattr(self._spec, 'path', '')
        mtime = self._file_mtime(path)
        if not path or not mtime or mtime == self._spec_mtime:
            return False
        spec = load_writer(path)
        if not spec.valid:
            return False
        if not spec.matches(self._descriptor):
            if not spec.matches_family(self._descriptor):
                return False
            spec.pack_mismatch = True
        self._spec = spec
        self._can_write = bool(spec.fields)
        self._spec_mtime = mtime
        self._template_created = ''
        self._rebuild_ui()
        return True

    def _start_read(self):
        if self._closed:
            return
        self._reload_spec()
        self._set_busy(True)
        threading.Thread(target=self._read_worker, daemon=True).start()
        self._poll()

    def _read_worker(self):
        try:
            if self._programmer.session is None:
                self._programmer.open()
            values, _regs = self._programmer.read(self._descriptor)
        except Exception as exc:
            self._queue.put(('read_err', str(exc)))
            return
        self._queue.put(('read_ok', values))

    def _poll(self):
        if self._closed:
            return
        try:
            kind, payload = self._queue.get_nowait()
        except queue.Empty:
            self.after(50, self._poll)
            return
        if kind == 'read_ok':
            self._read_done(payload)
        elif kind == 'write_ok':
            self._write_done(payload)
        elif kind == 'action_ok':
            self._action_done(payload)
        elif kind == 'write_err' or kind == 'action_err':
            self._write_failed(payload)
        elif kind == 'error':
            self._read_failed(payload)
        else:
            self._read_failed(payload)

    def _apply_values(self, values):
        for name, (var, width) in self._value_vars.items():
            value = int(values.get(name, 0))
            if width == 1:
                var.set(1 if value else 0)
            else:
                var.set('0x%X' % value)

    def _read_done(self, values):
        if self._closed:
            return
        self._apply_values(values)
        self._initial = dict(values)
        self._initial_choices = {}
        for name, var in self._choice_vars.items():
            choice = self._spec.choice_for(name, values)
            if not choice:
                enum = (self._spec.fields.get(name) or {}).get('enum') or {}
                choice = next(iter(enum)) if enum else ''
            if choice:
                var.set(choice)
                self._initial_choices[name] = choice
        self._set_busy(False)

    def _read_failed(self, message):
        if self._closed:
            return
        self._set_busy(False)
        messagebox.showwarning('Option Bytes', message, parent=self)

    # ---------------------------------------------------------------- load YAML
    def _load_yaml(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=self, title='Load option-byte YAML',
            filetypes=[('Option byte YAML', '*.yaml *.yml'),
                       ('All files', '*.*')])
        if path:
            self._import_path(path)

    def _import_path(self, path, start_read=True):
        from .writer import install_writer
        try:
            spec = install_writer(path, self._descriptor)
        except Exception as exc:
            messagebox.showwarning('Option Bytes', str(exc), parent=self)
            return
        self._spec = spec
        self._can_write = bool(spec.fields)
        self._spec_mtime = self._file_mtime(spec.path)
        self._template_created = ''
        self._rebuild_ui()
        if start_read:
            self._start_read()

    def _content_height(self):
        height = max(MIN_HEIGHT, self.winfo_reqheight())
        try:
            screen = self.winfo_screenheight()
            height = min(height, int(screen * 0.8))
        except Exception:
            pass
        return height

    def _rebuild_ui(self):
        for child in self.winfo_children():
            child.destroy()
        self._value_vars = {}
        self._choice_vars = {}
        self._initial_choices = {}
        self._widgets = {}
        self._initial = {}
        self._action_btns = []
        self._build_ui()
        self.update_idletasks()
        width = max(MIN_WIDTH, self.winfo_width())
        self.geometry('%dx%d' % (width, self._content_height()))

    # ---------------------------------------------------------------- write
    def _collect(self):
        values = dict(self._initial)
        changed = []
        for name, (var, width) in self._value_vars.items():
            if width == 1:
                value = int(var.get())
            else:
                text = str(var.get()).strip()
                try:
                    value = int(text, 0)
                except ValueError:
                    raise ValueError('Invalid value for field %s: %s' % (name, text))
            values[name] = value
            if name in self._spec.fields and value != int(self._initial.get(name, -1)):
                changed.append(name)
        choices = {}
        for name, var in self._choice_vars.items():
            choice = var.get()
            choices[name] = choice
            if choice != self._initial_choices.get(name):
                changed.append(name)
        return values, choices, changed

    def _apply(self):
        if self._reload_spec():
            self._start_read()
            return
        if not self._can_write:
            return
        try:
            values, choices, changed = self._collect()
        except ValueError as exc:
            messagebox.showwarning('Option Bytes', str(exc), parent=self)
            return
        if not changed:
            messagebox.showinfo('Option Bytes', 'No writable option byte was changed.',
                                parent=self)
            return
        warnings = []
        for name, choice in choices.items():
            warn = (self._spec.fields.get(name) or {}).get(
                'warning', {}).get(choice)
            if warn:
                warnings.append(str(warn))
        if warnings:
            if not messagebox.askyesno('Option Bytes',
                                       '\n\n'.join(warnings), parent=self):
                return
        if not self._spec.verified:
            if not messagebox.askyesno(
                    'Option Bytes',
                    'This write sequence is not verified and may brick the chip.\n\nContinue writing %d field(s)?'
                    % len(changed), parent=self):
                return
        else:
            if not messagebox.askyesno(
                    'Option Bytes',
                    'Write %d option byte field(s)?' % len(changed), parent=self):
                return
        self._set_busy(True)
        threading.Thread(target=self._write_worker,
                         args=(values, changed, choices), daemon=True).start()
        self._poll()

    def _write_worker(self, values, changed, choices):
        try:
            result = run_writer(self._programmer, self._spec,
                                self._descriptor, values, changed,
                                choices=choices)
        except Exception as exc:
            self._queue.put(('write_err', str(exc)))
            return
        self._queue.put(('write_ok', result))

    def _write_done(self, result):
        if self._closed:
            return
        new_values = result.get('values') or {}
        self._apply_values(new_values)
        self._initial = dict(new_values)
        self._initial_choices = {}
        for name, var in self._choice_vars.items():
            choice = self._spec.choice_for(name, new_values)
            if choice:
                var.set(choice)
                self._initial_choices[name] = choice
        self._set_busy(False)
        lines = []
        for name, (wanted, got) in (result.get('mismatches') or {}).items():
            lines.append('%s: wrote 0x%X, read 0x%X' % (name, wanted, got))
        for name, (wanted, got) in (result.get('choice_mismatches') or {}).items():
            lines.append('%s: chose %s, read %s' % (name, wanted, got))
        if lines:
            messagebox.showwarning('Option Bytes',
                                   'Written, but read-back mismatch:\n' + '\n'.join(lines),
                                   parent=self)
        else:
            messagebox.showinfo('Option Bytes', 'Write complete; read-back matches.',
                                parent=self)

    def _write_failed(self, message):
        if self._closed:
            return
        self._set_busy(False)
        messagebox.showwarning('Option Bytes', message, parent=self)

    # ---------------------------------------------------------------- AUTO actions
    def _run_auto(self, name):
        label = str(name).replace('_', ' ').title()
        if not messagebox.askyesno(
                'Option Bytes', 'Run AUTO action: %s?' % label, parent=self):
            return
        self._set_busy(True)
        threading.Thread(target=self._action_worker, args=(name,),
                         daemon=True).start()
        self._poll()

    def _action_worker(self, name):
        try:
            if self._programmer.session is None:
                self._programmer.open()
            run_action(self._programmer, self._spec, self._descriptor, name)
        except Exception as exc:
            self._queue.put(('action_err', str(exc)))
            return
        self._queue.put(('action_ok', name))

    def _action_done(self, name):
        if self._closed:
            return
        self._set_busy(False)
        label = str(name).replace('_', ' ').title()
        messagebox.showinfo('Option Bytes', '%s completed; values reloaded.' % label,
                            parent=self)
        self._start_read()

    # ---------------------------------------------------------------- close
    def _close(self):
        self.destroy()

    def _on_destroy(self, event):
        if event.widget is not self:
            return
        self._closed = True
        try:
            self._programmer.close()
        except Exception:
            pass
        try:
            self.grab_release()
        except tk.TclError:
            pass

    def destroy(self):
        try:
            self._programmer.close()
        except Exception:
            pass
        super().destroy()
