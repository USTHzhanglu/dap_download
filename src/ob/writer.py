# coding: utf-8
"""YAML-driven option-byte writer: common flow + per-field program fragments."""

from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .catalog import resolve_regs, validate_sequence
from .descriptors import normalize, pack_key

FRAGMENT_OPS = ('usd_bit', 'usd_byte', 'usd_const', 'usd_enum')

def _app_dir():
    """Directory holding the program: exe dir when frozen, else the source dir."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def _default_dir() -> str:
    override = os.environ.get('DAP_OB_DIR')
    if override:
        return os.path.abspath(override)
    return os.path.join(_app_dir(), 'option_bytes')


@dataclass
class WriterSpec:
    device: str
    from_pack: str
    flow: Dict[str, List[Dict[str, Any]]]
    fields: Dict[str, Dict[str, Any]]
    auto: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    block: Optional[Dict[str, Any]] = None
    verified: bool = False
    reset_after: bool = True
    path: str = ''
    error: str = ''

    @property
    def valid(self) -> bool:
        return not self.error

    def matches(self, descriptor) -> bool:
        if pack_key(self.from_pack) != pack_key(descriptor.from_pack):
            return False
        wanted = {normalize(name) for name in descriptor.devices}
        wanted.add(normalize(descriptor.device))
        return normalize(self.device) in wanted

    def choice_for(self, field_name: str, values: Dict[str, int]) -> str:
        """Reverse-map register values to an enum choice (via read rules)."""
        entry = self.fields.get(field_name) or {}
        for rule in entry.get('read') or []:
            choice = rule.get('value')
            if choice is None:
                continue
            ok = True
            for key, expected in rule.items():
                if key == 'value':
                    continue
                if int(values.get(key, -1)) != int(expected):
                    ok = False
                    break
            if ok:
                return str(choice)
        return ''

    def enum_variables(self) -> Dict[str, int]:
        """Expose <FIELD>_<CHOICE> constants for flows like recover."""
        variables: Dict[str, int] = {}
        for name, entry in self.fields.items():
            for choice, value in (entry.get('enum') or {}).items():
                variables['%s_%s' % (name.upper(), str(choice).upper())] = int(value)
        return variables


def _validate_flow(section: str, ops: Any) -> List[str]:
    errors: List[str] = []
    if ops is None:
        return errors
    if not isinstance(ops, list):
        return ['flow.%s must be a list' % section]
    for index, step in enumerate(ops):
        if not isinstance(step, dict):
            errors.append('flow.%s[%d] must be a mapping' % (section, index))
            continue
        if 'usd_write' in step:
            continue
        errors.extend(
            'flow.%s[%d]: %s' % (section, index, msg)
            for msg in validate_sequence([step])
        )
    return errors


def _validate_fragments(field_name: str, ops: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(ops, list):
        return ['fields.%s.program must be a list' % field_name]
    for index, step in enumerate(ops):
        if not isinstance(step, dict):
            errors.append('fields.%s[%d] must be a mapping' % (field_name, index))
            continue
        if any(key in FRAGMENT_OPS for key in step):
            op = next(key for key in step if key in FRAGMENT_OPS)
            payload = step[op]
            if not isinstance(payload, dict):
                errors.append('fields.%s[%d].%s must be a mapping'
                              % (field_name, index, op))
                continue
            word = payload.get('word')
            if not isinstance(word, str) or not word:
                errors.append('fields.%s[%d].%s is missing word'
                              % (field_name, index, op))
            if op == 'usd_bit':
                bit = payload.get('bit')
                if not isinstance(bit, int) or not (0 <= bit <= 15):
                    errors.append('fields.%s[%d].usd_bit is missing a valid bit'
                                  % (field_name, index))
            if op == 'usd_const' and not isinstance(payload.get('value'), int):
                errors.append('fields.%s[%d].usd_const is missing an integer value'
                              % (field_name, index))
            continue
        errors.extend(
            'fields.%s[%d]: %s' % (field_name, index, msg)
            for msg in validate_sequence([step])
        )
    return errors


def _parse_spec(path: str) -> WriterSpec:
    try:
        with open(path, 'r', encoding='utf-8-sig') as handle:
            doc = yaml.safe_load(handle)
    except (OSError, yaml.YAMLError) as exc:
        return WriterSpec('', '', {}, {}, path=path, error='Read failed: %s' % exc)
    if not isinstance(doc, dict):
        return WriterSpec('', '', {}, {}, path=path, error='Top level must be a mapping')
    errors: List[str] = []
    device = str(doc.get('device') or '').strip()
    from_pack = str(doc.get('from_pack') or '').strip()
    if not device:
        errors.append('Missing device')
    if not from_pack:
        errors.append('Missing from_pack')
    flow = doc.get('flow')
    if not isinstance(flow, dict):
        errors.append('Missing flow')
        flow = {}
    for section in ('unlock', 'erase', 'program', 'lock', 'recover'):
        errors.extend(_validate_flow(section, flow.get(section)))
    auto = doc.get('auto') or {}
    if auto and not isinstance(auto, dict):
        errors.append('auto must be a mapping')
        auto = {}
    for section in ('unlock', 'erase', 'program', 'lock', 'recover'):
        errors.extend(_validate_flow('auto.%s' % section, auto.get(section)))
    fields = doc.get('fields') or {}
    if not isinstance(fields, dict):
        errors.append('fields must be a mapping')
        fields = {}
    parsed_fields: Dict[str, Dict[str, Any]] = {}
    for name, entry in fields.items():
        if isinstance(entry, dict):
            program = entry.get('program') or []
            enum_raw = entry.get('enum') or {}
            read_rules = entry.get('read') or []
            warning = entry.get('warning') or {}
        else:
            program = entry or []
            enum_raw, read_rules, warning = {}, [], {}
        errors.extend(_validate_fragments(str(name), program))
        enum: Dict[str, int] = {}
        if enum_raw:
            if not isinstance(enum_raw, dict):
                errors.append('fields.%s.enum must be a mapping' % name)
            else:
                for choice, value in enum_raw.items():
                    if not isinstance(value, int):
                        errors.append('fields.%s.enum.%s must be an integer'
                                      % (name, choice))
                    else:
                        enum[str(choice)] = int(value)
                if not enum:
                    errors.append('fields.%s.enum must not be empty' % name)
        if read_rules and not isinstance(read_rules, list):
            errors.append('fields.%s.read must be a list' % name)
            read_rules = []
        for rule in read_rules:
            if not isinstance(rule, dict) or 'value' not in rule:
                errors.append('fields.%s.read rule needs value' % name)
                break
        if warning and not isinstance(warning, dict):
            errors.append('fields.%s.warning must be a mapping' % name)
            warning = {}
        parsed_fields[str(name)] = {
            'program': list(program or []),
            'enum': enum,
            'read': list(read_rules or []),
            'warning': dict(warning or {}),
        }
    block = doc.get('block')
    if block is not None:
        words = block.get('words') if isinstance(block, dict) else None
        if not isinstance(words, list) or not words:
            errors.append('block.words must be a non-empty list')
        else:
            for item in words:
                if not isinstance(item, dict) \
                        or not isinstance(item.get('name'), str) \
                        or not isinstance(item.get('addr'), int):
                    errors.append('block.words items need name/addr')
                    break
                if 'default' in item and not isinstance(item['default'], int):
                    errors.append('block.words.default must be an integer')
                    break
    spec = WriterSpec(
        device=device,
        from_pack=from_pack,
        flow={key: list(value or []) for key, value in flow.items()
              if isinstance(value, list)},
        fields=parsed_fields,
        auto={key: list(value or []) for key, value in auto.items()
              if isinstance(value, list)},
        block=block if isinstance(block, dict) else None,
        verified=bool(doc.get('verified', False)),
        reset_after=bool(doc.get('reset_after', True)),
        path=path,
    )
    if errors:
        spec.error = '; '.join(errors)
    return spec


def load_writers(directory: Optional[str] = None) -> List[WriterSpec]:
    directory = os.path.abspath(directory or _default_dir())
    specs: List[WriterSpec] = []
    if not os.path.isdir(directory):
        return specs
    for name in sorted(os.listdir(directory)):
        if name.lower().endswith(('.yaml', '.yml')):
            specs.append(_parse_spec(os.path.join(directory, name)))
    return specs


def find_writer(descriptor, directory: Optional[str] = None) -> Optional[WriterSpec]:
    for spec in load_writers(directory):
        if spec.valid and spec.matches(descriptor):
            return spec
    return None


def _file_key(text: str) -> str:
    key = re.sub(r'[^A-Za-z0-9]+', '_', text or '').strip('_').lower()
    return key or 'device'


def install_writer(source_path: str, descriptor,
                   directory: Optional[str] = None) -> WriterSpec:
    """Validate a writer YAML, copy it into option_bytes/ and return it."""
    spec = _parse_spec(source_path)
    if not spec.valid:
        raise WriterError(spec.error)
    if not spec.matches(descriptor):
        raise WriterError('YAML does not match this device: %s / %s'
                          % (spec.device, spec.from_pack))
    target_dir = os.path.abspath(directory or _default_dir())
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, _file_key(spec.device) + '.yaml')
    if os.path.abspath(source_path) != target:
        import shutil
        shutil.copyfile(source_path, target)
    installed = _parse_spec(target)
    if not installed.valid:
        raise WriterError(installed.error)
    return installed


class WriterError(RuntimeError):
    pass


def _build_variables(programmer, descriptor, values):
    regs = programmer._read_regs(descriptor)
    merged = programmer._assemble(descriptor, values, regs)
    variables: Dict[str, Any] = dict(merged)
    for key, value in merged.items():
        if '_' in key:
            variables.setdefault(key.split('_', 1)[1], value)
    variables.update(values)
    return variables


def _operand(spec: Any, addresses, variables) -> int:
    if isinstance(spec, int) and not isinstance(spec, bool):
        return int(spec)
    if isinstance(spec, str):
        if spec.startswith('$'):
            key = spec[1:]
            if key in variables:
                return int(variables[key])
            raise WriterError('Undefined variable: %s' % spec)
        if spec in addresses:
            return int(addresses[spec])
        try:
            return int(spec, 0)
        except ValueError:
            pass
    raise WriterError('Cannot parse operand: %r' % (spec,))


def run_action(programmer, spec: WriterSpec, descriptor,
               action: str) -> Dict[str, Any]:
    """Run one fixed AUTO sequence (a UI button action, no computation)."""
    ops = spec.auto.get(action)
    if not ops:
        raise WriterError('Undefined AUTO action: %s' % action)
    session = programmer.session
    if session is None:
        raise WriterError('not connected')
    target = session.target
    addresses = resolve_regs(descriptor.regs or {})
    variables = _build_variables(programmer, descriptor, {})
    variables.update(spec.enum_variables())
    target.halt()
    try:
        for index, op in enumerate(ops, 1):
            if 'usd_write' in op:
                raise WriterError('AUTO action does not support usd_write: %s' % action)
            try:
                programmer._exec_step(index, op, addresses, variables, target)
            except Exception as exc:
                raise WriterError('%s step %d: %s' % (action, index, exc))
    finally:
        if spec.reset_after:
            try:
                target.reset_and_halt()
                target.resume()
            except Exception:
                pass
        else:
            try:
                target.resume()
            except Exception:
                pass
    return {}

def run_writer(programmer, spec: WriterSpec, descriptor,
               values: Dict[str, int], changed: List[str],
               choices: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Run common flow once, merging changed fields' program fragments."""
    session = programmer.session
    if session is None:
        raise WriterError('not connected')
    target = session.target
    addresses = resolve_regs(descriptor.regs or {})
    variables = _build_variables(programmer, descriptor, values)
    variables.update(spec.enum_variables())

    block = spec.block or {}
    words: Dict[str, Dict[str, int]] = {}
    for item in block.get('words') or []:
        words[str(item['name'])] = {
            'addr': int(item['addr']),
            'value': int(item.get('default', 0xFFFF)) & 0xFFFF,
        }
    enum_choices: Dict[str, str] = dict(choices or {})
    enum_values: Dict[str, int] = {}
    for field_name, entry in spec.fields.items():
        enum = entry.get('enum') or {}
        if not enum:
            continue
        choice = enum_choices.get(field_name)
        if not choice:
            choice = spec.choice_for(field_name, values) or next(iter(enum))
            enum_choices[field_name] = choice
        if choice not in enum:
            raise WriterError('Invalid enum value for field %s: %s' % (field_name, choice))
        enum_values[field_name] = int(enum[choice])

    def exec_ops(ops, where):
        for index, op in enumerate(ops, 1):
            if 'usd_write' in op:
                if not words:
                    raise WriterError('%s: usd_write but block.words is not defined' % where)
                ctrl = addresses.get('FLASH_CTRL')
                sts = addresses.get('FLASH_STS')
                # Same as the FLM ProgramPage: set USDPRGM, write ONE 16-bit
                # data word (hardware adds the complement), wait OBF, clear.
                for name, item in words.items():
                    if ctrl is not None:
                        value = int(target.read_memory(ctrl, 32)) | 0x10
                        target.write_memory(ctrl, value, 32)
                    target.write_memory(item['addr'], item['value'] & 0xFFFF, 16)
                    if sts is not None:
                        deadline = time.time() + 1.0
                        while True:
                            status = int(target.read_memory(sts, 32))
                            if not (status & 0x1):
                                break
                            if time.time() > deadline:
                                raise WriterError('%s: word %s OBF timeout'
                                                  % (where, name))
                            time.sleep(0.001)
                    if ctrl is not None:
                        value = int(target.read_memory(ctrl, 32)) & ~0x10
                        target.write_memory(ctrl, value, 32)
                continue
            try:
                programmer._exec_step(index, op, addresses, variables, target)
            except Exception as exc:
                raise WriterError('%s step %d: %s' % (where, index, exc))

    def exec_fragment(field_name):
        entry = spec.fields.get(field_name) or {}
        ops = entry.get('program') if isinstance(entry, dict) else entry
        for index, op in enumerate(ops or [], 1):
            try:
                if any(key in FRAGMENT_OPS for key in op):
                    frag = next(key for key in op if key in FRAGMENT_OPS)
                    payload = op[frag]
                    name = str(payload['word'])
                    item = words.get(name)
                    if item is None:
                        raise WriterError('Undefined word: %s' % name)
                    raw = payload.get('value')
                    value = _operand(raw, addresses, variables) if raw is not None \
                        else int(variables.get(field_name, 0))
                    if frag == 'usd_bit':
                        bit = int(payload['bit'])
                        if value & 1:
                            item['value'] |= (1 << bit)
                        else:
                            item['value'] &= ~(1 << bit)
                    elif frag == 'usd_byte':
                        item['value'] = (item['value'] & ~0xFF) | (value & 0xFF)
                    elif frag == 'usd_enum':
                        item['value'] = int(enum_values.get(field_name, 0xFFFF)) & 0xFFFF
                    else:  # usd_const
                        item['value'] = int(payload['value']) & 0xFFFF
                else:
                    programmer._exec_step(index, op, addresses, variables, target)
            except Exception as exc:
                raise WriterError('Field %s step %d: %s' % (field_name, index, exc))

    target.halt()
    try:
        exec_ops(spec.flow.get('unlock') or [], 'unlock')
        exec_ops(spec.flow.get('erase') or [], 'erase')
        # erase wipes the whole block, so every writable field is re-encoded
        # from its current UI value (not only the ones the user touched)
        for field_name in spec.fields:
            exec_fragment(field_name)
        exec_ops(spec.flow.get('program') or [], 'program')
        exec_ops(spec.flow.get('lock') or [], 'lock')
    finally:
        if spec.reset_after:
            try:
                target.reset_and_halt()
                target.resume()
            except Exception:
                pass
        else:
            try:
                target.resume()
            except Exception:
                pass

    new_values, _ = programmer.read(descriptor)
    mismatches = {
        name: (wanted, new_values.get(name))
        for name, wanted in values.items()
        if name in spec.fields and not (spec.fields.get(name) or {}).get('enum')
        and new_values.get(name) != wanted
    }
    choice_mismatches = {}
    for field_name, choice in enum_choices.items():
        actual = spec.choice_for(field_name, new_values)
        if actual != choice:
            choice_mismatches[field_name] = (choice, actual)
    return {'values': new_values, 'mismatches': mismatches,
            'choice_mismatches': choice_mismatches}
