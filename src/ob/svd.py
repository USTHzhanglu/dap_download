# coding: utf-8
"""容错 SVD 解析(厂商 SVD 常带 BOM/前导空白/非法字符,不能直接交给严格解析器)。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from xml.etree import ElementTree as ET

from .errors import ObParseError

_XML_DECL_RE = re.compile(r"^\s*<\?xml[^>]*\?>")
_INVALID_AMP_RE = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _int(text: Optional[str], default: int = 0) -> int:
    if text is None:
        return default
    try:
        return int(str(text).strip(), 0)
    except (TypeError, ValueError):
        return default


@dataclass
class SvdField:
    name: str
    bit_offset: int
    bit_width: int
    description: str = ""
    access: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        data: Dict[str, object] = {
            "name": self.name,
            "bit": self.bit_offset,
            "width": self.bit_width,
        }
        if self.description:
            data["desc"] = self.description
        if self.access:
            data["access"] = self.access
        return data


@dataclass
class SvdRegister:
    name: str
    offset: int
    size: int = 32
    access: Optional[str] = None
    description: str = ""
    fields: List[SvdField] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "offset": self.offset,
            "size": self.size,
            "access": self.access,
            "desc": self.description,
            "fields": [f.to_dict() for f in self.fields],
        }


@dataclass
class SvdPeripheral:
    name: str
    base: int
    description: str = ""
    derived_from: Optional[str] = None
    registers: List[SvdRegister] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "base": self.base,
            "desc": self.description,
            "derived_from": self.derived_from,
            "registers": [r.to_dict() for r in self.registers],
        }


@dataclass
class Svd:
    name: str
    peripherals: List[SvdPeripheral] = field(default_factory=list)

    def peripheral(self, name: str) -> Optional[SvdPeripheral]:
        want = name.upper()
        for per in self.peripherals:
            if per.name.upper() == want:
                return per
        return None


def _clean_xml(data: bytes) -> str:
    """把厂商 SVD 清洗成严格解析器可接受的形式。"""
    text = data.decode("utf-8-sig", errors="replace")
    # 去掉 XML 声明前的空白(GD32 等厂商的 SVD 常见问题)。
    text = _XML_DECL_RE.sub("", text, count=1).lstrip("\ufeff \t\r\n")
    # 去掉首尾残留的 XML 声明。
    text = re.sub(r"<\?xml[^>]*\?>", "", text, count=1)
    return text


def load_svd(data: bytes) -> Svd:
    """解析 SVD 字节流;失败时抛出 ObParseError。"""
    text = _clean_xml(data)
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        # 再尝试修复裸 '&'(部分厂商 SVD 不转义)。
        try:
            root = ET.fromstring(_INVALID_AMP_RE.sub("&amp;", text))
        except ET.ParseError as exc:
            raise ObParseError("failed to parse SVD: %s" % exc)

    name = (root.findtext("name") or "").strip()
    peripherals: List[SvdPeripheral] = []

    for per_elem in root.iter():
        if _local(per_elem.tag) != "peripheral":
            continue
        per_name = (per_elem.findtext("name") or "").strip()
        if not per_name:
            continue
        base = _int(per_elem.findtext("baseAddress"), -1)
        derived = per_elem.attrib.get("derivedFrom")
        desc = (per_elem.findtext("description") or "").strip()

        registers: List[SvdRegister] = []
        registers_elem = None
        for child in per_elem:
            if _local(child.tag) == "registers":
                registers_elem = child
                break
        if registers_elem is not None:
            for reg_elem in registers_elem:
                if _local(reg_elem.tag) != "register":
                    continue
                registers.extend(_parse_register(reg_elem))

        peripherals.append(
            SvdPeripheral(
                name=per_name,
                base=base,
                description=desc,
                derived_from=derived,
                registers=registers,
            )
        )

    # 解析 derivedFrom:继承被引用外设的寄存器与基址。
    by_name: Dict[str, SvdPeripheral] = {p.name.upper(): p for p in peripherals}
    for per in peripherals:
        if not per.derived_from:
            continue
        parent = by_name.get(per.derived_from.upper())
        if parent is None:
            continue
        if per.base < 0:
            per.base = parent.base
        if not per.registers:
            per.registers = list(parent.registers)

    for per in peripherals:
        if per.base < 0:
            per.base = 0

    return Svd(name=name, peripherals=peripherals)


def _parse_register(reg_elem: ET.Element) -> List[SvdRegister]:
    name = (reg_elem.findtext("name") or "").strip()
    offset = _int(reg_elem.findtext("addressOffset"), -1)
    if not name or offset < 0:
        return []
    size = _int(reg_elem.findtext("size"), 32)
    access = reg_elem.attrib.get("access") or reg_elem.findtext("access")
    desc = (reg_elem.findtext("description") or "").strip()

    fields: List[SvdField] = []
    fields_elem = None
    for child in reg_elem:
        if _local(child.tag) == "fields":
            fields_elem = child
            break
    if fields_elem is not None:
        for field_elem in fields_elem:
            if _local(field_elem.tag) != "field":
                continue
            field = _parse_field(field_elem)
            if field is not None:
                fields.append(field)

    dim = _int(reg_elem.findtext("dim"), 0)
    if dim > 0:
        increment = _int(reg_elem.findtext("dimIncrement"), 0)
        # SVD 数组名常用 %s 或 [%s] 占位。
        base_name = name.replace("[%s]", "").replace("%s", "")
        registers = []
        for index in range(dim):
            registers.append(
                SvdRegister(
                    name="%s%d" % (base_name, index),
                    offset=offset + increment * index,
                    size=size,
                    access=access,
                    description=desc,
                    fields=list(fields),
                )
            )
        return registers

    return [
        SvdRegister(
            name=name,
            offset=offset,
            size=size,
            access=access,
            description=desc,
            fields=fields,
        )
    ]


def _parse_field(field_elem: ET.Element) -> Optional[SvdField]:
    name = (field_elem.findtext("name") or "").strip()
    if not name or name.lower().startswith("reserved"):
        return None

    bit_offset = _int(field_elem.findtext("bitOffset"), -1)
    bit_width = _int(field_elem.findtext("bitWidth"), -1)
    if bit_offset < 0:
        lsb = _int(field_elem.findtext("lsb"), -1)
        msb = _int(field_elem.findtext("msb"), -1)
        if lsb >= 0 and msb >= lsb:
            bit_offset = lsb
            bit_width = msb - lsb + 1
    if bit_offset < 0 or bit_width <= 0:
        return None

    return SvdField(
        name=name,
        bit_offset=bit_offset,
        bit_width=bit_width,
        description=(field_elem.findtext("description") or "").strip(),
        access=field_elem.attrib.get("access") or field_elem.findtext("access"),
    )
