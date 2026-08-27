## 环境准备

Python 3.9 及以上(当前依赖锁定的最低支持版本,本项目在 Python 3.14 上开发测试)。

Pyocd、Pyinstaller 和 Pygubu 理论上支持所有操作系统,但是这里只在 Windows10 22H2 上测试通过。



## Instructions

These instructions assume that you already have Python installed:

The following script shows the basic steps that one must follow:

```cmd
# Setup a virtualenv and install dependencies
python -m venv venv
venv\Scripts\activate
pip install -r packaging\requirements.txt

# Package as a directory (onedir) build; output lands in .\dist\<name>\
pyinstaller packaging\dap_downloader.spec
```

The build produces a folder `.\.\dist\<name>\` containing the executable and its dependencies (a directory-mode / onedir build, not a single file). Distribute that folder as-is: the `.exe` plus its `_internal` folder must be kept together.
