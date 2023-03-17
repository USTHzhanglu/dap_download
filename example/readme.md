## *.bin
    烧录所用到的固件
## *.pack
    烧录算法文件，Keil补丁包。文件名需要与yaml中对应
## *.yaml
    配置文件，描述了目标芯片型号，烧录算法所在位置，烧录速率等


​    
```yaml
target_override: GD32F310G8 #目标芯片型号
pack:                       #烧录算法所在位置,可以存放多个
  ./GD32F3x0_DFP.3.0.2.pack
frequency: 10000000         #烧录速率
```