#!/usr/bin/env python
# coding: utf-8

import ctypes
import sys
import threading
import webbrowser

import tkinter as tk
import tkinter.ttk as ttk
from pygubu.widgets.pathchooserinput import PathChooserInput

from core import Flasher
from version import __appname__, __version__, __author__, __copyright__

show_about = (
__appname__+'\r\n\r\n'+
'Version:%s\r\n'%__version__+
'Author:%s\r\n'%__author__+
'Copyright@%s'%__copyright__
)

DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


def _enable_dpi_awareness():
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

class std2tk(object): 
    def __init__(self,tk):
        self._buff = ""
        self.tk = tk
    def write(self, out_stream): 
        self.tk.down_progress+=1
        if(self.tk.down_progress>169):
            self.tk.down_progress = 169
        self.tk.out.edit_undo()
        progress = (int)(self.tk.down_progress/17*2)
        self.tk.out.insert('end','\r\n['+ \
                           progress*'='+\
                           (20 - progress)*' '+\
                           ']   %.2f%%\r\n'%(self.tk.down_progress/1.7))
    def flush(self): 
        pass

class PyocdApp:
    def __init__(self, master=None):
        _enable_dpi_awareness()
        self._flasher = Flasher(log=self._append_log)
        self.down_progress = 0

        # build ui
        self.toplevel1 = tk.Tk() if master is None else tk.Toplevel(master)
        self.toplevel1.withdraw()
        #menu
        self.menu1 = tk.Menu(self.toplevel1,tearoff = True)

        self.mi_scan = 1
        self.menu1.add('command', font='{宋体} 9 {}', label='扫描探针')
        _wcmd = lambda itemid="scan": self.menucallback(itemid)
        self.menu1.entryconfigure(self.mi_scan, command=_wcmd)
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

        self.out = tk.Text(self.frame1,undo=True,maxundo = 1)
        self.out.configure(background='#000000',font='{宋体} 10 {}', foreground='#00ff00', height='20', relief='groove')
        self.out.configure(width='42')
        self.out.pack(anchor='center', side='top')

        self.erase = tk.Button(self.frame1)
        self.erase.configure(relief='groove', text='擦除程序')
        self.erase.pack(anchor='center', ipadx='10p',
                        padx='13p', pady='7p', side='left')
        self.erase.configure(command=self.erasechip)
        self.start = tk.Button(self.frame1)
        self.start.configure(relief='groove', text='开始下载')
        self.start.pack(anchor='center', ipadx='10p',
                        padx='13p', pady='7p', side='right')
        self.start.configure(command=self.download)

        self.frame1.pack(anchor='center', side='bottom')
        self.gui.pack(anchor='center', side='top')
        self.toplevel1.update_idletasks()
        w = self.toplevel1.winfo_reqwidth()
        h = self.toplevel1.winfo_reqheight()
#自适应屏幕居中
        self.toplevel1.geometry('+%d+%d' % (
            (self.toplevel1.winfo_screenwidth() - w) // 2,
            (self.toplevel1.winfo_screenheight() - h) // 2 - 18))
        self.toplevel1.deiconify()

        self.toplevel1.title(__appname__)
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

    def _append_log(self, msg):
        self.out.insert('end', msg)
        self.out.insert('end', '\r\n')

    def menucallback(self, itemid):
        if itemid == 'about':
            tk.messagebox.showinfo(title="关于",message = show_about)
        elif itemid =='help':
            webbrowser.open('https://github.com/USTHzhanglu/dap_download/blob/main/readme.md',new=0)
        elif itemid =='scan':
            self.scan_probe()      

    def download(self):
        bin_path = self.binchooserinput.cget('path')
        yaml_path = self.pathchooserinput1.cget('path')
        self.down_progress = 0
        if (bin_path and yaml_path):
            self.out.delete('1.0','end')
            self.out.insert('end',"bin:%s"%(bin_path))
            self.out.insert('end','\r\n')
            self.out.insert('end',"dir:%s"%(yaml_path))
            self.out.insert('end','\r\n')
            self.out.edit_separator()
            threading.Thread(target=self._flasher.download,
                             args=(bin_path, yaml_path), daemon=True).start()
        else :
            self.out.delete('1.0','end')
            self.out.insert('end','请选择有效的bin文件或文件夹路径\r\n')
            
    def erasechip(self):
        yaml_path = self.pathchooserinput1.cget('path')
        if yaml_path:
            self.out.delete('1.0','end')
            self.out.insert('end',"dir:%s"%(yaml_path))
            self.out.insert('end','\r\n')
            if tk.messagebox.askokcancel("erase", "你确定要擦除吗?"):
                threading.Thread(target=self._flasher.erase,
                                 args=(yaml_path,), daemon=True).start()
        else :
            self.out.delete('1.0','end')
            self.out.insert('end','请选择有效的文件夹路径\r\n')

    def scan_probe(self):
        self.out.delete('1.0','end')
        self.out.insert('end','-------------扫描探针--------------\r\n')
        threading.Thread(target=self._flasher.scan_probes, daemon=True).start()
    
            
    def press_key(self,event):
        key_index = event.keycode
        if key_index in [13,32]:
            self.download()
        elif key_index == 27:
            if tk.messagebox.askokcancel("Quit", "你确定要退出吗?"):
                self.mainwindow.destroy()


if __name__ == '__main__':
    app = PyocdApp()
    _std = std2tk(app)
    sys.stdout = _std
    app.run()

