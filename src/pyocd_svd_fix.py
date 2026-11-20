# coding: utf-8
"""Tolerate malformed vendor SVD files.

Some packs (e.g. GigaDevice GD32F3x0) ship an SVD whose XML declaration is
preceded by whitespace. pyOCD parses the SVD in a background thread during
session init; the strict ElementTree parser raises ParseError and the thread
prints a traceback (swallowed by pyOCD's loader).

This module patches pyOCD's SVD parser to clean the text and retry, and makes
the loader swallow any remaining SVD errors (SVD is not needed for flashing or
option-byte register access).
"""

from __future__ import annotations

import logging
import re
from xml.etree import ElementTree as ET

LOG = logging.getLogger(__name__)

_XML_DECL_RE = re.compile(r'^\s*<\?xml[^>]*\?>')


def _read_bytes(source):
    if hasattr(source, 'read'):
        try:
            source.seek(0)
        except Exception:
            pass
        data = source.read()
        if isinstance(data, bytes):
            return data
        return data.encode('utf-8', errors='replace')
    with open(source, 'rb') as handle:
        return handle.read()


def _clean(data: bytes) -> str:
    text = data.decode('utf-8-sig', errors='replace')
    text = _XML_DECL_RE.sub('', text, count=1)
    return text.lstrip()


def apply() -> None:
    """Install the tolerant parser once; safe to call repeatedly."""
    try:
        from pyocd.debug.svd.parser import SVDParser
        from pyocd.debug.svd.loader import SVDLoader
    except Exception:
        return

    if getattr(SVDParser, '_dap_svd_patched', False):
        return

    original_for_xml_file = SVDParser.for_xml_file

    def for_xml_file(cls, path, remove_reserved=False):
        try:
            return original_for_xml_file.__func__(cls, path, remove_reserved)
        except ET.ParseError:
            data = _read_bytes(path)
            tree = ET.ElementTree(ET.fromstring(_clean(data)))
            LOG.warning('SVD had a malformed header; parsed after cleaning')
            return cls(tree, remove_reserved)

    SVDParser.for_xml_file = classmethod(for_xml_file)
    SVDParser._dap_svd_patched = True

    original_run = SVDLoader.run

    def run(self):
        try:
            original_run(self)
        except Exception as exc:
            LOG.warning('failed to load SVD: %s', exc)

    SVDLoader.run = run
