import requests,re

def main(url):#视频解析函数
    share_url =url
    headers = {
        'user-agent': 'Mozilla/5.0 (Linux; Android 6.0.1; Moto G (4)) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Mobile Safari/537.36'
    }
    response = requests.get(share_url,headers = headers)
    url  = response.url #处理页面重定向，提取新连接
    id = re.search(r'/video/(.*?)/',url).group(1) #获取视频id


    #提取带水印的视频链接地址
    url = 'https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids=' + id
    response = requests.get(url,headers=headers)
    json = response.json()
    download_url = json['item_list'][0]['video']['play_addr']['url_list'][0].replace('wm','')
     #输出的链接就是无水印地址
    return '无水印地址:'+download_url
if __name__ == '__main__':
    download_url = main(input('请输入抖音小视频URL：'))
    print(download_url)
