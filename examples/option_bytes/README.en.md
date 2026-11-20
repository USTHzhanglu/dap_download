# Option Bytes Descriptor (Writer YAML)

[中文](./README.md) | **English**

This folder contains an example writer YAML. A descriptor tells the tool how one chip's option bytes are read and written:

- which SVD fields may be modified;
- the common write flow (unlock → erase → program → lock);
- fixed action buttons (AUTO, e.g. Erase).

No chip descriptors are built into the application. Put YAML files in the `option_bytes/` folder, or import them with **Import...** in the Option Bytes window.

## Where the files live

| How it runs | Folder |
| --- | --- |
| Packaged exe | `option_bytes/` next to the exe |
| Running from source | `src/ob/option_bytes/` |
| Environment override | `DAP_OB_DIR=<folder>` |

- File names are arbitrary; every `*.yaml` in the folder is scanned.
- **Import...** copies the selected file as `<device>.yaml`.
- Use one YAML per chip; do not put multiple chips in one file.

## Matching rules

```yaml
device: AT32F425
from_pack: ArteryTek.AT32F425_DFP@2.1.5
```

- `from_pack` prefers an exact match with the pack reference shown in Pack Manager (including the version).
- If no exact match exists, a descriptor with the same vendor/pack name but a different version is used, and the window shows a version-mismatch note.
- A version difference may change the register layout; verify it before writing.
- `device` must belong to that pack's device family (e.g. AT32F425 covers AT32F425C6U7).
- With no match, the Option Bytes window stays read-only.

## Full structure

```yaml
device: AT32F425
from_pack: ArteryTek.AT32F425_DFP@2.1.5
verified: false          # set true after hardware verification; false warns on write
reset_after: true        # reset the target after the flow

# Option-byte data block: usd_write writes these 16-bit words
block:
  words:
    - {name: fap,   addr: 0x1FFFF800, default: 0xA5}
    - {name: ssb,   addr: 0x1FFFF802, default: 0x0000}
    - {name: data0, addr: 0x1FFFF804}
    - {name: data1, addr: 0x1FFFF806}

# Fixed actions: every key becomes a button; sequences cannot use field values
auto:
  erase:
    - {write: FLASH_UNLOCK, value: 0x45670123}
    - {write: FLASH_UNLOCK, value: 0xCDEF89AB}
    - {wait: FLASH_STS, mask: 0x1, eq: 0, timeout_ms: 1000}
    - {set_bits: FLASH_CTRL, mask: 0x2060}
    - {wait: FLASH_STS, mask: 0x1, eq: 0, timeout_ms: 1000}
    - {clear_bits: FLASH_CTRL, mask: 0x60}

# Interactive write flow: executed by Apply
flow:
  unlock: [...]
  erase:  [...]
  program:
    - {usd_write: true}
  lock:   [...]

# Writable fields; fields not listed here are read-only in the UI
fields:
  nBOOT1:
    program:
      - {usd_bit: {word: ssb, bit: 4}}
  USER_D0:
    program:
      - {usd_byte: {word: data0}}
```

Register and field names come from the chip's own SVD. `FLASH_UNLOCK`, `FLASH_CTRL`, `FLASH_STS`, etc. are **not universal** and differ between vendors and families.

## Operations (ops)

These operations are available in `flow`, `auto`, and `fields.*.program`:

| op | Parameters | Description |
| --- | --- | --- |
| `write` | register, `value` | 32-bit register write |
| `write16` | register/address, `value` | 16-bit write |
| `write_mem` | `addr`, `value` | 32-bit write by address |
| `set_bits` | register, `mask` | read-modify-write, set bits |
| `clear_bits` | register, `mask` | read-modify-write, clear bits |
| `wait` | register, `mask`, `eq`, `timeout_ms` | poll until `(reg & mask) == eq` |
| `assert` | register, `mask`, `eq` | check `(reg & mask) == eq` |
| `delay_ms` | integer | delay |
| `reset` | none | reset the target |
| `usd_write` | `true` | write `block.words` (encoding is implemented by the executor) |

> The encoding of `block.words` is chip-specific; see the comments in the example YAML.

Values may be integers or `$variables`:

- register names are resolved to SVD addresses;
- `$FIELD` is the current UI value;
- `$FIELD_CHOICE` is an enum's raw value, e.g. `$FAP_UNPROTECTED`.

## AUTO section

```yaml
auto:
  erase: [...]
  unlock: [...]
```

- Every key becomes a button (`erase` → **Erase**).
- Sequences are fixed and do not take field values: use them for erase, unlock, factory reset, etc.
- A YAML may define several AUTO buttons; the UI shows at most 4 per row.

## Field fragments

Only fields listed under `fields` are writable. Each field uses a `program` fragment to encode its value into `block.words`:

| Fragment | Effect |
| --- | --- |
| `usd_bit` | write the field value as one bit at `bit` of `word` |
| `usd_byte` | write the field value as the low 8 bits of `word` |
| `usd_enum` | write the enum's raw value into `word` |
| `usd_const` | write a fixed value into `word` |

Execution order: `flow.unlock` → `flow.erase` → all field fragments → `flow.program` (usually with `usd_write`) → `flow.lock`.

### Enum fields

```yaml
fields:
  FAP:
    enum:
      unprotected: 0xA5
      low: 0xFFFF
      high: 0xCC
    read:                       # read-back state → enum choice
      - {FAP: 0, value: unprotected}
      - {FAP: 1, FAP_HL: 0, value: low}
      - {FAP: 1, FAP_HL: 1, value: high}
    warning:
      high: High FAP disables SWD and may be unrecoverable.
    program:
      - {usd_enum: {word: fap}}
```

- `enum` values are the raw hardware values;
- `read` maps read-back register/field values to the current choice;
- `warning` asks for confirmation before writing that choice;
- fields without `enum` are treated as plain numbers.

## Generated template and Import

The first time Option Bytes is opened for a chip without a matching descriptor, a default skeleton is generated automatically and its path is shown in the window hint:

- `device` and `from_pack` are filled in;
- comments list the chip's flash registers and option-byte field candidates;
- `flow` / `auto` / `fields` are empty with TODOs; unlock keys, erase bits and block layout are never guessed.

Edit that generated file and click **Read** / **Apply** — it is reloaded automatically.

Use **Import...** only to load a descriptor prepared by someone else (or downloaded from a shared library); you can also drag a `.yaml` file onto the main window to Import

## Adding a new chip

1. Install the CMSIS-Pack and confirm its reference (with version) in Pack Manager.
2. Select the chip and open **Option Bytes**: without a descriptor it is read-only but shows the SVD fields.
3. The first open generates a skeleton automatically; alternatively copy `examples/option_bytes/at32f425.yaml`.
4. Fill in `device` and `from_pack`.
5. Write `flow` (unlock, erase, program, lock) and `block.words` from the reference manual.
6. Add only verified `fields` fragments; keep `verified: false`.
7. Edit the generated file or Import a descriptor.
8. Verify on hardware:
   - Read back the values;
   - Run an AUTO action such as Erase;
   - Apply one field and confirm read-back;
   - Test the failure/recovery path.
9. Set `verified: true` after verification passes.

## Safety

- Only fields with a `program` fragment become writable; everything else is read-only.
- High protection levels (e.g. high FAP) may disable SWD; a warning is shown first.
- `verified: false` warns every write that it may brick the chip.
- YAML can write arbitrary registers and memory: never load descriptors from untrusted sources.
- Erase/protection granularity follows the reference manual; `usd_write` only fits controllers that write the block word by word.
