#!/usr/bin/env python
# coding: utf-8

import pathlib
import tkinter as tk
import tkinter.ttk as ttk
from pygubu.widgets.pathchooserinput import PathChooserInput
import threading
import datetime
import os,sys
import webbrowser
from pyocd.core.helpers import ConnectHelper
from pyocd.flash.file_programmer import FileProgrammer
from pyocd.flash.eraser import FlashEraser
from pyocd.probe.aggregator import PROBE_CLASSES
# from pyocd.probe.cmsis_dap_probe import CMSISDAPProbe
# PROBE_CLASSES["cmsisdap"] = CMSISDAPProbe
from pyocd.probe.stlink_probe import StlinkProbe
PROBE_CLASSES["stlink"] = StlinkProbe

bin_path = ''
yaml_path = ''
version = '1.0.0'
author = 'USTHzhanglu@outlook.com'
copyright = 'USTHzhanglu'
show_about = (
'dap_download\r\n\r\n'+
'Version:%s\r\n'%version+
'Author:%s\r\n'%author+
'Copyright@%s'%copyright
)


def download_bin():
    is_err_download = False
    try:
        with ConnectHelper.session_with_chosen_probe() as session:
            target = session.target
            # Load firmware into device.
            FileProgrammer(session,progress = None).program(bin_path)
            # Reset, run.
            target.reset_and_halt()
            target.resume()
    except Exception as r:
        app.out.insert('end',r)
        app.out.insert('end',"\r\n")
        is_err_download = True
    finally:
        if is_err_download == False:
            app.out.insert('end',"-------------烧录成功--------------\r\n")
        else:
            app.out.insert('end',"-------------烧录失败--------------\r\n")
        app.out.insert('end',datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S'))
        app.out.insert('end','\r\n')
        
def erase_bin():
    is_err_erase= False
    try:
        with ConnectHelper.session_with_chosen_probe() as session:
            FlashEraser(session,mode = FlashEraser.Mode.CHIP).erase()
    except Exception as r:
        app.out.insert('end',r)
        app.out.insert('end',"\r\n")
        is_err_erase = True
    finally:
        if is_err_erase == False:
            app.out.insert('end',"-------------擦除完毕--------------\r\n")
        else:
            app.out.insert('end',"-------------擦除失败--------------\r\n")
        app.out.insert('end',datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S'))
        app.out.insert('end','\r\n')


class std2tk(object): 
    def __init__(self):
        self._buff = ""
    def write(self, out_stream): 
        app.out.insert('end',out_stream)
    def flush(self): 
        self._buff = ""


class PyocdApp:
    def __init__(self, master=None):
        # build ui
        self.toplevel1 = tk.Tk() if master is None else tk.Toplevel(master)
        #menu
        self.menu1 = tk.Menu(self.toplevel1,tearoff = True)

        self.mi_download = 1
        self.menu1.add('command', font='{宋体} 9 {}', label='获取固件')
        _wcmd = lambda itemid="download": self.menucallback(itemid)
        self.menu1.entryconfigure(self.mi_download, command=_wcmd)
        self.toplevel1.configure(menu=self.menu1)
        
        self.mi_help = 2
        self.menu1.add('command', font='{宋体} 9 {}', label='帮助')
        _wcmd = lambda itemid="help": self.menucallback(itemid)
        self.menu1.entryconfigure(self.mi_help, command=_wcmd)
        
        self.mi_about = 3
        self.menu1.add('command', font='{宋体} 9 {}', label='关于')
        _wcmd = lambda itemid="about": self.menucallback(itemid)
        self.menu1.entryconfigure(self.mi_about, command=_wcmd)
        self.toplevel1.configure(menu=self.menu1)
        
        
        self.gui = ttk.Frame(self.toplevel1)
        self.labelframe1 = ttk.Labelframe(self.gui)
        self.binchooserinput = PathChooserInput(self.labelframe1)
        self.binchooserinput.configure(state='normal', title='bin文件', type='file')
        self.binchooserinput.pack(fill='x', side='top')
        self.labelframe1.configure(text='选择Bin文件')
        self.labelframe1.pack(fill='x', side='top')
        
        self.labelframe2 = ttk.Labelframe(self.gui)
        self.pathchooserinput1 = PathChooserInput(self.labelframe2)
        self.pathchooserinput1.configure(state='normal', title='bin文件', type='directory')
        self.pathchooserinput1.pack(fill='x', side='top')
        self.labelframe2.configure(text='选择配置文件所在文件夹')
        self.labelframe2.pack(fill='x', side='top')
        self.frame1 = ttk.Frame(self.gui)

        self.out = tk.Text(self.frame1)
        self.out.configure(background='#000000',font='{宋体} 10 {}', foreground='#00ff00', height='9', relief='groove')
        self.out.configure(width='50')
        self.out.pack(anchor='center', expand='true', fill='both', side='top')
        
        self.erase = tk.Button(self.frame1)
        self.erase.configure(relief='groove', text='擦除程序')
        self.erase.pack(anchor='center', ipadx='15', padx='20', pady='10', side='left')
        self.erase.configure(command=self.erasechip)
        self.start = tk.Button(self.frame1)
        self.start.configure(relief='groove', text='开始下载')
        self.start.pack(anchor='center', ipadx='15', padx='20', pady='10', side='right')
        self.start.configure(command=self.download)
        
        self.frame1.pack(anchor='center', expand='true', fill='both', side='bottom')
        self.gui.configure(height='480', relief='flat', width='320')
        self.gui.pack(anchor='center', side='top')
        self.gui.pack_propagate(0)
        self.toplevel1.configure(height='480', width='320')
#        self.toplevel1.geometry('320x480')
#自适应屏幕居中
        self.toplevel1.geometry('320x480' + '+'
                            + str((self.toplevel1.winfo_screenwidth() - 320) // 2) + '+'
                            + str((self.toplevel1.winfo_screenheight() - 480) // 2 - 18))

        self.toplevel1.title('dap_download')
        self.toplevel1.resizable(False, False)
        self.toplevel1.attributes('-alpha',0.95)        
        
        # Main widget
        self.mainwindow = self.toplevel1
        self.mainwindow.attributes('-topmost', 1)#强制前台
        self.mainwindow.after_idle(self.mainwindow.attributes,'-topmost',False)
        self.mainwindow.focus_force()
        self.mainwindow.bind('<Key>',self.press_key)
    
    def run(self):
        self.mainwindow.mainloop()
        
        
    def menucallback(self, itemid):
        if itemid == 'about':
            tk.messagebox.showinfo(title="关于",message = show_about)
        elif itemid =='help':
            webbrowser.open('https://github.com/USTHzhanglu/dap_download/readme.md',new=0)
        elif itemid =='download':  
            if tk.messagebox.askokcancel("download", "是否获取固件?"):
                webbrowser.open('https://github.com/USTHzhanglu/dap_download',new=0)
        
    def download(self):
        global bin_path
        global yaml_path
        bin_path = self.binchooserinput.cget('path')
        yaml_path = self.pathchooserinput1.cget('path')
        if (bin_path and yaml_path):
            self.out.delete('1.0','end')
            self.out.insert('end',"bin:%s"%(bin_path))
            self.out.insert('end','\r\n')
            self.out.insert('end',"dir:%s"%(yaml_path))
            self.out.insert('end','\r\n')
            
            os.chdir(yaml_path)
            
            self.out.insert('end','-------------开始烧录--------------\r\n')
            self.out.insert('end',datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S'))
            self.out.insert('end','\r\n')
            download = threading.Thread(target=download_bin)
            if download.is_alive() is False:
                download.start() 
            else:
                self.out.insert('end','烧录失败\r\n')  
        else :
            self.out.delete('1.0','end')
            self.out.insert('end','请选择有效的bin文件或文件夹路径\r\n')
            
    def erasechip(self):
        global yaml_path
        yaml_path = self.pathchooserinput1.cget('path')
        if yaml_path:
            self.out.delete('1.0','end')
            self.out.insert('end',"dir:%s"%(yaml_path))
            self.out.insert('end','\r\n')
            os.chdir(yaml_path)
            
            if tk.messagebox.askokcancel("erase", "你确定要擦除吗?"):
                self.out.insert('end','-------------开始擦除--------------\r\n')
                self.out.insert('end',datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S'))
                self.out.insert('end','\r\n')
                erase = threading.Thread(target=erase_bin)
                if erase.is_alive() is False:
                    erase.start() 
                else:
                    self.out.insert('end','擦除失败\r\n')
        else :
            self.out.delete('1.0','end')
            self.out.insert('end','请选择有效的文件夹路径\r\n')
    
            
    def press_key(self,event):
        key_index = event.keycode
        if key_index in [13,32]:
            self.download()
        elif key_index == 27:
            if tk.messagebox.askokcancel("Quit", "你确定要退出吗?"):
                self.mainwindow.destroy()

if __name__ == '__main__':
    app = PyocdApp()
    _std = std2tk()
    sys.stdout = _std
    app.run()


