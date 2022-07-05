# -*- coding: utf-8 -*-

import time
import requests
import webbrowser
import urllib.parse

# # 颜色兼容Win 10
from colorama import init,Fore
from threading import Thread
init()

def open_webbrowser(question):
    webbrowser.open('https://baidu.com/s?wd=' + urllib.parse.quote(question))

def open_webbrowser_count(question,choices):

    print('\n-- 方法2： 题目+选项搜索结果计数法 --\n')
    print('Question: ' + question)
    if '不是' in question:
        print('**请注意此题为否定题,选计数最少的**')
    headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
               # "Accept-Encoding": "gzip, deflate, br",
               "Accept-Language": "zh-CN,zh;q=0.9",
               "User-Agent": "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36",
               "Cookie": """BIDUPSID=B621356CA5747AECE9F6C1E5C4F52E7D; PSTM=1654337027; BD_UPN=12314353; ispeed_lsm=2; BDUSS=1R5cUVWeG9Qak14QlljSmpWRmNPTThSYnUwdU9HNHV5YzFONDlVYnRRNVctc3hpRVFBQUFBJCQAAAAAAAAAAAEAAADbLJ8RYmxpbmswMTUAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFZtpWJWbaViT; BDUSS_BFESS=1R5cUVWeG9Qak14QlljSmpWRmNPTThSYnUwdU9HNHV5YzFONDlVYnRRNVctc3hpRVFBQUFBJCQAAAAAAAAAAAEAAADbLJ8RYmxpbmswMTUAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFZtpWJWbaViT; BAIDUID=B621356CA5747AEC6FB3A8E231488C49:SL=0:NR=10:FG=1; BDORZ=B490B5EBF6F3CD402E515D22BCDA1598; COOKIE_SESSION=643734_0_8_8_2_28_1_0_7_7_0_6_643756_0_43_0_1656721887_0_1656721844|9#881761_4_1655563286|3; delPer=0; BD_CK_SAM=1; PSINO=2; BA_HECTOR=0k212l8h8l0ha5a40l1hbv50h14; ZFY=00zaONgFo8zXpJwSi0JZtI:BW6w82hkkILQstTriQtxo:C; BD_HOME=1; RT="z=1&dm=baidu.com&si=t8e76ppxgf&ss=l535sn2p&sl=h&tt=knp&bcn=https://fclog.baidu.com/log/weirwood?type=perf&ld=19uq6&ul=1cq6d&hd=1cq8k"; BDRCVFR[feWj1Vr5u3D]=I67x6TjHwwYf0; H_PS_PSSID=36550_36506_36454_36665_34812_36691_36165_36694_36696_36773_36746_36762_36768_36764_26350_36469_36713; sug=0; sugstore=0; ORIGIN=2; bdime=0; H_PS_645EC=b203sIwuxxHoHxxoUOO8Dlgrv6RpcX8OkWTIxwOM2S+Y0RvbdDc/GvlFK9E; baikeVisitId=b313d197-bba5-4ef1-930f-f4c43cf305dd"""
               }   
    counts = []   

    for i in range(len(choices)):
        # 请求
        req = requests.get(url='http://www.baidu.com/s', params={'wd': question + choices[i]},headers=headers)
        
        content = req.text
        index = content.find('百度为您找到相关结果约') + 11
        content = content[index:]
        index = content.find('个')
        count = content[:index].replace(',', '')
        counts.append(count)
        #print(choices[i] + " : " + count)
    output(choices, counts)

def count_base(question,choices):
    print('\n-- 方法3： 题目搜索结果包含选项词频计数法 --\n')
    # 请求
    # headers = {'Accept': 'application/json, text/javascript, */*; q=0.01',
    #            'Host': 'www.baidu.com',
    #            'User-Agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.53 Mobile Safari/537.36 Edg/103.0'}
    headers = {
               "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
               # "Accept-Encoding": "gzip, deflate, br",
               "Accept-Language": "zh-CN,zh;q=0.9",
               "User-Agent": "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36",
               "Cookie": """BIDUPSID=B621356CA5747AECE9F6C1E5C4F52E7D; PSTM=1654337027; BD_UPN=12314353; ispeed_lsm=2; BDUSS=1R5cUVWeG9Qak14QlljSmpWRmNPTThSYnUwdU9HNHV5YzFONDlVYnRRNVctc3hpRVFBQUFBJCQAAAAAAAAAAAEAAADbLJ8RYmxpbmswMTUAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFZtpWJWbaViT; BDUSS_BFESS=1R5cUVWeG9Qak14QlljSmpWRmNPTThSYnUwdU9HNHV5YzFONDlVYnRRNVctc3hpRVFBQUFBJCQAAAAAAAAAAAEAAADbLJ8RYmxpbmswMTUAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFZtpWJWbaViT; BAIDUID=B621356CA5747AEC6FB3A8E231488C49:SL=0:NR=10:FG=1; BDORZ=B490B5EBF6F3CD402E515D22BCDA1598; COOKIE_SESSION=643734_0_8_8_2_28_1_0_7_7_0_6_643756_0_43_0_1656721887_0_1656721844|9#881761_4_1655563286|3; delPer=0; BD_CK_SAM=1; PSINO=2; BA_HECTOR=0k212l8h8l0ha5a40l1hbv50h14; ZFY=00zaONgFo8zXpJwSi0JZtI:BW6w82hkkILQstTriQtxo:C; BD_HOME=1; RT="z=1&dm=baidu.com&si=t8e76ppxgf&ss=l535sn2p&sl=h&tt=knp&bcn=https://fclog.baidu.com/log/weirwood?type=perf&ld=19uq6&ul=1cq6d&hd=1cq8k"; BDRCVFR[feWj1Vr5u3D]=I67x6TjHwwYf0; H_PS_PSSID=36550_36506_36454_36665_34812_36691_36165_36694_36696_36773_36746_36762_36768_36764_26350_36469_36713; sug=0; sugstore=0; ORIGIN=2; bdime=0; H_PS_645EC=b203sIwuxxHoHxxoUOO8Dlgrv6RpcX8OkWTIxwOM2S+Y0RvbdDc/GvlFK9E; baikeVisitId=b313d197-bba5-4ef1-930f-f4c43cf305dd"""
               }
    req = requests.get(url='https://www.baidu.com/s', params={'wd':question},headers=headers)
    print(req)  ####
    content = req.text
    # res_to_html(content)  ####

    #print(content)
    counts = []
    print('Question: '+question)
    if '不是' in question:
        print('**请注意此题为否定题,选计数最少的**')
    for i in range(len(choices)):
        counts.append(content.count(choices[i]))
        print(choices[i] + " : " + str(counts[i]))
    output(choices, counts)

def output(choices, counts):
    print(choices, counts)

    counts = list(map(int, counts))
    # print(choices, counts)

    # 计数最高
    index_max = counts.index(max(counts))

    # 计数最少
    index_min = counts.index(min(counts))

    if index_max == index_min:
        print(Fore.RED + "高低计数相等此方法失效！" + Fore.RESET)
        return

    for i in range(len(choices)):
        if i == index_max:
            # 绿色为计数最高的答案
            print(Fore.GREEN + "{0} : {1} ".format(choices[i], counts[i]) + Fore.RESET)
        elif i == index_min:
            # 红色为计数最低的答案
            print(Fore.MAGENTA + "{0} : {1}".format(choices[i], counts[i]) + Fore.RESET)
        else:
            print("{0} : {1}".format(choices[i], counts[i]))


def run_algorithm(al_num, question, choices):
    if al_num == 0:
        open_webbrowser(question)
    elif al_num == 1:
        open_webbrowser_count(question, choices)
    elif al_num == 2:
        count_base(question, choices)

def res_to_html(res):
    """响应结果text写到桌面的html中"""
    with open(r"C:\Users\Lenovo\Desktop\Project\crawler\666ocr\Wikl" + str(int(time.time())) + ".html", "w", encoding="utf-8") as f:
        f.writelines(res)

if __name__ == '__main__':
    start = time.time()
    question = '歌曲《康定情歌》中的“康定”位于哪个省?'
    # question = '夏天旅游去哪个省份最好'
    choices = ['四川', '云南', '贵州']
    # run_algorithm(1, question, choices)
    # m1 = Thread(run_algorithm(0, question, choices))
    m2 = Thread(run_algorithm(1, question, choices))
    m3 = Thread(run_algorithm(2, question, choices))
    # m1.start()
    m2.start()
    m3.start()
    end = time.time()
    time = end - start
    print('此次耗时%.1f秒' % time)

