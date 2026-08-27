#!/usr/bin/env python
# coding: utf-8

import ctypes
import sys
import threading
import webbrowser

import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox

from core import Flasher
from version import __appname__, __version__, __author__, __copyright__
from pack_manager import PackLibrary
from tksheet import Sheet
from target_picker import TargetPickerDialog
from probe_picker import ProbePickerDialog

show_about = (
__appname__+'\r\n\r\n'+
'Version:%s\r\n'%__version__+
'Author:%s\r\n'%__author__+
'Copyright@%s'%__copyright__
)

DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


def _enable_dpi_awareness():
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def dpi_scale():
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
    except Exception:
        dpi = 96
    return max(1.0, dpi / 96)




class PyocdApp:
    def __init__(self, master=None):
        _enable_dpi_awareness()
        self._flasher = Flasher(log=self._append_log, progress=self._on_progress,
                                done=self._on_done)
        self._library = PackLibrary()
        self._dialog_open = False
        self._current_dialog = None
        self._progress_dlg = None
        self._progress_creating = False
        self._progress_active = False
        self._progress_pending = None
        self._op_title = 'Operation'

        self.toplevel1 = tk.Tk() if master is None else tk.Toplevel(master)
        self.toplevel1.withdraw()
        self._install_unraisable_hook()
        _style = ttk.Style(self.toplevel1)
        _style.configure('TEntry', padding=(0, 0))
        self.menu1 = tk.Menu(self.toplevel1, tearoff=True)

        # Pack Manager first; each item binds its own command to avoid index drift
        self.menu1.add_command(label='Pack Manager', command=self._open_pack_manager)
        self.menu1.add_command(label='Help', command=lambda: self.menucallback('help'))
        self.menu1.add_command(label='About', command=lambda: self.menucallback('about'))
        self.toplevel1.configure(menu=self.menu1)
        
        
        self.gui = ttk.Frame(self.toplevel1)

        self.target_frame = tk.Frame(self.gui)
        self.target_frame.columnconfigure(0, weight=2)
        self.target_frame.columnconfigure(1, weight=2)
        self.target_frame.columnconfigure(2, weight=1)
        self.target_frame.columnconfigure(3, weight=1)
        self.target_frame.pack(fill='x', side='top', padx='3p', pady='2p')

        self.probe_group = ttk.Labelframe(self.target_frame, text='Probe')
        self.probe_group.grid(row=0, column=0, sticky='nsew')
        self.probe_entry = ttk.Combobox(self.probe_group, state='readonly', width=10)
        self.probe_entry.pack(fill='x', expand=True)
        self.probe_entry.bind('<Button-1>', self._open_probe_picker)

        self.dev_group = ttk.Labelframe(self.target_frame, text='Target')
        self.dev_group.grid(row=0, column=1, sticky='nsew')
        self.target_btn = ttk.Combobox(self.dev_group, state='readonly', width=12)
        self.target_btn.set('Not Select')
        self.target_btn.pack(fill='x', expand=True)
        self.target_btn.bind('<Button-1>', self._on_device_click, add='+')
        self._selected_target = None

        self.iface_group = ttk.Labelframe(self.target_frame, text='Interface')
        self.iface_group.grid(row=0, column=2, sticky='nsew')
        self.interface_entry = ttk.Combobox(self.iface_group, state='readonly', values=['SWD','JTAG'], width=6)
        self.interface_entry.set('SWD')
        self.interface_entry.pack(fill='x', expand=True)

        self.speed_group = ttk.Labelframe(self.target_frame, text='Speed')
        self.speed_group.grid(row=0, column=3, sticky='nsew')
        self.speed_entry = ttk.Combobox(self.speed_group, width=6, values=['1000 kHz', '2000 kHz', '4000 kHz', '8000 kHz'])
        self.speed_entry.set('4000 kHz')
        self.speed_entry.pack(fill='x', expand=True)

        self.data_group = ttk.Labelframe(self.gui, text='Data File (bin / hex / mot / srec / ...)')
        self.data_group.columnconfigure(0, weight=1)
        self.data_group.columnconfigure(1, minsize=0)
        self.bin_frame = ttk.Frame(self.data_group)
        self.bin_frame.grid(row=0, column=0, sticky='ew')
        self.bin_frame.columnconfigure(0, weight=1)
        self.bin_entry = ttk.Entry(self.bin_frame)
        self.bin_entry.grid(row=0, column=0, sticky='ew')
        self.bin_browse_btn = ttk.Button(self.bin_frame, text='...', width=4, command=self._browse_bin)
        self.bin_browse_btn.grid(row=0, column=1, padx='1p')
        self.bin_addr_lbl = ttk.Label(self.bin_frame, text='@')
        self.bin_addr_lbl.grid(row=0, column=2, padx=('1p', 0))
        self.bin_addr_entry = ttk.Entry(self.bin_frame, width=12)
        self.bin_addr_entry.grid(row=0, column=3, padx='1p')
        # Hidden until a .bin file is selected
        self.bin_addr_lbl.grid_remove()
        self.bin_addr_entry.grid_remove()

        self.erase = ttk.Button(self.data_group, text='Erase Chip', command=self.erasechip)
        self.erase.grid(row=0, column=1, sticky='', padx='1p', pady='1p')

        self.data_group.pack(fill='x', side='top', padx='3p', pady='2p')

        self.start = ttk.Button(self.gui, text='Program Device', command=self.download)
        self.start.pack(fill='x', padx='3p', pady='2p')

        self.log_group = ttk.Labelframe(self.gui, text='Log')
        self.log_group.pack(fill='both', expand=True, side='top', padx='3p', pady=(0, '2p'))
        self.out = tk.Text(self.log_group, undo=True, maxundo=1)
        self.out.configure(font=('', 8))
        self.out.pack(fill='both', expand=True, side='top')
        self._log_buffer = []
        self._log_after = None

        self.gui.pack(fill='both', expand=True, side='top')
        self._refresh_probes()
        self.toplevel1.update_idletasks()
        scale = dpi_scale()
        w, h = int(480 * scale), int(320 * scale)
        self.toplevel1.geometry('%dx%d+%d+%d' % (
            w, h,
            (self.toplevel1.winfo_screenwidth() - w) // 2,
            (self.toplevel1.winfo_screenheight() - h) // 2 - 18))
        self.toplevel1.minsize(w, h)
        self.toplevel1.maxsize(w, h)
        self.toplevel1.deiconify()

        self.toplevel1.title(__appname__)
        self.toplevel1.resizable(False, False)
        self.toplevel1.attributes('-alpha',0.95)        
        
        import windnd
        windnd.hook_dropfiles(self.toplevel1, func=self._on_drop_files)
        self.mainwindow = self.toplevel1
        self.mainwindow.attributes('-topmost', 1)  # force foreground
        self.mainwindow.after_idle(self.mainwindow.attributes,'-topmost',False)
        self.mainwindow.focus_force()

    
    def run(self):
        self.mainwindow.mainloop()

    def _install_unraisable_hook(self):
        # Catch unraisable errors: a RecursionError inside a ctypes callback (e.g. JLink
        # DLL logs) is only printed to stderr, never reaching the normal exception flow.
        # React promptly so the progress dialog fails instead of waiting for done.
        orig = sys.unraisablehook
        app = self

        def hook(args, _orig=orig):
            try:
                if args.exc_type is RecursionError:
                    app.toplevel1.after(0, lambda a=args: app._on_recursion_error(str(a.exc_value)))
                elif _orig is not None:
                    _orig(args)
            except Exception:
                pass

        sys.unraisablehook = hook

    def _on_recursion_error(self, msg):
        try:
            # Log only, do not touch the dialog: such a RecursionError is usually an
            # ignored log-callback exception and the flash may still succeed; done decides.
            self._append_log('RecursionError: %s' % msg)
        except Exception:
            pass

    def _append_log(self, msg):
        # Worker threads append to a buffer; the main thread flushes periodically
        self._log_buffer.append(msg)
        if self._log_after is None:
            self._log_after = self.toplevel1.after(40, self._flush_log)

    def _flush_log(self):
        self._log_after = None
        if not self._log_buffer:
            return
        text = '\n'.join(self._log_buffer) + '\n'
        self._log_buffer = []
        try:
            self.out.insert('end', text)
            self.out.see('end')
        except Exception:
            pass

    def _clear_log(self):
        self._log_buffer = []
        if self._log_after is not None:
            try:
                self.toplevel1.after_cancel(self._log_after)
            except Exception:
                pass
            self._log_after = None
        self.out.delete('1.0', 'end')

    def _on_progress(self, phase, frac):
        try:
            # First progress after connect creates the dialog (only while an op runs)
            if self._progress_active and self._progress_dlg is None \
                    and not self._progress_creating and 0.0 <= frac < 1.0:
                self._progress_creating = True
                self.toplevel1.after(0, self._create_progress_dialog)
            dlg = self._progress_dlg
            # Stop updating once the dialog is finished (would override the final state)
            if dlg is None or getattr(dlg, '_finished', False):
                return
            op = 'Erase:' if phase == 0 else 'Program:'
            f = min(1.0, max(0.0, frac))
            self.toplevel1.after(0, lambda d=dlg, o=op, x=f:
                                 (d.set_op(o), d.set_progress(x, 'run', '')))
        except Exception:
            pass

    def _on_done(self, ok):
        try:
            self._progress_active = False
            self._progress_pending = 'ok' if ok else 'fail'
            dlg = self._progress_dlg
            if dlg is None:
                return
            if ok:
                self.toplevel1.after(0, lambda d=dlg: d.set_progress(1.0, 'ok', 'Success'))
            else:
                self.toplevel1.after(0, lambda d=dlg: d.set_progress(0.0, 'fail', 'Failed'))
        except Exception:
            pass

    def _create_progress_dialog(self):
        from progress_dialog import ProgressDialog
        try:
            dlg = ProgressDialog(self.toplevel1, getattr(self, '_op_title', 'Operation'),
                                 getattr(self, '_op_text', ''))
            dlg.bind('<Destroy>', self._on_progress_dlg_destroy)
            self._progress_dlg = dlg
            if self._progress_pending == 'ok':
                dlg.set_progress(1.0, 'ok', 'Success')
            elif self._progress_pending == 'fail':
                dlg.set_progress(0.0, 'fail', 'Failed')
            else:
                dlg.set_op(getattr(self, '_op_text', 'Program:'))
                dlg.set_progress(0.0, 'run', '')
        finally:
            self._progress_creating = False

    def _on_progress_dlg_destroy(self, event):
        if event.widget is getattr(self, '_progress_dlg', None):
            self._progress_dlg = None
        self._progress_creating = False
        # Dialog destroyed ends that op's progress display; do not rebuild
        self._progress_active = False

    def _enumerate_probes(self):
        """List connected probes; empty list on failure."""
        try:
            from pyocd.core.helpers import ConnectHelper
            return ConnectHelper.get_all_connected_probes(blocking=False)
        except Exception:
            return []

    def _refresh_probes(self):
        probes = self._enumerate_probes()
        if not probes:
            self.probe_entry.set('')
            self._selected_probe = None
            return
        p = probes[0]
        board = p.product_name or p.vendor_name
        self.probe_entry.set(board)
        self._selected_probe = p.unique_id

    def _open_probe_picker(self, event=None):
        probes = self._enumerate_probes()
        items = []
        for p in probes:
            board = p.product_name or p.vendor_name
            items.append((board, p.unique_id))
        if not items:
            self._selected_probe = None
            self.probe_entry.set('')

        def on_pick(board, uid):
            self._selected_probe = uid
            self.probe_entry.set(board)

        self._dialog_open = True
        self._set_drop_accept(False)
        dlg = ProbePickerDialog(self.toplevel1, items, on_pick)
        self._current_dialog = dlg
        dlg.bind('<Destroy>', self._on_dialog_destroy, add='+')
        return 'break'

    def _on_device_click(self, event=None):
        self._open_target_picker()
        return 'break'

    def _open_target_picker(self):
        rows = self._library.list_all_targets()

        def on_pick(name):
            self._selected_target = name
            self.target_btn.set(name)
            self._fill_bin_addr(name)

        self._dialog_open = True
        self._set_drop_accept(False)
        dlg = TargetPickerDialog(self.toplevel1, rows, on_pick)
        self._current_dialog = dlg
        dlg.bind('<Destroy>', self._on_dialog_destroy, add='+')

    def _open_pack_manager(self):
        from pack_manager_dialog import PackManagerDialog

        def on_removed(removed):
            if getattr(self, '_selected_target', None) in removed:
                self._selected_target = None
                self.target_btn.set('Not Select')
            self._append_log('Pack removed (%d devices)' % len(removed))

        def on_added(ref, count, already):
            if already:
                self._append_log('Pack already installed: %s (%d devices)' % (ref, count))
            else:
                self._append_log('Pack installed: %s (%d devices)' % (ref, count))

        def on_toggled(ref, enabled, device_names):
            if not enabled and getattr(self, '_selected_target', None) in device_names:
                self._selected_target = None
                self.target_btn.set('Not Select')
            self._append_log('Pack %s: %s' % (ref, 'enabled' if enabled else 'disabled'))

        self._dialog_open = True
        self._set_drop_accept(False)
        dlg = PackManagerDialog(self.toplevel1, self._library, on_removed, on_added, on_toggled)
        self._current_dialog = dlg
        dlg.bind('<Destroy>', self._on_dialog_destroy, add='+')

    def menucallback(self, itemid):
        if itemid == 'about':
            tk.messagebox.showinfo(title="About",
                                    message=show_about)
        elif itemid =='help':
            webbrowser.open('https://github.com/USTHzhanglu/dap_download/blob/main/readme.md',new=0)

    def _browse_bin(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(title='Select bin file',
                                          filetypes=[('Firmware files', '*.bin *.hex *.elf *.axf *.mot *.srec'),
                                                     ('All files', '*.*')])
        if path:
            self.bin_entry.delete(0, 'end')
            self.bin_entry.insert(0, path)
            self._set_bin_addr_visibility(path)
            self.bin_entry.update_idletasks()
            self.bin_entry.xview_moveto(1.0)

    def _set_drop_accept(self, accept):
        try:
            import ctypes
            hwnd = int(self.toplevel1.winfo_id())
            shell32 = ctypes.windll.shell32
            shell32.DragAcceptFiles.argtypes = [ctypes.c_void_p, ctypes.c_bool]
            shell32.DragAcceptFiles.restype = None
            shell32.DragAcceptFiles(ctypes.c_void_p(hwnd), bool(accept))
        except Exception:
            pass

    def _on_dialog_destroy(self, event):
        if getattr(self, '_current_dialog', None) is event.widget:
            self._dialog_open = False
            self._set_drop_accept(True)
            self._current_dialog = None

    def _on_drop_files(self, files):
        if self._dialog_open:
            return
        if not files:
            return
        packs = []
        firmware = None
        for raw in files:
            p = raw.decode('utf-8', errors='replace') if isinstance(raw, bytes) else raw
            if p.lower().endswith('.pack'):
                packs.append(p)
            elif firmware is None:
                firmware = p
        for p in packs:
            self._install_pack(p)
        if firmware:
            self.bin_entry.delete(0, 'end')
            self.bin_entry.insert(0, firmware)
            self._set_bin_addr_visibility(firmware)
            self.bin_entry.update_idletasks()
            self.bin_entry.xview_moveto(1.0)

    def _install_pack(self, path):
        try:
            ref, count, already = self._library.install(path)
            if already:
                self._append_log("Pack already installed: %s (%d devices)" % (ref, count))
            else:
                self._append_log("Pack installed: %s (%d devices)" % (ref, count))
            self._selected_target = None
            self.target_btn.set('Not Select')
        except Exception as e:
            self._append_log("Pack install failed: %s" % e)

    def _parse_speed(self, text):
        """Parse a speed string into Hz; supports '4000 kHz', '4MHz', '5000000', etc."""
        t = (text or '').strip().lower().replace(' ', '')
        if not t:
            return None
        mult = 1
        for suffix, m in (('ghz', 1e9), ('mhz', 1e6), ('khz', 1e3), ('hz', 1),
                          ('g', 1e9), ('m', 1e6), ('k', 1e3)):
            if t.endswith(suffix):
                t = t[: -len(suffix)]
                mult = m
                break
        try:
            return int(float(t) * mult)
        except ValueError:
            return None

    def _set_bin_addr_visibility(self, path):
        is_bin = (path or '').lower().endswith('.bin')
        if is_bin:
            self.bin_addr_lbl.grid()
            self.bin_addr_entry.grid()
            # Re-fill the default address if a target is already selected
            if getattr(self, '_selected_target', None):
                self._fill_bin_addr(self._selected_target)
        else:
            self.bin_addr_lbl.grid_remove()
            self.bin_addr_entry.grid_remove()
            self.bin_addr_entry.delete(0, 'end')

    def _fill_bin_addr(self, name):
        addr = self._library.get_boot_address(name)
        if addr is not None:
            self.bin_addr_entry.delete(0, 'end')
            self.bin_addr_entry.insert(0, '0x%08X' % addr)
            # Select all and focus to signal it is an editable default
            self.bin_addr_entry.focus_set()
            self.bin_addr_entry.select_range(0, 'end')

    def _parse_addr(self, text):
        t = (text or '').strip()
        if not t:
            return None
        try:
            return int(t, 0)
        except ValueError:
            try:
                return int(t, 16)
            except ValueError:
                return None

    def download(self):
        bin_path = self.bin_entry.get()
        target = getattr(self, '_selected_target', None)
        if not bin_path:
            self._clear_log()
            self._append_log('Please select a valid bin file')
            return
        if not target:
            self._clear_log()
            self._append_log('Please select a target device')
            return
        pack_paths = self._library.get_pack_paths(target)
        self._clear_log()
        speed = self._parse_speed(self.speed_entry.get()) if hasattr(self, 'speed_entry') else None
        base = self._parse_addr(self.bin_addr_entry.get()) if hasattr(self, 'bin_addr_entry') else None
        self.out.edit_separator()
        self._op_title = 'Programming Device'
        self._op_text = 'Program:'
        self._progress_active = True
        # Reset the terminal flag so a stale pending cannot instantly close a new dialog
        self._progress_pending = None
        interface = self.interface_entry.get() if hasattr(self, 'interface_entry') else None
        threading.Thread(target=self._flasher.download,
                         args=(bin_path, target, pack_paths, getattr(self, '_selected_probe', None),
                               speed, base, interface), daemon=True).start()

    def erasechip(self):
        target = getattr(self, '_selected_target', None)
        if not target:
            self._clear_log()
            self._append_log('Please select a target device')
            return
        pack_paths = self._library.get_pack_paths(target)
        self._clear_log()
        if tk.messagebox.askokcancel("Erase", "Are you sure you want to erase?"):
            speed = self._parse_speed(self.speed_entry.get()) if hasattr(self, 'speed_entry') else None
            self._op_title = 'Erasing Chip'
            self._op_text = 'Erase:'
            self._progress_active = True
            self._progress_pending = None
            interface = self.interface_entry.get() if hasattr(self, 'interface_entry') else None
            threading.Thread(target=self._flasher.erase,
                             args=(target, pack_paths, getattr(self, '_selected_probe', None),
                                   speed, interface), daemon=True).start()
    
            

if __name__ == '__main__':
    app = PyocdApp()
    app.run()

