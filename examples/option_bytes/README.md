# 选项字描述文件（Writer YAML）

**中文** | [English](./README.en.md)

本目录存放 writer YAML 示例。YAML 描述一颗芯片的选项字怎么读、怎么写：

- 哪些 SVD 字段允许修改；
- 公共写流程（解锁 → 擦除 → 编程 → 上锁）；
- 固定动作按钮（AUTO，如 Erase）。

程序运行时不会内置任何芯片的 YAML，需要把描述文件放到 `option_bytes/` 目录，或通过 Option Bytes 窗口的 **Import...** 导入。

## 文件放哪里

| 运行方式 | 目录 |
| --- | --- |
| 打包后的 exe | exe 所在目录下的 `option_bytes/` |
| 源码运行 | `src/ob/option_bytes/` |
| 环境变量覆盖 | `DAP_OB_DIR=<目录>` |

- 文件名任意，程序会扫描目录下所有 `*.yaml`；
- **Import...** 会把选中的文件复制为 `<device>.yaml`；
- 一个芯片对应一份 YAML，不要在一个文件里写多颗芯片。

## 匹配规则

```yaml
device: AT32F425
from_pack: ArteryTek.AT32F425_DFP@2.1.5
```

- `from_pack` 优先与 Pack Manager 里的 pack 引用 **完全一致**（包含版本号）；
- 找不到完全一致时，会匹配同 vendor/pack 名称、版本不同的描述文件，并在窗口显示版本差异提示；
- 版本差异可能改变寄存器布局，写入前需自行确认；
- `device` 必须属于该 pack 中的器件系列（如 AT32F425 覆盖 AT32F425C6U7 等型号）；
- 匹配不到时，Option Bytes 窗口只读。

## 完整结构

```yaml
device: AT32F425
from_pack: ArteryTek.AT32F425_DFP@2.1.5
verified: false          # 是否已上板验证；false 时写入前会警告
reset_after: true        # 流程结束后是否复位

# 选项字数据块：usd_write 会逐个写入这些 16 位字
block:
  words:
    - {name: fap,   addr: 0x1FFFF800, default: 0xA5}
    - {name: ssb,   addr: 0x1FFFF802, default: 0x0000}
    - {name: data0, addr: 0x1FFFF804}
    - {name: data1, addr: 0x1FFFF806}

# 固定动作：每个 key 在界面上是一个按钮，序列里不能引用字段值
auto:
  erase:
    - {write: FLASH_UNLOCK, value: 0x45670123}
    - {write: FLASH_UNLOCK, value: 0xCDEF89AB}
    - {wait: FLASH_STS, mask: 0x1, eq: 0, timeout_ms: 1000}
    - {set_bits: FLASH_CTRL, mask: 0x2060}
    - {wait: FLASH_STS, mask: 0x1, eq: 0, timeout_ms: 1000}
    - {clear_bits: FLASH_CTRL, mask: 0x60}

# 交互写入流程：Apply 时执行
flow:
  unlock: [...]
  erase:  [...]
  program:
    - {usd_write: true}
  lock:   [...]

# 可写字段；没出现在这里的字段在界面上只读
fields:
  nBOOT1:
    program:
      - {usd_bit: {word: ssb, bit: 4}}
  USER_D0:
    program:
      - {usd_byte: {word: data0}}
```

## 操作（op）参考

`flow`、`auto`、`fields.*.program` 都可以使用下面的通用操作：

| op | 参数 | 说明 |
| --- | --- | --- |
| `write` | 寄存器名, `value` | 32 位写寄存器 |
| `write16` | 寄存器名/地址, `value` | 16 位写 |
| `write_mem` | `addr`, `value` | 按地址写 32 位 |
| `set_bits` | 寄存器名, `mask` | 读-改-写，置位 |
| `clear_bits` | 寄存器名, `mask` | 读-改-写，清位 |
| `wait` | 寄存器名, `mask`, `eq`, `timeout_ms` | 轮询直到 `(reg & mask) == eq` |
| `assert` | 寄存器名, `mask`, `eq` | 校验 `(reg & mask) == eq` |
| `delay_ms` | 整数 | 延时 |
| `reset` | 无 | 目标复位 |
| `usd_write` | `true` | 把 `block.words` 写入（编码由执行器实现） |

> `block.words` 的编码方式与芯片相关，具体以示例 YAML 中的说明为准。

数值参数可以写整数，也可以写 `$变量`：

- 寄存器名会自动解析为 SVD 地址；
- `$字段名` 是当前界面值；
- `$字段名_枚举值` 是 YAML 里枚举的原始值，例如 `$FAP_UNPROTECTED`。

## AUTO 区

```yaml
auto:
  erase: [...]
  unlock: [...]
```

- 每个 key 会生成一个按钮（`erase` → **Erase**）；
- 序列是固定的，不接收字段值，适合擦除、解锁、恢复出厂等动作；
- 同一份 YAML 可以有多个 AUTO 按钮，界面每行最多 4 个。

## 字段片段

只有 `fields` 中列出的字段可写。每个字段用 `program` 片段描述如何把自己的值编码进 `block.words`：

| 片段 | 作用 |
| --- | --- |
| `usd_bit` | 把字段值作为 1 个 bit 写入 `word` 的 `bit` 位 |
| `usd_byte` | 把字段值作为低 8 位写入 `word` |
| `usd_enum` | 把枚举选择对应的原始值写入 `word` |
| `usd_const` | 直接向 `word` 写入固定值 |

执行顺序：`flow.unlock` → `flow.erase` → 所有字段片段 → `flow.program`（通常包含 `usd_write`）→ `flow.lock`。

### 枚举字段

```yaml
fields:
  FAP:
    enum:
      unprotected: 0xA5
      low: 0xFFFF
      high: 0xCC
    read:                       # 回读状态 → 枚举
      - {FAP: 0, value: unprotected}
      - {FAP: 1, FAP_HL: 0, value: low}
      - {FAP: 1, FAP_HL: 1, value: high}
    warning:
      high: High FAP disables SWD and may be unrecoverable.
    program:
      - {usd_enum: {word: fap}}
```

- `enum` 的 value 是硬件原始值；
- `read` 用寄存器/字段回读值反推当前枚举；
- `warning` 在写入该枚举值前弹确认；
- 没有 `enum` 的字段按普通数值处理。

## 从 SVD 生成模板

第一次为某颗芯片打开 **Option Bytes**、且 `option_bytes/` 中没有匹配描述时，程序会自动生成一份骨架 YAML，并在窗口提示区显示路径：

- 自动写入 `device`、`from_pack`；
- 注释里列出该芯片的 flash 寄存器地址和选项字字段候选；
- `flow` / `auto` / `fields` 只给空结构和 TODO，不会猜测解锁值、擦除位和块布局。

注意：`FLASH_UNLOCK`、`FLASH_CTRL`、`FLASH_STS` 等名字来自**当前芯片的 SVD**，不同厂商/系列并不相同；模板只是减少查寄存器名的工作，具体序列仍需按手册填写。

生成后直接编辑该文件；点 **Read / Apply** 时会自动重新加载，不需要 Import。

**Import...** 只用于导入别人生成/分享的描述文件；也可以直接把 `.yaml` 拖到主窗口进行导入

```text
第一次点 Option Bytes → 自动生成 option_bytes/<device>.yaml
→ 编辑 → Read/Apply 自动生效
```

## 新增一颗芯片的步骤

1. 安装对应 CMSIS-Pack，在 Pack Manager 中确认 pack 引用（含版本）；
2. 选中芯片，打开 **Option Bytes**：没有匹配描述时窗口只读，但能显示 SVD 里的选项字字段；
3. 首次打开 Option Bytes 会自动生成骨架，或复制 `examples/option_bytes/at32f425.yaml`；
4. 填写 `device`、`from_pack`；
5. 按参考手册写 `flow`（解锁、擦除、编程、上锁）和需要的 `block.words`；
6. 先只加已经确认的 `fields` 片段，`verified` 保持 `false`；
7. 编辑自动生成的 `option_bytes/<device>.yaml`（或从外部 Import），Read/Apply 时自动重新加载；
8. 上板验证：
   - Read 确认回读值；
   - 点 AUTO（如 Erase）确认擦除；
   - Apply 写入单个字段，确认回读一致；
   - 测试失败恢复路径；
9. 验证通过后把 `verified` 改成 `true`。

## 安全提醒

- 只有声明了 `program` 的字段才可写，其他字段只读；
- 高等级保护（如 high FAP）可能禁用 SWD，写入前会弹警告；
- `verified: false` 时每次写入都会提示“可能变砖”；
- YAML 可以写任意寄存器和内存，**不要加载来源不明的描述文件**；
- 写保护/擦除粒度以手册为准；`usd_write` 的适用范围见具体芯片 YAML 的说明。
