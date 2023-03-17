## 首先感谢以下项目

[pyOCD](https://github.com/pyocd/pyOCD)：一个开源的mcu调试以及下载项目，基本支持所有芯片

[pygubu](https://github.com/alejandroautalan/pygubu)：一个开源宜用的GUI draw项目，支持实时浏览界面

## 项目介绍

本项目是基于tkinter，pygubu和pyOCD设计的一个GUI，可以通过DAP-LINK直接下载固件。使用者只需要提供芯片的pack包，即可下载hex，elf以及bin文件。

## 使用说明
### 烧录
1. 选择下载文件
2. 选择芯片配置文件所在文件夹
3. 开始下载
### 擦除
1. 选择芯片配置文件所在文件夹
2. 擦除程序
注：目前只支持全盘擦除
