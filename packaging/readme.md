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

# Create single-file executables
pyinstaller packaging\dap_downloader.spec
```

In ./dist folder, there will be a single executable file per tool which is ready to use or distribute it to other library.
