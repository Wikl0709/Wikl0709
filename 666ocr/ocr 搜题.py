#coding:'utf-8'
import aip
import win32gui, win32ui, win32con, win32api
from PIL import Image
import pytesseract
import webbrowser
#先下载pyautogui库，pip install pyautogui
import os,time
import pyautogui as pag
from aip import AipOcr, ocr
#获取sdk http://ai.baidu.com/。
#获取aip    pip install git+https://github.com/Baidu-AIP/python-sdk.git@master
from aip import AipOcr
from Wikl import methods
from threading import Thread
from colorama import init,Fore
import json

status=0
""" yanbin_ APPID AK SK """
APP_ID = '25383950'
API_KEY = 'HiMbboCSG9TCNvRF6xEigsOR'
SECRET_KEY = 'sdrZ3lnyQ2F2146mqCTaXrGzOC8u3scf'
client = AipOcr(APP_ID, API_KEY, SECRET_KEY)

""" 读取图片 """

def get_question(path):
    '''百度识别图片文字'''
    with open(path, 'rb') as fp:
        image=fp.read()
    res = client.basicGeneral(image)
    words = res['words_result']
    lines = [item['words'] for item in words]
    print(lines)

    if len(lines) > 2:
        question = lines[0]#+lines[1]
        choices = lines[1:]
        choices = [x.replace(' ', '') for x in choices]
    else:
        print(Fore.RED + '截图区域设置错误，请重新设置' + Fore.RESET)
        exit(0)
    # 处理出现问题为两行或三行，注意中英文？?
    if choices[0].endswith('？'):
        question += choices[0]
        choices.pop(0)
    elif choices[1].endswith('？'):
        question += choices[0]
        question += choices[1]
        choices.pop(0)
        choices.pop(0)

    return question, choices


    # question = ''.join(lines)
    # print(question)
    #
    # if question[1] == '.':
    #     question = question[2:]
    # elif question[2] == '.':
    #     question = question[3:]
    # return question.replace('?', '  ')

#采集坐标
def get_point():
    '''采集坐标，并返回w,h,x,y。 作为window_capture() 函数使用'''
    try:
        print('正在采集坐标1，请将鼠标移动到该点')
        # print(3)
        # time.sleep(1)
        print(2)
        time.sleep(1)
        print(1)
        time.sleep(1)
        x1,y1 = pag.position() #返回鼠标的坐标
        print('采集成功，坐标为：',(x1,y1))
        print('')
        # time.sleep(2)
        print('正在采集坐标2，请将鼠标移动到该点')
        print(3)
        time.sleep(1)
        print(2)
        time.sleep(1)
        print(1)
        time.sleep(1)
        x2, y2 = pag.position()  # 返回鼠标的坐标
        print('采集成功，坐标为：',(x2,y2))
        #os.system('cls')#清除屏幕
        w = abs(x1 - x2)
        h = abs(y1 - y2)
        x = min(x1, x2)
        y = min(y1, y2)
        return (w,h,x,y)
    except  KeyboardInterrupt:
        print('获取失败')
#获取截图
def window_capture(result,filename):
    '''获取截图'''
    #宽度w
    #高度h
    #左上角截图的坐标x,y
    w,h,x,y=result
    hwnd = 0
    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()
    saveBitMap = win32ui.CreateBitmap()
    MoniterDev = win32api.EnumDisplayMonitors(None,None)
    #w = MoniterDev[0][2][2]
    # #h = MoniterDev[0][2][3]
    # w = 516
    # h = 514
    saveBitMap.CreateCompatibleBitmap(mfcDC,w,h)
    saveDC.SelectObject(saveBitMap)
    saveDC.BitBlt((0,0),(w,h),mfcDC,(x,y),win32con.SRCCOPY)
    saveBitMap.SaveBitmapFile(saveDC,filename)

def get_point_txt(status):
    #如果status=y,则重新获取坐标
    '''如果存在point.txt，则询问是否重新采集，删除point.txt;如果不存在txt,则直接采集。'''

    if not os.path.isfile('point.txt') :
        result = get_point()
        with open('point.txt', 'w') as f:
            f.write(str(result))
        return result
    else:
        if status=='y':
            result = get_point()
            with open('point.txt', 'w') as f:
                f.write(str(result))
            return result
        else:
            with open('point.txt', 'r') as f:
                result = f.readline()
            result = eval(result)
            return result

# def orc_pic():
#     #识别中文
#     text=pytesseract.image_to_string(Image.open('jietu.jpg'),lang='chi_sim')
#     #识别英文
#     # text=pytesseract.image_to_string(Image.open('jietu.jpg'))
#     text = ''.join(text.split())
#     return text

#百度识别
def orc_baidu():
    text=get_question('jietu.jpg')
    return text

# =y 重新定位,=x直接进行
status='y'

start = time.time()
result=get_point_txt(status)
# for i in range(10):
img=window_capture(result,'jietu.jpg')
text=orc_baidu()
# print(text)
question, choices = get_question('jietu.jpg')
print(question)
print(choices)
# text=orc_pic()
# print(text)

#浏览器搜索
# url = 'http://www.baidu.com/s?wd=%s' % text
# webbrowser.open(url)

# question, choices =ocr.ocr_img_baidu(img,client)
# m1 = Thread(methods.run_algorithm(0, question, choices))
m2 = Thread(methods.run_algorithm(1, question, choices))
m3 = Thread(methods.run_algorithm(2, question, choices))
# m1.start()
m2.start()
m3.start()
end = time.time()
time=end-start
print('此次耗时%.1f秒' % time)
