import time
import requests
# import webbrowser

# def open_webbrowser(question):
#     webbrowser.open('https://baidu.com/s?wd=' + question)

def count_base(question,choices):
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
    req = requests.get(url='https://www.baidu.com/s', params={'wd':question}, headers=headers)
    print(req)  ####
    content = req.text
    # res_to_html(content)  ####

    counts = []
    print('Question: '+question)
    for i in range(len(choices)):
        counts.append(content.count(choices[i]))
        print(choices[i] + " : " + str(counts[i]))
    print('Recommend Choose : ' + choices[counts.index(max(counts))])


# def run_algorithm(al_num,question,choices):
#     if al_num == 0:
#         open_webbrowser(question)
#     elif al_num == 1:
#         count_base(question, choices)

def res_to_html(res):
    """响应结果text写到桌面的html中"""
    with open(r"C:\Users\Blink\Desktop\res" + str(int(time.time())) + ".html", "w", encoding="utf-8") as f:
        f.writelines(res)

if __name__ == '__main__':
    # question = '歌曲《康定情歌》中的“康定”位于哪个省??'
    question = '夏天旅游去哪个省份最好'
    choices = ['四川', '云南', '贵州']
    count_base(question, choices)


