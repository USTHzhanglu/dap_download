## 环境准备

pyOCD需要Python3.6版本及以上，这意味着本项目也至少需要Python3.6

Pyocd，Pyinstaller和Pygubu理论上支持所有操作系统，但是这里只在Windows10 22H2 上测试通过。



## Instructions

These instructions assume that you already have Python installed:

The following script shows the basic steps that one must follow:

```cmd
cd build
# Setup a virtualenv and install dependencies
python -m venv venv
venv\Scripts\activate
pip installer -r requirements.txt

# Create single-file executables
pyinstaller  dap_downloader.spec
```

In ./dist folder, there will be a single executable file per tool which is ready to use or distribute it to other library.