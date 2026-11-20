# coding: utf-8
"""CMSIS-Pack(.pack)读取:pdsc 解析、设备/算法/内存/SVD 提取。"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

from .errors import ObParseError

_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")


def _local(tag: str) -> str:
    """返回去掉命名空间的标签名。"""
    return tag.rsplit("}", 1)[-1]


def _as_int(value: Optional[str], default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class Algorithm:
    """pdsc 里的 <algorithm> 条目(一个 FLM 及其地址范围)。"""

    name: str
    start: int
    size: int
    default: bool = False
    style: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "name": self.name,
            "start": self.start,
            "size": self.size,
            "default": self.default,
        }
        if self.style:
            data["style"] = self.style
        return data


@dataclass(frozen=True)
class Memory:
    """pdsc 里的 <memory> 条目。"""

    name: str
    start: int
    size: int
    access: Optional[str] = None
    default: bool = False
    startup: bool = False


@dataclass
class Device:
    """pdsc 里的一个器件(一个具体型号)。"""

    name: str
    family: Optional[str] = None
    svd: Optional[str] = None
    algorithms: List[Algorithm] = field(default_factory=list)
    memories: List[Memory] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "family": self.family,
            "svd": self.svd,
            "algorithms": [a.to_dict() for a in self.algorithms],
            "memories": [
                {"name": m.name, "start": m.start, "size": m.size}
                for m in self.memories
            ],
        }


@dataclass
class Pack:
    """一个已打开(可惰性读取)的 CMSIS-Pack。"""

    path: Path
    vendor: str
    name: str
    version: str
    pdsc_name: str
    devices: List[Device] = field(default_factory=list)
    _zip: Optional[zipfile.ZipFile] = field(default=None, repr=False)

    @property
    def ref(self) -> str:
        """例如 ArteryTek.AT32F425_DFP@2.1.5,用于 YAML 溯源。"""
        return "%s.%s@%s" % (self.vendor, self.name, self.version)

    @property
    def members(self) -> List[str]:
        if self._zip is None:
            return []
        return self._zip.namelist()

    def has(self, member: str) -> bool:
        return self._zip is not None and member in self._zip.namelist()

    def read(self, member: str) -> bytes:
        if self._zip is None:
            raise ObParseError("pack is closed: %s" % self.path)
        try:
            return self._zip.read(member)
        except KeyError:
            raise ObParseError("file not found in pack: %s" % member)

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()
            self._zip = None


def _resolve_version(pack_path: Path, root: ET.Element) -> str:
    # 本地 pack 常见命名: <Pack>/<version>.pack,优先用文件名/父目录名。
    for candidate in (pack_path.stem, pack_path.parent.name):
        if _VERSION_RE.match(candidate):
            return candidate
    for child in root:
        if _local(child.tag) == "releases":
            for rel in child:
                version = rel.attrib.get("version")
                if version:
                    return version
    return "unknown"


def _parse_algorithm(elem: ET.Element) -> Optional[Algorithm]:
    name = elem.attrib.get("name")
    if not name:
        return None
    style = elem.attrib.get("style")
    if style is not None and style.lower() != "keil":
        # 目前仅解析 Keil FLM 风格算法(与 pyOCD 一致)。
        return None
    return Algorithm(
        name=name,
        start=_as_int(elem.attrib.get("start")),
        size=_as_int(elem.attrib.get("size")),
        default=_as_bool(elem.attrib.get("default")),
        style=style,
    )


def _parse_memory(elem: ET.Element) -> Optional[Memory]:
    name = elem.attrib.get("id") or elem.attrib.get("name")
    if not name:
        return None
    return Memory(
        name=name,
        start=_as_int(elem.attrib.get("start")),
        size=_as_int(elem.attrib.get("size")),
        access=elem.attrib.get("access"),
        default=_as_bool(elem.attrib.get("default")),
        startup=_as_bool(elem.attrib.get("startup")),
    )


def _direct_debug_svd(elem: ET.Element) -> Optional[str]:
    for child in elem:
        if _local(child.tag) == "debug":
            svd = child.attrib.get("svd")
            if svd:
                return svd
    return None


def _walk_devices(
    elem: ET.Element,
    pack: Pack,
    family: Optional[str],
    svd: Optional[str],
    algorithms: List[Algorithm],
) -> None:
    tag = _local(elem.tag)

    local_svd = _direct_debug_svd(elem) or svd
    local_family = (
        elem.attrib.get("Dfamily")
        or elem.attrib.get("DsubFamily")
        or family
    )

    own_algorithms = [
        algo
        for algo in (_parse_algorithm(c) for c in elem if _local(c.tag) == "algorithm")
        if algo is not None
    ]
    effective_algorithms = own_algorithms or algorithms

    if tag == "device":
        name = elem.attrib.get("Dname")
        if name:
            memories = [
                mem
                for mem in (_parse_memory(c) for c in elem if _local(c.tag) == "memory")
                if mem is not None
            ]
            pack.devices.append(
                Device(
                    name=name,
                    family=local_family,
                    svd=local_svd,
                    algorithms=list(effective_algorithms),
                    memories=memories,
                )
            )
        return

    for child in elem:
        if _local(child.tag) in ("family", "subFamily", "device"):
            _walk_devices(child, pack, local_family, local_svd, effective_algorithms)


def load_pack(path: "str | Path") -> Pack:
    """打开 .pack,解析 pdsc,返回 Pack(含器件列表)。"""
    pack_path = Path(path)
    if not pack_path.is_file():
        raise ObParseError("pack file does not exist: %s" % pack_path)
    try:
        zf = zipfile.ZipFile(pack_path)
    except zipfile.BadZipFile as exc:
        raise ObParseError("not a valid .pack (zip): %s (%s)" % (pack_path, exc))

    pdsc_names = sorted(n for n in zf.namelist() if n.lower().endswith(".pdsc"))
    if not pdsc_names:
        zf.close()
        raise ObParseError("no .pdsc file in pack: %s" % pack_path)
    pdsc_name = pdsc_names[0]
    try:
        root = ET.fromstring(zf.read(pdsc_name))
    except ET.ParseError as exc:
        zf.close()
        raise ObParseError("failed to parse pdsc: %s (%s)" % (pdsc_name, exc))

    vendor = (root.findtext("vendor") or "").strip() or "unknown"
    name = (root.findtext("name") or "").strip() or pack_path.stem
    version = _resolve_version(pack_path, root)

    pack = Pack(
        path=pack_path,
        vendor=vendor,
        name=name,
        version=version,
        pdsc_name=pdsc_name,
        _zip=zf,
    )

    for child in root:
        if _local(child.tag) in ("devices", "family", "subFamily", "device"):
            _walk_devices(child, pack, None, None, [])
    return pack
