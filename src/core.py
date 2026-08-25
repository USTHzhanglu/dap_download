#!/usr/bin/env python
# coding: utf-8

import datetime
import os
from typing import Callable, Optional

from pyocd.core.helpers import ConnectHelper
from pyocd.flash.file_programmer import FileProgrammer
from pyocd.flash.eraser import FlashEraser

LogFunc = Callable[[str], None]


class Flasher:
    def __init__(self, log: Optional[LogFunc] = None):
        self._log = log if log is not None else print

    def download(self, bin_path: str, yaml_path: str) -> bool:
        ok = True
        try:
            os.chdir(yaml_path)
            self._log("-------------开始烧录--------------")
            self._log(datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
            self._log("----------正在连接设备-------------")
            with ConnectHelper.session_with_chosen_probe() as session:
                target = session.target
                # Load firmware into device.
                FileProgrammer(session, progress=None).program(bin_path)
                # Reset, run.
                target.reset_and_halt()
                target.resume()
        except Exception as r:
            self._log(str(r))
            ok = False
        finally:
            if ok:
                self._log("[" + 20 * "=" + "]     100%")
                self._log("-------------烧录成功--------------")
            else:
                self._log("-------------烧录失败--------------")
            self._log(datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        return ok

    def erase(self, yaml_path: str) -> bool:
        ok = True
        try:
            os.chdir(yaml_path)
            self._log("-------------开始擦除--------------")
            self._log(datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
            with ConnectHelper.session_with_chosen_probe() as session:
                FlashEraser(session, mode=FlashEraser.Mode.CHIP).erase()
        except Exception as r:
            self._log(str(r))
            ok = False
        finally:
            if ok:
                self._log("-------------擦除完毕--------------")
            else:
                self._log("-------------擦除失败--------------")
            self._log(datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        return ok

    def scan_probes(self):
        try:
            probes = ConnectHelper.get_all_connected_probes(blocking=False)
        except Exception as r:
            self._log(str(r))
            return
        if not probes:
            self._log("未检测到探针")
            return
        for probe in probes:
            desc = f"{probe.vendor_name} {probe.product_name}".strip()
            self._log(f"{desc}  unique_id={probe.unique_id}")
