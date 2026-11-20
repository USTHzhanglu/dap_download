# coding: utf-8
"""Generate read-only option-byte descriptors from an installed CMSIS-Pack.

Reading option bytes is deterministic: the pack's SVD describes the flash
controller's option registers and their bit fields. This module builds an
in-memory descriptor (regs + fields) per device family; writing rules live in
the writer YAML (option_bytes/).
"""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

from .errors import ObParseError
from .pack import load_pack
from .svd import Svd, SvdPeripheral, load_svd

OB_TOKENS = {"OPT", "USD", "OB", "OPTION", "OTP", "OPTIONBYTES"}
FLASH_PERIPHERAL_PREFIXES = ("FLASH", "FMC", "EFC", "NVM")
_OPTION_REG_NAME_RE = re.compile(
    r"(OPT|OB|USD|RDP|FSEC|FOPT|UCFG|PLEVEL|USER|CONFIG|FUSE|WP)",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    return re.sub(r'[^a-z0-9]', '', (text or '').lower())


def pack_key(value: str) -> str:
    return (value or '').replace('@', '.').strip().lower()


def _tokens(name: str):
    return {t for t in re.split(r'[^A-Za-z0-9]+', name.upper()) if t}


def _is_flash_peripheral(name: str) -> bool:
    upper = name.upper()
    return any(upper.startswith(prefix) for prefix in FLASH_PERIPHERAL_PREFIXES)


def _is_option_register(name: str) -> bool:
    if not _OPTION_REG_NAME_RE.search(name):
        return False
    upper = name.upper()
    return 'UNLOCK' not in upper and 'KEY' not in upper


def _flash_peripheral(svd: Svd) -> Optional[SvdPeripheral]:
    for peripheral in svd.peripherals:
        if _is_flash_peripheral(peripheral.name) and peripheral.registers:
            return peripheral
    return None


def _reg_key(peripheral: SvdPeripheral, name: str) -> str:
    """Prefix register names with the peripheral (FLASH_UNLOCK, FMC_STAT...)."""
    peripheral_name = peripheral.name.upper()
    upper = name.upper()
    if upper.startswith(peripheral_name + '_'):
        return name
    return '%s_%s' % (peripheral_name, name)


def _regs_of(peripheral: SvdPeripheral) -> Dict[str, Any]:
    """All flash-controller registers (needed later by write sequences)."""
    regs: Dict[str, Any] = {peripheral.name: peripheral.base}
    for register in peripheral.registers:
        regs[_reg_key(peripheral, register.name)] = {
            'at': peripheral.name,
            'offset': register.offset,
        }
    return regs


def _fields_of(peripheral: SvdPeripheral) -> List[Dict[str, Any]]:
    fields: List[Dict[str, Any]] = []
    for register in peripheral.registers:
        if not _is_option_register(register.name):
            continue
        register_key = _reg_key(peripheral, register.name)
        for item in register.fields:
            entry: Dict[str, Any] = {
                'name': item.name,
                'register': register_key,
                'bit': item.bit_offset,
                'width': item.bit_width,
            }
            if item.description:
                entry['desc'] = item.description
            fields.append(entry)
    return fields



def _family_name(names: List[str]) -> str:
    if not names:
        return 'device'
    prefix = names[0]
    for name in names[1:]:
        limit = min(len(prefix), len(name))
        index = 0
        while index < limit and prefix[index] == name[index]:
            index += 1
        prefix = prefix[:index]
    prefix = prefix.strip('-_ .')
    return prefix or names[0].strip('-_ .') or 'device'


@dataclass
class Descriptor:
    device: str
    devices: List[str]
    match: List[str]
    from_pack: str
    regs: Dict[str, Any]
    fields: List[Dict[str, Any]]


    def matches(self, target: str) -> bool:
        wanted = normalize(target)
        if any(normalize(name) == wanted for name in self.devices):
            return True
        if normalize(self.device) == wanted:
            return True
        stripped = (target or '').lstrip('-_').lower()
        for pattern in self.match:
            if fnmatch.fnmatchcase((target or '').lower(), pattern.lower()):
                return True
            if fnmatch.fnmatchcase(stripped, pattern.lower()):
                return True
        return False


def generate_for_pack(pack_path: str) -> List[Descriptor]:
    """Parse a .pack and return one descriptor per device family."""
    pack = load_pack(pack_path)
    try:
        svd_cache: Dict[str, Optional[Svd]] = {}
        groups: Dict[tuple, Dict[str, Any]] = {}
        for device in pack.devices:
            svd = None
            if device.svd and pack.has(device.svd):
                if device.svd not in svd_cache:
                    try:
                        svd_cache[device.svd] = load_svd(pack.read(device.svd))
                    except ObParseError:
                        svd_cache[device.svd] = None
                svd = svd_cache[device.svd]
            if svd is None:
                continue
            peripheral = _flash_peripheral(svd)
            if peripheral is None:
                continue
            option_names = tuple(
                r.name for r in peripheral.registers if _is_option_register(r.name)
            )
            if not option_names:
                continue
            key = (device.svd, peripheral.name, option_names)
            groups.setdefault(key, {'devices': [], 'peripheral': peripheral})

            groups[key]['devices'].append(device.name)

        descriptors: List[Descriptor] = []
        for (svd_path, peripheral_name, _option_names), group in sorted(
                groups.items(), key=lambda item: (item[0][1], item[0][2])):
            names = sorted(group['devices'])
            family = _family_name(names)
            peripheral = group['peripheral']
            descriptors.append(Descriptor(
                device=family,
                devices=names,
                match=[family + '*'],
                from_pack=pack.ref,
                regs=_regs_of(peripheral),
                fields=_fields_of(peripheral),
            ))
        return descriptors
    finally:
        pack.close()


class ObProvider:
    """Auto-generated read descriptors from installed packs."""

    def __init__(self, library):
        self._library = library
        self._cache: Dict[tuple, List[Descriptor]] = {}

    def _descriptors_for_path(self, path: Optional[str]) -> List[Descriptor]:
        if not path or not os.path.isfile(path):
            return []
        try:
            stamp = (os.path.abspath(path), os.path.getmtime(path))
        except OSError:
            return []
        cached = self._cache.get(stamp)
        if cached is not None:
            return cached
        try:
            descriptors = generate_for_pack(path)
        except (OSError, ObParseError):
            descriptors = []
        self._cache[stamp] = descriptors
        return descriptors

    def descriptors_for_pack_ref(self, ref: str) -> List[Descriptor]:
        return self._descriptors_for_path(self._library.path_for_ref(ref))

    def support_for_pack(self, ref: str) -> str:
        try:
            descriptors = self.descriptors_for_pack_ref(ref)
        except Exception:
            return '-'
        return 'Support' if any(d.fields for d in descriptors) else '-'

    def descriptor_for_target(self, target: Optional[str]) -> Optional[Descriptor]:
        if not target:
            return None
        try:
            packs = self._library.list_packs()
        except Exception:
            return None
        for ref, _vendor, _pack, _version, enabled in packs:
            if not enabled:
                continue
            for descriptor in self.descriptors_for_pack_ref(ref):
                if descriptor.matches(target):
                    return descriptor
        return None
