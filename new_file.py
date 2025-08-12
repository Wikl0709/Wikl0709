# !/user/bin/env python
# -*- coding:utf-8 -*-

import os
import time


# 获取username, 如chinaren
def getusername():
    namelist = os.popen('echo %username%').readlines()
    username = namelist[0].replace("\n", "")
    # 获取当前的username
    return username


# 获取时间和日期
def getnowdatatime(flag=0):
    '''
    flag = 0为时间和日期         eg:2018-04-11 10:04:55
    flag = 1仅获取日期           eg:2018-04-11
    flag = 2仅获取时间           eg:10:04:55
    flag = 3纯数字的日期和时间   eg:20180411100455
    '''
    now = time.localtime(time.time())
    if flag == 0:
        return time.strftime('%Y-%m-%d %H:%M:%S', now)
    if flag == 1:
        return time.strftime('%Y-%m-%d', now)
    if flag == 2:
        return time.strftime('%H:%M:%S', now)
    if flag == 3:
        return time.strftime('%Y%m%d%H%M%S', now)


# 生成指定大小的TXT档
def generateTXTFile():
    fileSize = 0
    # 判断输入是否有误
    while True:
        size = input('请输入你想生成的文件大小(MB):')
        if size.strip().isdigit() != True:
            print('只能输入整数，请重新输入!')
            continue
        else:
            fileSize = int(size)
            break
    if fileSize >= 200:
        print('正在生成文件中，请稍候... ...')
    # 生成指定大小的TXT档
    filename = getnowdatatime(3) + '_' + size + 'MB.xlsx'
    print(f'文件名：{filename}')
    # 设置文件保存的路径
    filepath = 'D:\\lenovo_yanbin\\speed_file\\test_f\\'
    f = open(filepath + filename, 'w')
    # 获取开始时间
    starttime = getnowdatatime()
    startclock = time.perf_counter()
    for i in range(fileSize):
        if i >= 100:
            if i % 100 == 0:
                print(f'已生成{i//100 * 100}MB数据.')
        for j in range(1024):
            try:
                f.write('wi' * 512)
            except KeyboardInterrupt:
                print('\n异常中断:KeyboardInterrupt')
                f.close()
                exit(-1)
    f.close()
    print(f'文件已成生并保存在桌面,  文件大小:{fileSize}MB.\n')
    print(f'DetailInfo:')
    print(f'保存路径: {filepath + filename}')
    print(f'开始时间:{starttime}')
    print(f'结束时间:{getnowdatatime()}')
    print(f'总共耗时:{(time.perf_counter() - startclock):<.3}sec.')


if __name__ == '__main__':
    generateTXTFile()
# https://blog.csdn.net/weixin_43835542/article/details/107763157