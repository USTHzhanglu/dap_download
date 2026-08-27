#!/usr/bin/env python
# coding: utf-8

import gc
import logging
from typing import Callable, Optional

from pyocd.core.helpers import ConnectHelper
from pyocd.flash.file_programmer import FileProgrammer
from pyocd.flash.eraser import FlashEraser

LogFunc = Callable[[str], None]


class _PyocdLogBridge(logging.Handler):
    """Forward pyocd flash stats logs to the GUI LOG callback."""

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def emit(self, record):
        try:
            msg = record.getMessage()
            # Keep only key stats (identical/programmed) and warnings/errors
            if record.levelno >= logging.WARNING or 'identical' in msg or 'programmed' in msg:
                self._fn(msg)
        except Exception:
            pass


class Flasher:
    def __init__(self, log: Optional[LogFunc] = None,
                 progress: Optional[Callable[[float], None]] = None,
                 done: Optional[Callable[[bool], None]] = None):
        self._log = log if log is not None else print
        self._progress = progress
        self._done = done
        # Forward flash stats (identical/skipped) to LOG to spot smart_flash skips
        self._pyocd_bridge = _PyocdLogBridge(self._log)
        logging.getLogger('pyocd.flash').addHandler(self._pyocd_bridge)
        logging.getLogger('pyocd.flash').setLevel(logging.INFO)

    @staticmethod
    def _build_options(target_override, pack_paths=None, speed_hz=None, interface=None):
        """Session options shared by flash and erase."""
        options = {'target_override': target_override}
        if pack_paths:
            options['pack'] = pack_paths
        if speed_hz:
            options['frequency'] = int(speed_hz)
        if interface:
            options['dap_protocol'] = interface.lower()
        return options

    def _finish(self, ok):
        """Completion signal; notify the UI via the done callback."""
        if self._done is not None:
            try:
                self._done(ok)
            except Exception:
                pass

    def _wrap_prog(self, frac):
        """Convert FileProgrammer progress to (phase, frac) (0=erase, 1=program).

        Phase switch is inferred from a progress regression (erase -> program).
        """
        phase, last = self._prog_state
        if frac < last - 1e-4:  # regression => program phase started
            phase = 1
        self._prog_state = [phase, frac]
        if self._progress is not None:
            try:
                self._progress(phase, frac)
            except Exception:
                pass

    def _report(self, frac):
        # Non-FileProgrammer progress (e.g. connect); phase defaults to erase
        if self._progress is not None:
            try:
                self._progress(0, frac)
            except Exception:
                pass

    def download(self, bin_path: str, target_override: str,
                 pack_paths: Optional[list] = None, probe_id: Optional[str] = None,
                 speed_hz: Optional[int] = None, base_address: Optional[int] = None,
                 interface: Optional[str] = None) -> bool:
        ok = True
        try:
            self._log("Programming: %s -> %s" % (bin_path, target_override))
            options = self._build_options(target_override, pack_paths, speed_hz, interface)
            with ConnectHelper.session_with_chosen_probe(unique_id=probe_id, options=options) as session:
                target = session.target
                # First progress after connect prompts the UI to show the dialog
                self._report(0.0)
                # Staged progress: erase (0) / program (1)
                self._prog_state = [0, 0.0]
                # bin carries no addresses: use base_address, else boot memory
                fp = FileProgrammer(session, progress=self._wrap_prog)
                if base_address is not None:
                    fp.program(bin_path, base_address=int(base_address))
                else:
                    fp.program(bin_path)
                target.reset_and_halt()
                target.resume()
        except Exception as r:
            gc.collect()
            self._log("Flash failed: %s" % r)
            ok = False
        finally:
            self._finish(ok)
            if ok:
                self._log("Flash success")
        return ok

    def erase(self, target_override: str, pack_paths: Optional[list] = None,
              probe_id: Optional[str] = None, speed_hz: Optional[int] = None,
              interface: Optional[str] = None) -> bool:
        ok = True
        try:
            self._log("Erase: %s" % target_override)
            options = self._build_options(target_override, pack_paths, speed_hz, interface)
            with ConnectHelper.session_with_chosen_probe(unique_id=probe_id, options=options) as session:
                session.target.reset_and_halt()
                self._report(0.0)
                FlashEraser(session, mode=FlashEraser.Mode.CHIP).erase()
        except Exception as r:
            gc.collect()
            self._log("Erase failed: %s" % r)
            ok = False
        finally:
            self._finish(ok)
            if ok:
                self._log("Erase done")
        return ok




