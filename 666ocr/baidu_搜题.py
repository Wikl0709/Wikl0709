import requests
import webbrowser

def open_webbrowser(question):
    webbrowser.open('https://baidu.com/s?wd=' + question)

def count_base(question,choices):
    # 请求
    headers = {"Accept": "application/json, text/javascript, */*; q=0.01",
               "Accept-Language": "zh-CN,zh;q=0.9",
               "Cookie":"BIDUPSID=C489A33FBAF77D8416138B7A2968D3A2; PSTM=1651585183; BAIDUID=F935B5A845DAD39441B6709B80F4F2D9:FG=1; BD_UPN=12314753; ZFY=ywf5BG:AgxQX9ohYE9gW6R8wyliKeEwX3on0vNIr8ago:C; BAIDUID_BFESS=F935B5A845DAD39441B6709B80F4F2D9:FG=1; baikeVisitId=129851f7-df71-4071-adae-2a438e6a7d1c; BDRCVFR[nPakuLoEdV0]=mk3SLVN4HKm; delPer=0; BD_CK_SAM=1; PSINO=2; H_PS_PSSID=31660_26350; BA_HECTOR=al0ka0212g0k040h0k1hc01o715; BDORZ=FFFB88E999055A3F8A630C64834BD6D0; COOKIE_SESSION=12_0_9_9_32_2_0_0_9_2_0_0_82659_0_0_0_1656233168_0_1656751887|9#0_0_1656751887|1; H_PS_645EC=0e76r7DAFbxFbPChE0iHF+QDQsb+8adcNbnojsyVPbtytpCTE73YdY4O2+6dBqHKeuhHEBDCFM0b",
               "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36"}
    req = requests.get(url='https://www.baidu.com/s', params={'wd':question},headers=headers)
    content = req.text

    counts = []
    print('Question: '+question)
    for i in range(len(choices)):
        counts.append(content.count(choices[i]))
        print(choices[i] + " : " + str(counts[i]))
    print('Recommend Choose : ' + choices[counts.index(max(counts))])



def run_algorithm(al_num,question,choices):
    if al_num == 0:
        open_webbrowser(question)
    elif al_num == 1:
        count_base(question, choices)

if __name__ == '__main__':
    question = '国内夏天去哪旅游最好??'
    choices = ['四川', '云南', '贵州']
    count_base(question, choices)