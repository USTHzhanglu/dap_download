# coding: utf-8
"""Generic operation validation and register address resolution."""

from __future__ import annotations

from typing import Any, Dict, List


class ObOpsError(Exception):
    """Invalid register map / operation."""


# op -> required parameters besides the op's own value
OPS = {
    'write': (),
    'write_mem': ('addr', 'value'),
    'write16': ('value',),
    'set_bits': ('mask',),
    'clear_bits': ('mask',),
    'wait': ('mask', 'eq'),
    'delay_ms': (),
    'assert': ('mask', 'eq'),
    'reset': (),
}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def resolve_regs(regs: Dict[str, Any]) -> Dict[str, int]:
    resolved: Dict[str, int] = {}
    pending = dict(regs)
    for _ in range(len(pending) + 1):
        if not pending:
            break
        progressed = False
        for name in list(pending):
            value = pending[name]
            if _is_int(value):
                resolved[name] = int(value)
                del pending[name]
                progressed = True
            elif isinstance(value, dict) and 'at' in value:
                parent = value['at']
                if _is_int(parent):
                    base = int(parent)
                elif isinstance(parent, str) and parent in resolved:
                    base = resolved[parent]
                else:
                    continue
                offset = value.get('offset', 0)
                if not _is_int(offset):
                    continue
                resolved[name] = base + int(offset)
                del pending[name]
                progressed = True
        if not progressed:
            break
    if pending:
        raise ObOpsError('Cannot resolve regs (dangling at reference): %s'
                         % ', '.join(sorted(pending)))
    return resolved


def validate_sequence(sequence: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(sequence, list) or not sequence:
        return ['sequence must be a non-empty list']
    for index, step in enumerate(sequence):
        if not isinstance(step, dict):
            errors.append('sequence[%d] must be a mapping' % index)
            continue
        op_names = [key for key in step if key in OPS]
        if len(op_names) != 1:
            errors.append('sequence[%d] must contain exactly one op (%s)'
                          % (index, '/'.join(sorted(OPS))))
            continue
        op = op_names[0]
        op_value = step[op]
        if op in ('write', 'write16', 'wait', 'assert'):
            if not (isinstance(op_value, str) or _is_int(op_value)):
                errors.append('sequence[%d] %s value must be a register name' % (index, op))
            if op in ('write', 'write16'):
                value = step.get('value')
                if not (_is_int(value) or isinstance(value, str)):
                    errors.append('sequence[%d] %s.value must be an integer or $variable'
                                  % (index, op))
            else:
                for param in ('mask', 'eq'):
                    if not _is_int(step.get(param)):
                        errors.append('sequence[%d] %s.%s must be an integer'
                                      % (index, op, param))
                if op == 'wait' and 'timeout_ms' in step \
                        and not _is_int(step['timeout_ms']):
                    errors.append('sequence[%d] timeout_ms must be an integer' % index)
        elif op == 'write_mem':
            for param in ('addr', 'value'):
                if param not in step:
                    errors.append('sequence[%d] write_mem is missing parameter %s'
                                  % (index, param))
                    continue
                value = step[param]
                if not (_is_int(value) or
                        (isinstance(value, str) and value.startswith('$'))):
                    errors.append('sequence[%d] write_mem.%s must be an integer or $variable'
                                  % (index, param))
        elif op in ('set_bits', 'clear_bits'):
            if not (isinstance(op_value, str) or _is_int(op_value)):
                errors.append('sequence[%d] %s value must be a register name' % (index, op))
            if not _is_int(step.get('mask')):
                errors.append('sequence[%d] %s.mask must be an integer' % (index, op))
        elif op == 'delay_ms':
            if not _is_int(op_value):
                errors.append('sequence[%d] delay_ms value must be an integer' % index)
    return errors
