# coding: utf-8
"""Local CMSIS-Pack library (self-managed; no cmsis-pack-manager).

Copies dropped .pack files into the local lib dir, parses devices with pyocd's
CmsisPack, and caches them in index.json so device/pack lookups skip parsing.

Layout::
    <lib_dir>/
        <vendor>/<pack>/<version>.pack
        index.json   {"version":1,"packs":[...],"devices":[...]}
"""

import json
import os
import shutil
import sys
import zipfile
from xml.etree import ElementTree as ET

# Import CmsisPack lazily to keep module import light
_CmsisPack = None

# Builtin algorithms show up as a pseudo-pack in the manager list
BUILTIN_REF = '__builtin__'


def _cmsis_pack():
    global _CmsisPack
    if _CmsisPack is None:
        from pyocd.target.pack.cmsis_pack import CmsisPack
        _CmsisPack = CmsisPack
    return _CmsisPack


def _app_dir():
    """Directory holding the program: exe dir when frozen, else the source dir."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _default_lib_dir():
    """Lib root defaults next to the program; overridable via DAP_PACK_DIR."""
    override = os.environ.get('DAP_PACK_DIR')
    if override:
        return os.path.abspath(override)
    return os.path.join(_app_dir(), 'packs')


def _read_pack_meta(pack_path):
    """Extract (vendor, pack, version) from the .pack's embedded PDSC."""
    with zipfile.ZipFile(pack_path) as z:
        pdsc_name = next((n for n in z.namelist() if n.lower().endswith('.pdsc')), None)
        if pdsc_name is None:
            raise ValueError("Pack file does not contain a .pdsc description")
        root = ET.fromstring(z.read(pdsc_name))

    def _text(tag):
        for el in root.iter():
            if el.tag.split('}')[-1] == tag and el.text and el.text.strip():
                return el.text.strip()
        return ''

    vendor = _text('vendor')
    name = _text('name')
    version = ''
    for el in root.iter():
        if el.tag.split('}')[-1] == 'release':
            version = el.get('version') or ''
            if version:
                break
    return vendor, name, version


def _device_flash_size(dev):
    """Largest flash region length (bytes); 0 on failure."""
    try:
        flashes = [r for r in dev.memory_map if getattr(r, 'is_flash', False)]
        if flashes:
            return max(r.length for r in flashes) or 0
    except Exception:
        pass
    return 0


def _device_flash_start(dev):
    """Start address of boot memory (same as pyocd without base_address).

    Returns None when there is no boot memory.
    """
    try:
        boot = dev.memory_map.get_boot_memory()
        if boot is not None:
            return int(boot.start)
    except Exception:
        pass
    return None


def _fmt_flash(size):
    return ('%dK' % (size // 1024)) if size else '-'


class PackLibrary:
    """Local CMSIS-Pack library."""

    def __init__(self, lib_dir=None):
        self._dir = lib_dir or _default_lib_dir()
        # No extra packs/ layer: vendor/pack/version.pack sits next to index.json
        self._packs_dir = self._dir
        self._index_path = os.path.join(self._dir, 'index.json')
        self._builtin_flash_start = {}

    @property
    def dir(self):
        return self._dir

    @property
    def index_path(self):
        return self._index_path

    # ---------- cache read/write ----------
    def _load_index(self):
        try:
            with open(self._index_path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {'packs': [], 'devices': [], 'builtin_enabled': True}
        # Accept entries that have packs/devices (no version field required)
        return {'packs': data.get('packs', []), 'devices': data.get('devices', []),
                'builtin_enabled': data.get('builtin_enabled', True)}

    def _save_index(self, index):
        os.makedirs(self._dir, exist_ok=True)
        index['version'] = 1
        tmp = self._index_path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self._index_path)

    # ---------- install ----------
    def install(self, pack_path):
        """Install a .pack into the library.

        Returns (ref_str, device_count, already_installed).
        """
        pack_path = os.path.abspath(pack_path)
        if not os.path.isfile(pack_path):
            raise FileNotFoundError(pack_path)

        # Parse devices (also verifies the pack is readable)
        CmsisPack = _cmsis_pack()
        devices = CmsisPack(pack_path).devices
        if not devices:
            raise ValueError("Pack defines no devices")

        vendor, name, version = _read_pack_meta(pack_path)
        if not (vendor and name and version):
            raise ValueError("Unable to read vendor/pack/version from PDSC")

        ref = "%s.%s.%s" % (vendor, name, version)
        rel_path = os.path.join(vendor, name, "%s.pack" % version)
        dest = os.path.join(self._packs_dir, rel_path)
        already = os.path.isfile(dest)
        if not already:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(pack_path, dest)

        # Collect device records, keeping the pack ref for path lookup
        dev_records = []
        for dev in devices:
            dev_records.append({
                'name': dev.part_number,
                'vendor': dev.vendor or '',
                'flash': _device_flash_size(dev),
                'ref': ref,
            })

        index = self._load_index()
        # Drop any old records for this ref, then write
        packs = [p for p in index['packs'] if p.get('ref') != ref]
        packs.append({
            'ref': ref,
            'vendor': vendor,
            'pack': name,
            'version': version,
            'path': rel_path,
            'enabled': True,
        })
        devices_map = {d['name']: d for d in dev_records}
        other = [d for d in index['devices'] if d['name'] not in devices_map]
        index['packs'] = packs
        index['devices'] = other + dev_records
        self._save_index(index)
        return ref, len(devices), already

    # ---------- query ----------
    def list_targets(self):
        """List all library devices (excluding disabled packs).

        Returns [(name, vendor, part, flash), ...]; name is the raw part_number used
        for flashing, part is the display name without a leading '-'.
        """
        index = self._load_index()
        disabled = {p['ref'] for p in index['packs'] if not p.get('enabled', True)}
        rows = []
        for d in index['devices']:
            name = d.get('name', '')
            if not name:
                continue
            if d.get('ref') in disabled:
                continue
            rows.append((name, d.get('vendor', '') or '-', name.lstrip('-'),
                         _fmt_flash(d.get('flash', 0))))
        rows.sort(key=lambda r: (r[0].lower(), r[1].lower()))
        return rows

    def get_boot_address(self, target_name):
        """Return a chip's boot memory start (default bin base address).

        Library devices are parsed from their pack; builtins use the list cached
        during enumeration (builtins have no pack).
        """
        index = self._load_index()
        dev = next((d for d in index['devices'] if d['name'] == target_name), None)
        if dev is not None:
            return self._resolve_boot_from_pack(dev.get('ref'), target_name)
        return getattr(self, '_builtin_flash_start', {}).get(target_name)

    def _resolve_boot_from_pack(self, ref, target_name):
        if not ref:
            return None
        index = self._load_index()
        for p in index['packs']:
            if p.get('ref') != ref:
                continue
            path = os.path.join(self._packs_dir, p['path'])
            try:
                pk = _cmsis_pack()(path)
                for d in pk.devices:
                    if d.part_number == target_name:
                        return _device_flash_start(d)
            except Exception:
                continue
        return None

    def get_pack_paths(self, target_name):
        """Absolute .pack paths for a device; empty when its pack is disabled."""
        index = self._load_index()
        dev = next((d for d in index['devices'] if d['name'] == target_name), None)
        if dev is None:
            return []
        ref = dev.get('ref')
        if not ref:
            return []
        for p in index['packs']:
            if p.get('ref') == ref and not p.get('enabled', True):
                return []
        paths = []
        for p in index['packs']:
            if p.get('ref') == ref:
                paths.append(os.path.abspath(os.path.join(self._packs_dir, p['path'])))
        return paths

    def list_packs(self):
        """Returns [(ref, vendor, pack, version, enabled), ...]."""
        return [(p['ref'], p.get('vendor', ''), p.get('pack', ''), p.get('version', ''),
                 p.get('enabled', True))
                for p in self._load_index()['packs']]

    def toggle_enabled(self, ref):
        """Toggle a pack's enabled state.

        Returns (new_enabled, device_names_for_ref).
        """
        index = self._load_index()
        dev_names = {d['name'] for d in index['devices'] if d.get('ref') == ref}
        for p in index['packs']:
            if p.get('ref') == ref:
                p['enabled'] = not p.get('enabled', True)
                enabled = p['enabled']
                break
        else:
            raise KeyError(ref)
        self._save_index(index)
        return enabled, dev_names

    def remove(self, ref):
        """Remove a pack (delete file + drop cache records).

        Returns the device name set it supplied (so the UI can reset selection).
        """
        index = self._load_index()
        removed_names = {d['name'] for d in index['devices'] if d.get('ref') == ref}
        kept_packs = [p for p in index['packs'] if p.get('ref') != ref]
        for p in index['packs']:
            if p.get('ref') != ref:
                continue
            rel = p['path']
            dest = os.path.join(self._packs_dir, rel)
            if os.path.isfile(dest):
                os.remove(dest)
            # Clean up empty directories
            d = os.path.dirname(dest)
            while d and d != self._packs_dir and os.path.isdir(d):
                try:
                    os.rmdir(d)
                except OSError:
                    break
                d = os.path.dirname(d)
        index['packs'] = kept_packs
        # Filter that ref's devices directly; no need to re-parse packs
        index['devices'] = [d for d in index['devices'] if d.get('ref') != ref]
        self._save_index(index)
        return removed_names

    def list_all_targets(self):
        """List builtin targets (if enabled) plus library devices.

        On a name clash the library device (more precise pack algo) wins.
        Returns [(name, vendor, part, flash), ...].
        """
        merged = {}
        if self.builtin_enabled():
            for row in self._list_builtin_targets():
                merged[row[0].lower()] = row
        for row in self.list_targets():
            merged[row[0].lower()] = row
        return list(merged.values())

    def builtin_enabled(self):
        """Whether builtin algorithms are currently enabled."""
        return bool(self._load_index().get('builtin_enabled', True))

    def toggle_builtin_enabled(self):
        """Toggle builtin algorithms. Returns (new_enabled, builtin target names)."""
        index = self._load_index()
        new_val = not bool(index.get('builtin_enabled', True))
        index['builtin_enabled'] = new_val
        self._save_index(index)
        return new_val, self._builtin_target_names()

    @staticmethod
    def _builtin_target_names():
        from pyocd.target.builtin import BUILTIN_TARGETS
        return set(BUILTIN_TARGETS.keys())

    @staticmethod
    def builtin_version():
        """pyocd version of the builtin algorithms."""
        try:
            import pyocd
            return getattr(pyocd, '__version__', '') or ''
        except Exception:
            return ''

    def _list_builtin_targets(self):
        """Enumerate pyocd builtin targets (have flash algo, no pack) and cache boot addresses."""
        from pyocd.target import TARGET
        from pyocd.core.session import Session
        from pyocd.tools.lists import StubProbe
        from pyocd.target.builtin import BUILTIN_TARGETS
        rows = []
        self._builtin_flash_start = {}
        for name in BUILTIN_TARGETS:
            try:
                s = Session(StubProbe(), no_config=True, target_override='cortex_m')
                t = TARGET[name](s)
                vendor = t.vendor or '-'
                part = t.part_number or name
                flashes = [r for r in t.memory_map if getattr(r, 'is_flash', False)]
                flash = ('%dK' % (max(r.length for r in flashes) // 1024)) if flashes else '-'
                boot = t.memory_map.get_boot_memory()
                if boot is not None:
                    self._builtin_flash_start[name] = int(boot.start)
                rows.append((name, vendor, part, flash))
            except Exception:
                rows.append((name, '-', name, '-'))
        return rows
