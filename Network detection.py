# coding:utf-8
import psutil
import time

def getNet():
    sent_before = psutil.net_io_counters().bytes_sent  # 发送
    recv_before = psutil.net_io_counters().bytes_recv  # 接受
    time.sleep(1)
    sent_now = psutil.net_io_counters().bytes_sent
    recv_now = psutil.net_io_counters().bytes_recv
    sent = (sent_now - sent_before)/1024
    recv = (recv_now - recv_before)/1024
    print(time.strftime(" %Y-%m-%d %H:%M:%S ", time.localtime()))
    print("网络上传：{0}KB/s".format("%.2f"%sent))
    print("网络下载：{0}KB/s".format("%.2f"%recv))
    print('*'*32)


if __name__ == "__main__":
    print('*'*32)
    while 1:
        getNet()