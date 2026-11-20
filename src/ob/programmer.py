# coding: utf-8
"""Option-byte read backend + generic step executor for writer YAML flows."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

from core import Flasher
from .catalog import resolve_regs


class SequenceError(RuntimeError):
    """A write sequence failed (step index included in the message)."""


class ObProgrammer:
    """Owns the probe session used by the option-byte window."""

    def __init__(self, target: str, pack_paths=None, probe_id=None,
                 speed_hz=None, interface=None):
        self._options = Flasher._build_options(target, pack_paths, speed_hz, interface)
        self._probe_id = probe_id
        self.session = None
        self._ctx = None

    # ---------------------------------------------------------------- session
    def open(self) -> None:
        if self.session is not None:
            return
        from pyocd.core.helpers import ConnectHelper
        self._ctx = ConnectHelper.session_with_chosen_probe(
            unique_id=self._probe_id, options=self._options)
        self.session = self._ctx.__enter__()

    def close(self) -> None:
        ctx, self._ctx = self._ctx, None
        self.session = None
        if ctx is not None:
            try:
                ctx.__exit__(None, None, None)
            except Exception:
                pass

    # ---------------------------------------------------------------- read
    def _read_regs(self, descriptor) -> Dict[str, int]:
        addresses = resolve_regs(descriptor.regs or {})
        needed = {item['register'] for item in (descriptor.fields or [])}
        regs: Dict[str, int] = {}
        for name in sorted(needed):
            address = addresses.get(name)
            if address is None:
                continue
            regs[name] = int(self.session.target.read_memory(address, 32))
        return regs

    def read(self, descriptor) -> Tuple[Dict[str, int], Dict[str, int]]:
        """Return ({field name: value}, {register name: raw value})."""
        if self.session is None:
            raise RuntimeError('not connected')
        regs = self._read_regs(descriptor)
        values: Dict[str, int] = {}
        for field in descriptor.fields or []:
            raw = regs.get(field['register'], 0)
            bit = int(field['bit'])
            width = int(field['width'])
            values[field['name']] = (raw >> bit) & ((1 << width) - 1)
        return values, regs

    # ---------------------------------------------------------------- write
    @staticmethod
    def _assemble(descriptor, values: Dict[str, int], regs: Dict[str, int]) -> Dict[str, int]:
        """Merge edited field values into whole-register values (RMW)."""
        merged = dict(regs)
        for field in descriptor.fields or []:
            name = field['name']
            register = field['register']
            bit = int(field['bit'])
            width = int(field['width'])
            mask = ((1 << width) - 1) << bit
            current = merged.get(register, 0)
            value = int(values.get(name, 0)) << bit
            merged[register] = (current & ~mask) | (value & mask)
        return merged

    @staticmethod
    def _operand(spec: Any, addresses: Dict[str, int], variables: Dict[str, Any]) -> Any:
        if isinstance(spec, int) and not isinstance(spec, bool):
            return spec
        if isinstance(spec, str):
            if spec.startswith('$'):
                key = spec[1:]
                if key not in variables:
                    raise SequenceError('Undefined variable: %s' % spec)
                return variables[key]
            if spec in addresses:
                return addresses[spec]
        raise SequenceError('Cannot parse operand: %r' % (spec,))

    def _exec_step(self, index: int, step: Dict[str, Any],
                   addresses: Dict[str, int], variables: Dict[str, Any],
                   target) -> None:
        if 'write' in step:
            address = self._operand(step['write'], addresses, variables)
            value = self._operand(step['value'], addresses, variables)
            target.write_memory(int(address), int(value), 32)
        elif 'write_mem' in step:
            address = self._operand(step['addr'], addresses, variables)
            value = self._operand(step['value'], addresses, variables)
            target.write_memory(int(address), int(value), 32)
        elif 'write16' in step:
            address = self._operand(step['write16'], addresses, variables)
            value = self._operand(step['value'], addresses, variables)
            target.write_memory(int(address), int(value), 16)
        elif 'set_bits' in step:
            address = self._operand(step['set_bits'], addresses, variables)
            mask = int(step['mask'])
            value = int(target.read_memory(int(address), 32)) | mask
            target.write_memory(int(address), value, 32)
        elif 'clear_bits' in step:
            address = self._operand(step['clear_bits'], addresses, variables)
            mask = int(step['mask'])
            value = int(target.read_memory(int(address), 32)) & ~mask
            target.write_memory(int(address), value, 32)
        elif 'wait' in step:
            address = self._operand(step['wait'], addresses, variables)
            mask = int(step['mask'])
            want = int(step['eq'])
            timeout = step.get('timeout_ms', 1000)
            deadline = time.time() + timeout / 1000.0
            while True:
                value = int(target.read_memory(int(address), 32))
                if (value & mask) == want:
                    return
                if time.time() > deadline:
                    raise SequenceError('wait timeout (0x%08X & 0x%X != 0x%X)'
                                        % (value, mask, want))
                time.sleep(0.001)
        elif 'assert' in step:
            address = self._operand(step['assert'], addresses, variables)
            value = int(target.read_memory(int(address), 32))
            if (value & int(step['mask'])) != int(step['eq']):
                raise SequenceError('assert failed (read 0x%08X)' % value)
        elif 'delay_ms' in step:
            time.sleep(int(step['delay_ms']) / 1000.0)
        elif 'reset' in step:
            target.reset_and_halt()
        else:
            raise SequenceError('Unknown operation: %r' % (step,))


