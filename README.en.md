# dap_downloader

<div align="center">

A visual MCU flash tool based on Tkinter + pyOCD

[中文](./README.md) | **English**

<br>

<img src="res/main.png" alt="Main UI" width="600"/>

</div>

## Thanks

- **[pyOCD](https://github.com/pyocd/pyOCD)**: an open-source MCU debug and download library that supports most chips.
- **[pygubu](https://github.com/alejandroautalan/pygubu)**: an easy-to-use Tkinter GUI designer (no longer used in this project). Our gratitude goes to it for helping beginners in the pre-AI era.
- **[DeepSeek](https://www.deepseek.com/)**: the AI assistant used during development.

## Features

- Supports pyOCD-supported debuggers
- Built-in algorithms + self-installed CMSIS-Pack chips
- SWD / JTAG with adjustable frequency
- bin / hex / elf / srec firmware, full-chip erase
- Built-in Pack manager
- Drag & drop support

## Usage

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r packaging\requirements.txt
```

```cmd
python src\dap_downloader.py
```

Package (directory mode):

```cmd
pyinstaller packaging\dap_downloader.spec
```

**Flash**: pick probe → pick chip → pick firmware (set address for bin) → pick interface & speed → Program Device.

**Erase**: pick chip → Erase Chip → confirm.

Pack management and drag & drop are handled in the GUI.

> Keep the J-Link driver at ≤ 9.12.
