import psutil
import os
import datetime
import time


def getMemCpu():
    data = psutil.virtual_memory()
    total = data.total  # 总内存,单位为byte
    free = data.available  # 可以内存
    # xiaowei=psutil.virtual_memory().percent  # 获取内存使用率
    # print(xiaowei)
    memory = "Memory usage:%d" % (int(round(data.percent)))+"%"+" "
    cpu = "CPU:%0.2f" % psutil.cpu_percent(interval=1)+"%"
    sent_before = psutil.net_io_counters().bytes_sent  # 发送
    recv_before = psutil.net_io_counters().bytes_recv  # 接受
    sent_now = psutil.net_io_counters().bytes_sent
    recv_now = psutil.net_io_counters().bytes_recv
    sent = (sent_now - sent_before) / 1024
    recv = (recv_now - recv_before) / 1024
    print(time.strftime(" %Y-%m-%d %H:%M:%S ", time.localtime()))
    sent1=("网络上传：{0}KB/s".format("%.2f" % sent))
    recv1=("网络下载：{0}KB/s".format("%.2f" % recv))
    return memory+cpu+sent1+recv1


def main():

    while(True):
        info = getMemCpu()
        time.sleep(0)
        now = datetime.datetime.now()
        f = open('./history.txt', 'a+')
        str_ = str(now) + ' ' + info + '\n'
        f.writelines(str_)
        print(str_)


if __name__ == "__main__":
    main()
