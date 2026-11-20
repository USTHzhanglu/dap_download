# dap_downloader

<div align="center">

基于 Tkinter + pyOCD 的可视化 MCU 烧录工具

**中文** | [English](./README.en.md)

<br>

<img src="res/main.png" alt="Main UI" width="600"/>

</div>

## 致谢

- **[pyOCD](https://github.com/pyocd/pyOCD)**：开源 MCU 调试与下载库，基本支持所有芯片。
- **[pygubu](https://github.com/alejandroautalan/pygubu)**：易用的 Tkinter GUI 设计器（本项目已不再使用）。感谢它在无 AI 时代帮助初学者。
- **[DeepSeek](https://www.deepseek.com/)**：本项目开发中的 AI 助手。

## 功能

- 支持 pyOCD 支持的各种调试器
- 内置算法 + 自装 CMSIS-Pack 芯片
- SWD / JTAG，频率可调
- 支持 bin / hex / elf / srec，全片擦除
- 集成 Pack 管理器
- 选项字读写（YAML 描述文件）
- 支持拖放导入

## 使用

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r packaging\requirements.txt
```

```cmd
python src\dap_downloader.py
```

打包（目录模式）：

```cmd
pyinstaller packaging\dap_downloader.spec
```

**烧录**：选探针 → 选芯片 → 选固件（bin 需设地址）→ 选接口与速度 → Program Device。

**擦除**：选芯片 → Erase Chip → 确认。

Pack 管理与拖放均在界面内完成。

## 选项字（Option Bytes）

部分芯片的选项字寄存器可以通过 pack 的 SVD 自动识别，配合 `option_bytes/` 下的 YAML 描述文件进行读写。

| 状态 | 说明 |
| --- | --- |
| 未导入描述 | 显示全部选项字字段，但全部只读 |
| 导入描述后 | YAML 中实现（声明了 program 片段）的字段可编辑，其余保持只读 |
| AUTO 动作 | YAML 中 `auto` 段定义的固定操作（如 Erase）以按钮显示，点击执行 |

<div>
<img src="res/option_bytes_readonly.png" alt="Option Bytes (read-only)" width="420"/>
<img src="res/option_bytes_writable.png" alt="Option Bytes (writable)" width="420"/>
</div>

描述文件放在程序目录的 `option_bytes/` 下，通过 `from_pack` + `device` 匹配芯片，文件名任意。示例见 [examples/option_bytes/at32f425.yaml](examples/option_bytes/at32f425.yaml)。窗口左下角的 **Import...** 可加载文件并复制到 `option_bytes/`。

> J-Link 驱动建议 ≤ 9.12。
