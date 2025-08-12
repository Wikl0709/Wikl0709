from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
import selenium.webdriver.support.ui as ui
from selenium.webdriver.support import expected_conditions as EC
import time
import subprocess
import psutil
import os
import openpyxl
import shutil
import re
import getpass
from pathlib import Path
import datetime
from datetime import datetime
import argparse
from selenium.webdriver.common.action_chains import ActionChains
from tqdm import tqdm
import random
from selenium.webdriver.common.keys import Keys
import pywinauto
from pywinauto import Application
from pywinauto.keyboard import send_keys  # 修复send_keys未定义错误
class DoubaoAutomator:

    def __init__(self,doubao_path):
        self.driver = None
        self.doubao_path = doubao_path
        self.project_dir = Path(__file__).parent.absolute()
        self.screenshot_dir = os.path.join(self.project_dir, "screenshots")
        self.image_dir = os.path.join(self.project_dir, "images1")
        self.reference_image_dir = os.path.join(self.project_dir, "reference_images")
        os.makedirs(self.reference_image_dir, exist_ok=True)
        self._create_dirs()

    def _create_dirs(self):
        os.makedirs(self.screenshot_dir, exist_ok=True)
        os.makedirs(self.image_dir, exist_ok=True)


    def _save_screenshot(self, prefix=""):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}{timestamp}.png"
        filepath = os.path.join(self.screenshot_dir, filename)
        try:
            self.driver.save_screenshot(filepath)
            return filepath
        except Exception as e:
            print(f"截图保存失败: {str(e)}")
            return None

    def start_doubao(self):
        """启动豆包应用设置调试端口"""
        try:
            # 关闭已存在的豆包进程
            for proc in psutil.process_iter():
                try:
                    if "doubao" in proc.name().lower():
                        proc.kill()
                except:
                    continue
            
            # 启动豆包应用并最大化窗口
            subprocess.Popen([self.doubao_path, "--remote-debugging-port=9222", "--start-maximized"])
            print("正在启动豆包应用最大化窗口...")
            time.sleep(5)  # 等待应用启动
            
        except Exception as e:
            print(f"启动豆包应用失败: {str(e)}")
            raise
    def connect_to_doubao(self):
        """通过调试端口连接豆包"""
        try:
            self.start_doubao()
            
            options = webdriver.ChromeOptions()
            options.debugger_address = "127.0.0.1:9222" 
            options.add_argument("--start-maximized")
            
            current_dir = os.path.dirname(os.path.abspath(__file__))
            chromedriver_path = os.path.join(current_dir, "chromedriver.exe")
            
            service = Service(executable_path=chromedriver_path)
            
            self.driver = webdriver.Chrome(
                service=service,
                options=options
            )
            
            self.driver.maximize_window()
            print("成功连接到豆包应用（窗口已最大化）")
            print(f"当前页面标题: {self.driver.title}")
            print(f"当前页面URL: {self.driver.current_url}")
            
        except Exception as e:
            print(f"连接失败: {str(e)}")
            raise

    def create_new_session(self):
        """创建新的会话"""
        try:
            print(f"\n当前窗口数: {len(self.driver.window_handles)}")
            print(f"当前窗口句柄: {self.driver.current_window_handle}")
            
            new_session_btn = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, 
                '//div[contains(@class, "section-item-title-AQqE5v") and @title="图像生成" and text()="图像生成"]')))
            
            original_window = self.driver.current_window_handle
            original_tabs = self.driver.window_handles
            new_session_btn.click()
            print("点击图像生成按钮")
        
            self._save_screenshot('new_session_')
            time.sleep(5)
            
        except Exception as e:
            print(f"创建新会话失败: {str(e)}")
            self._save_screenshot('create_session_error_')
            raise

    def upload_reference_image(self, image_path):
        """健壮的文件上传方法"""
        try:
            print(f"准备上传参考图: {image_path}")
            
            # 定位上传按钮
            upload_btn = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 
                'button[data-testid="image-creation-chat-input-picture-reference-button"]')))
            
            # 点击上传按钮
            upload_btn.click()
            print('已点击上传按钮，等待文件选择窗口出现')
            time.sleep(3)  # 等待文件选择窗口出现
            # 方法1：尝试键盘操作
            try:
                # 确保路径格式正确
                safe_path = image_path.replace('"', '\\"')
                send_keys(f'"{safe_path}"{{ENTER}}', pause=0.1)
                print("已通过键盘输入文件路径")
                time.sleep(3)
                return True
            except:
                pass
        #     try:
        # # 连接到“打开”对话框
        #         app = Application().connect(title='打开')
        #         dlg = app['打开']
        #         time.sleep(1)
        #         # 在编辑框中设置文件路径
        #         safe_path = image_path.replace('"', '\\"')
        #         print(f'正在设置文件路径为: {safe_path}')
        #         dlg.Edit.set_edit_text(safe_path)
        #         time.sleep(3)
        #         # 点击“打开”按钮
        #         dlg['打开'].click()
        #         time.sleep(5)
        #         print(f"Image uploaded successfully: {image_path}")
        #     except:
        #         pass
            
        except Exception as e:
            print(f"上传参考图片失败: {str(e)}")
            self._save_screenshot('upload_image_error_')
            return False

        
    def send_question(self, question):
    
        try:
            start_time = datetime.now()
            print(f"[开始时间] {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

            print(f"\n[准备发送] 问题: {question}")
            
            input_box = WebDriverWait(self.driver, 20).until(
                lambda d: d.find_element('css selector', 'div[contenteditable="true"]') or
                        d.find_element('xpath', '//div[@role="textbox"]') or
                        d.find_element('xpath', '//textarea')
            )
            # print("输入框定位成功", input_box)
            # JavaScript代码是在Selenium的`execute_script`方法中执行
            self.driver.execute_script("""
                // 先点击其他区域再聚焦目标（）
                document.body.click();
                arguments[0].focus();
                
                // 模拟完整的鼠标事件链
                const rect = arguments[0].getBoundingClientRect();
                const events = ['mousedown', 'mouseup', 'click'];
                events.forEach(event => {
                    arguments[0].dispatchEvent(new MouseEvent(event, {
                        bubbles: true,
                        clientX: rect.left + 10,
                        clientY: rect.top + 10,
                        view: window
                    }));
                });
            """, input_box)
            time.sleep(1)  # 确保完全激活


            print("模拟人工输入流程")
            
            # 清空现有内容（模拟全选+删除）
            ActionChains(self.driver)\
                .key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL)\
                .pause(0.2)\
                .send_keys(Keys.DELETE)\
                .perform()
            time.sleep(0.3)

            # 分段输入+随机事件触发
            chunks = [question[i:i+5] for i in range(0, len(question), 5)]
            for i, chunk in enumerate(chunks):
                # 模拟键盘输入
                input_box.send_keys(chunk)
                time.sleep(random.uniform(0.08, 0.15))  

            # 内容校验
            current_text = self.driver.execute_script("return arguments[0].textContent", input_box)
            self._save_screenshot('new_question_')
            if not current_text.strip():
                raise Exception("内容输入失败，输入框为空")

            # 模拟点击按钮
            time.sleep(1)  # 随机等待时间    
            # # --- 5. 破解按钮禁用逻辑 ---
            send_btn = WebDriverWait(self.driver, 15).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="flow-end-msg-send"]')))
            # 获取当前消息容器的数量作为基准
            prev_message_containers = self.driver.find_elements(
                By.XPATH, '//div[contains(@class, "auto-hide-last-sibling-br")]')
            prev_count = len(prev_message_containers)
            print(f"发送前消息容器数量: {prev_count}")
            # 发送问题
            send_btn.click()
            print("问题已发送")
            
            # 等待新消息容器出现（AI的回复）
            WebDriverWait(self.driver, 180).until(
                lambda d: len(d.find_elements(
                    By.XPATH, '//div[contains(@class, "auto-hide-last-sibling-br")]'
                )) > prev_count
            )
            

            # 获取当前轮次的消息容器
            current_containers = self.driver.find_elements(
                By.XPATH, '//div[contains(@class, "auto-hide-last-sibling-br")]')
            current_container = current_containers[-1]  # 最后一个是最新的
            print(f"发送后消息容器数量: {len(current_containers)}")
            

            # 给当前轮次的容器添加唯一标识
            unique_id = f"current_session_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            self.driver.execute_script(
                f"arguments[0].setAttribute('data-unique-id', '{unique_id}')", 
                current_container
            )
            print(f"为当前轮次添加唯一标识: {unique_id}")
            
            # 保存当前轮次的唯一ID供后续使用
            self.current_session_id = unique_id
            # 滚动到最新消息
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", current_container)
            # print("已滚动到最新消息")
            #为了防止错误定位到所以等
            time.sleep(10)
            #  滚动到当前轮次底部
            # self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", current_container)
            # self._scroll_to_bottom_until_stable()
            # print("页面滚动到底部")
            return unique_id
              # 随机等待时间
        except Exception as e:
            print(f"严重错误: {str(e)}")
            self._save_screenshot('final_fail_')
            raise

    def download_generated_images(self, group_id, turn_num, prompt, row_num,session_id):
        """下载生成的图片并保存到指定目录"""
        max_retries = 3
        retry_count = 0
        unique_id = session_id 
        print(f"当前处理的会话ID: {session_id}")
        # 确保当前轮次的唯一ID存在
        if not unique_id:
            print("当前轮次的唯一ID不存在，无法下载图片")
            return False, [], 0, "缺少会话ID"
        
        while retry_count < max_retries:
            try:
                current_user = getpass.getuser()
                download_dir = os.path.expanduser(f"C:\\Users\\{current_user}\\Downloads")
                # 清理文件名中的非法字符
                def clean_filename(text):
                    cleaned = re.sub(r'[<>:"/\\|?*]', '', text)
                    if len(cleaned) > 50:
                        cleaned = cleaned
                    return cleaned.strip()
                
                # 记录下载前的文件列表
                existing_files = set(os.listdir(download_dir))
                
                # 使用唯一ID定位当前轮次的容器
                # session_container = WebDriverWait(self.driver, 30).until(
                #     EC.presence_of_element_located((By.XPATH, 
                #     f'//div[@data-unique-id="{unique_id}"]')))
                # 滚动到最新消息
                # self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", session_container)
                time.sleep(1)
                # 在当前轮次容器内定位元素
                doload_BTN_XPATH = f'//span[contains(@class, "semi-button-content-right") and contains(text(), "下载")]'
                doload_all = '//*[@id="root"]/div[1]/div/div[3]/div/main/div/div/div[3]/div/div/div/div/button/span'
                quxiao_BTN_XPATH = '//*[@id="root"]/div[1]/div/div[3]/div/main/div/div/div[1]/div/div/div/div/div[2]'
                stop_btn = '//div[contains(@class, "stop-generating-button")]'
                gd_btn='//div[contains(@class, "to-bottom-button-Bs3jaG")]//*[local-name()="path"][@d="M21.707 7.293a1 1 0 0 0-1.414 0L12 15.586 3.707 7.293a1 1 0 0 0-1.414 1.414L10.586 17a2 2 0 0 0 2.828 0l8.293-8.293a1 1 0 0 0 0-1.414"]/ancestor::div[contains(@class, "container-HRpMdH")]'
                
                # 检查是否出现停止按钮（表示图片生成完成）
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, stop_btn))
                    )
                    is_pause_button_present = True
                    print("暂停按钮已出现，跳过下载流程")
                except:
                    is_pause_button_present = False
                    print("暂停按钮未出现，进行下一步,切换到最底部")
                    # image-box-grid-CTmlWP
                    #  滚动到当前轮次底部
                    # self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", session_container)
                    time.sleep(1)
                    # self._scroll_to_bottom_until_stable()
                    
                    
                if not is_pause_button_present:
                   
                    
                    # 滚动到最新消息
                    # self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", session_container)
                    #  滚动到当前轮次底部
                    # self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", session_container)
                    # self._scroll_to_bottom_until_stable()
                    # self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    print("已滚动到底部，查找下载按钮,等待15秒")
                    time.sleep(15)
                    try:
                        # text_box_div = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.XPATH, '(//div[@class="gap-20 flex flex-col w-full"])[last()]')))
                        # text_box=text_box_div.find_element(By.TAG_NAME, 'img')

                        # print("已找到文本框",text_box)
                        doload_box_div = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.XPATH, '(//div[@class="bp5-overflow-list container-i9_9R9 align-start-BRJcKo inner-K6EVuU"])[last()]')))
                        button = doload_box_div.find_elements(By.TAG_NAME, 'button')[2]
                        if button.text == '下载':
                            button.click()
                            print("下载按钮点击成功！！！！！！！！！！！！！！！！！！！！")
                        else:
                            # duihua_box_div=WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.XPATH, '(//div[@class="auto-hide-last-sibling-br.paragraph-JOTKXA.paragraph-element.br-paragraph-space"])[last()]')))[0]
                            # error_message = duihua_box_div.text
                            # print(f"❌ 错误: {error_message}")
                                # elements = WebDriverWait(self.driver, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '.auto-hide-last-sibling-br.paragraph-JOTKXA.paragraph-element.br-paragraph-space')))
                                # if elements:
                                #     # 获取最后一个元素
                                #     last_element = elements[-1]
                                #     # 获取该元素的文本内容
                                #     text_content = last_element.text
                                #     # print(text_content)
                                #     print(f"❌ 错误: {text_content}")

                                    print(f"找到的按钮文本是'{button.text}'，不是'下载'。")
                                    raise Exception("下载按钮文本不匹配")
                        # self.driver.execute_script("arguments[0].scrollIntoView(false);", flex_box_div)
                        
                        # doload_BTN = WebDriverWait(self.driver, 30).until(EC.element_to_be_clickable((By.XPATH, doload_BTN_XPATH)))
                        # print("下载按钮已出现,滚动到图片容器最底部！！！！！！！！！！！！！！！！！！！！")

                        # flex_box_div = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.XPATH, '(//div[@class="image-box-grid-CTmlWP"])[last()]')))
                        # self.driver.execute_script("arguments[0].scrollIntoView(false);", flex_box_div)
                        # time.sleep(2)
                        # # 3.续滚动到页面最底部（如果需要）
                        # self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        # time.sleep(1)
                         # self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", flex_box_div)
                        # doload_BTN.click()
                        # print("已点击下载按钮")
                    
                    except:
                        print("下载按钮未找到，请检查网页结构是否变化")
                        elements = WebDriverWait(self.driver, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '.auto-hide-last-sibling-br.paragraph-JOTKXA.paragraph-element.br-paragraph-space')))
                        if elements:
                            # 获取最后一个元素
                            last_element = elements[-1]
                            # 获取该元素的文本内容
                            text_content = last_element.text
                            # print(f"❌ 错误: {text_content}")
                          # 如果找不到下载按钮，检查是否有错误提示
                        
                            if text_content != None:   
                                print(f"❌ 检测到错误: {text_content}")
                                self._save_screenshot('download_error_')
                                return False, [], 0, error_msg
                            # error_element = self.driver.find_element(By.XPATH, './/div[contains(text())]')
                            # error_msg = error_element.text
                            # print(f"检测到错误提示: {error_msg}")
                            # self._save_screenshot('error_msg_')
                            # return False, [], 0, error_msg
                            else:
                                print(f"没有检测到错误")
                                # raise Exception("没有检测到错误")
                        # except:
                        #     error_msg = "无法生成你要求的图片"
                        #     print(error_msg)
                        #     self._save_screenshot('download_button_missing_')
                        #     return False, [], 0, error_msg
                    # 新增：检查并点击"跳转到最新消息"按钮（如果存在）
                    # try:
                    #     # 使用driver全局查找，因为按钮可能不在session_container内
                    #     to_bottom_button = WebDriverWait(self.driver, 10).until(
                    #         EC.element_to_be_clickable((By.XPATH, gd_btn)))
                        
                    #     if to_bottom_button.is_displayed():
                    #         print("检测到'跳转到最新消息'按钮，正在点击...")
                    #         # 确保按钮可见
                    #         self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded();", to_bottom_button)
                    #         time.sleep(0.3)
                    #         to_bottom_button.click()
                    #         print("已点击'跳转到最新消息'按钮，等待页面稳定...")
                    #         time.sleep(3)  # 等待页面更新
                    #         # 重新定位下载按钮，防止元素状态失效
                    #         flex_box_div = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.XPATH, '(//div[@class="image-box-grid-CTmlWP"])[last()]')))
                    #         self.driver.execute_script("arguments[0].scrollIntoView(false);", flex_box_div)
                    #         time.sleep(2)
                    #         # 3.续滚动到页面最底部（如果需要）
                    #         self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    #         time.sleep(1)
                    #         # # 重新定位下载按钮，防止元素状态失效
                    #         # doload_BTN = WebDriverWait(self.driver, 10).until(
                    #         #     EC.element_to_be_clickable((By.XPATH, doload_BTN_XPATH)))
                    #         # print("2下载按钮已出现,滚动到图片容器最底部！！！！！！！！！！！！！！！！！！！！")
                    #         # flex_box_div = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.XPATH, '(//div[@class="image-box-grid-CTmlWP"])[last()]')))
                    #         # self.driver.execute_script("arguments[0].scrollIntoView(false);", flex_box_div)
                    #         # time.sleep(2)
                    #             # 3.续滚动到页面最底部（如果需要）
                    #         # self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    #         # time.sleep(1)
                    #         print("准备点击下载按钮...")
                    #         time.sleep(1)  # 确保稳定性 
                    #         doload_box_div = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.XPATH, '(//div[@class="bp5-overflow-list container-i9_9R9 align-start-BRJcKo inner-K6EVuU"])[last()]')))
                    #         button = doload_box_div.find_elements(By.TAG_NAME, 'button')[2]
                    #         button.click()

                    #         time.sleep(1)
                    #     else:
                    #         print("'跳转到最新消息'按钮存在但不可见，跳过点击")
                    # except:
                    #     print("未检测到'跳转到最新消息'按钮，继续下载流程")
                    #     print("找到图片容器，开始滚动到底部...")
                    #     flex_box_div = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.XPATH, '(//div[@class="image-box-grid-CTmlWP"])[last()]')))
                    #     self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", flex_box_div)
                    #     doload_box_div = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.XPATH, '(//div[@class="bp5-overflow-list container-i9_9R9 align-start-BRJcKo inner-K6EVuU"])[last()]')))
                    #     button = doload_box_div.find_elements(By.TAG_NAME, 'button')[2]
                    #     button.click()
                    #     time.sleep(1)


                    # 获取页面显示的图片数量
                    try:
                        # 在当前轮次容器内查找数量元素
                        count_element = WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, '//div[contains(@class, "text-s-color-text-tertiary s-font-small")]'))
                        )
                        # 提取数字
                        count_text = count_element.text
                        print(f"选择数量文本: {count_text}")
                        match = re.search(r'已选择 (\d+) 项内容', count_text)
                        if match:
                            expected_count = int(match.group(1))
                            print(f"页面显示选择数量: {expected_count}")
                        else:
                            print(f"无法从文本中提取数字: {count_text}")
                            expected_count = 0
                    except Exception as e:
                        print(f"获取选择数量失败: {str(e)}")
                        expected_count = 0
                        self._save_screenshot('count_fail_')
                    
                    # 查找并点击下载按钮
                    self._scroll_to_bottom_until_stable()
                    download_btn = WebDriverWait(self.driver, 30).until(
                        EC.element_to_be_clickable((By.XPATH, doload_all)))
                    self._scroll_to_bottom_until_stable()
                    download_btn.click()
                    # time.sleep(5)
                    print(f"开始下载（尝试 {retry_count+1}/{max_retries}）...")
                    # 等待下载完成
                    print("等待下载完成5秒...")
                    time.sleep(5)
                    
                    # 监控下载目录的新文件
                    start_time = time.time()
                    timeout = 60
                    new_files = []
                    
                    while time.time() - start_time < timeout:
                        current_files = set(os.listdir(download_dir))
                        new_files = list(current_files - existing_files)
                        
                        # 过滤出图片文件和压缩包
                        new_files = [f for f in new_files if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                        
                        if new_files:
                            print(f"检测到新文件: {new_files}")
                            print(f"实际下载文件数量: {len(new_files)}")
                            break
                        
                        time.sleep(3)
                    
                    if not new_files:
                        print("未检测到新下载的文件")
                        # 重试前清理
                        self._cleanup_downloads(existing_files, download_dir)
                        retry_count += 1
                        continue
                    
                    # 检查下载数量是否匹配
                    if expected_count > 0 and len(new_files) != expected_count:
                        print(f"下载数量不匹配! 预期: {expected_count}, 实际: {len(new_files)}")
                        
                        # 清理下载的文件
                        self._cleanup_downloads(existing_files, download_dir)
                        
                        # 重试前关闭下载面板
                        try:
                            quxiao_BTN = WebDriverWait(self.driver, 15).until(
                                EC.element_to_be_clickable((By.XPATH, quxiao_BTN_XPATH)))
                            quxiao_BTN.click()
                            time.sleep(2)
                            print("已关闭下载面板，准备重试")
                        except:
                            print("关闭下载面板失败")
                        
                        retry_count += 1
                        continue
                    
                    # 处理下载的文件
                    saved_image_paths = []
                    for i, filename in enumerate(new_files):
                        src_path = os.path.join(download_dir, filename)
                        # 处理单张图片
                        clean_prompt = clean_filename(prompt)
                        # 修改文件名提取逻辑，取文件名第一个'_'前的部分作为group_id

                        new_filename = f"{group_id.split('.')[0]}_{turn_num}_{clean_prompt}_1-{i+1}.png"
                        dest_path = os.path.join(self.image_dir, new_filename)
                        # 移动并重命名文件
                        shutil.copy(src_path, dest_path)
                        saved_image_paths.append(new_filename)
                        print(f"保存图片: {new_filename}")
                    
                    # 关闭下载确认框
                    try:
                        quxiao_BTN = WebDriverWait(self.driver, 15).until(
                            EC.element_to_be_clickable((By.XPATH, quxiao_BTN_XPATH)))
                        quxiao_BTN.click()
                        time.sleep(2)
                    except:
                        print("关闭下载确认框失败")
                    
                    print(f"下载完成，共保存 {len(saved_image_paths)} 张图片")
                    return True, saved_image_paths, expected_count
                    
                else:
                    print("无需下载，跳过")
                    return False, ["无需下载" for _ in range(4)]
                
            except Exception as e:
                print(f"下载图片失败: {str(e)}")
                self._save_screenshot('download_error_')
                retry_count += 1
                if retry_count < max_retries:
                    print("下载失败，准备重试...")
                    time.sleep(3)
                else:
                    print(f"已达最大重试次数 {max_retries}，放弃下载")
                    return False, [f"ERROR_{i}" for i in range(1, 5)]
        
        # 重试次数用尽仍未成功
        error_msg = f"下载失败，达到最大重试次数 {max_retries}"
        print(error_msg)
        return False, [], 0, error_msg
    
    def _cleanup_downloads(self, existing_files, download_dir):
        """清理下载的文件"""
        current_files = set(os.listdir(download_dir))
        new_files = list(current_files - existing_files)
        
        for filename in new_files:
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                file_path = os.path.join(download_dir, filename)
                try:
                    os.unlink(file_path)
                    print(f"已清理文件: {filename}")
                except Exception as e:
                    print(f"清理文件失败: {file_path} - {e}")
    
    def _scroll_to_bottom_until_stable(self, max_retries=5):
        """持续滚动直到页面底部稳定不再变化"""
        retry_count = 0
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        
        while retry_count < max_retries:
            # 滚动到页面底部
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)  # 等待内容加载
            
            # 检查是否已经到达底部
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                print("页面已稳定在底部")
                return True
            
            print(f"页面高度变化: {last_height} -> {new_height}, 继续滚动...")
            last_height = new_height
            retry_count += 1
        
        print(f"滚动{max_retries}次后仍未稳定在底部")
        return False
    

    def close(self):
        """关闭连接"""
        if self.driver:
            try:
                self.driver.quit()
                print("已关闭浏览器驱动")
            except Exception as e:
                print(f"关闭浏览器时出错: {str(e)}")
        
        # 关闭豆包进程
        for proc in psutil.process_iter():
            try:
                if "doubao" in proc.name().lower():
                    proc.kill()
            except:
                continue
        print("已关闭豆包进程")
# ... 前面的类定义保持不变 ...

    def process_excel_questions(self, file_path):
        """处理Excel中的所有问题，按Dimensions和ID分组进行多轮对话并下载图片"""
        wb = None
        try:
            print(f"加载Excel文件: {file_path}")
            wb = openpyxl.load_workbook(file_path)
            sheet = wb.active
            print("Excel文件加载成功")
            
            # 获取列索引
            col_index = {}
            for col in range(1, sheet.max_column + 1):
                header = sheet.cell(row=1, column=col).value
                if header:
                    col_index[header] = col
            
            # 添加4个图片列（如果不存在）
            image_cols = []
            for i in range(1, 5):
                col_name = f"image{i}"
                col_found = False
                
                # 检查列是否已存在
                for col in range(1, sheet.max_column + 1):
                    if sheet.cell(row=1, column=col).value == col_name:
                        image_cols.append(col)
                        col_found = True
                        break
                
                if not col_found:
                    new_col = sheet.max_column + 1
                    sheet.cell(row=1, column=new_col, value=col_name)
                    image_cols.append(new_col)
                    print(f"创建新列 {col_name}，位于第{new_col}列")
            
            # 添加num列（图片数量列）
            num_col = None
            for col in range(1, sheet.max_column + 1):
                if sheet.cell(row=1, column=col).value == "num":
                    num_col = col
                    break
            
            if num_col is None:
                num_col = sheet.max_column + 1
                sheet.cell(row=1, column=num_col, value="num")
                print(f"创建新列 num，位于第{num_col}列")

            # 添加状态列
            status_col = None
            for col in range(1, sheet.max_column + 1):
                if sheet.cell(row=1, column=col).value == "status":
                    status_col = col
                    break
            if status_col is None:
                status_col = sheet.max_column + 1
                sheet.cell(row=1, column=status_col, value="status")
                print(f"创建新列 状态，位于第{status_col}列")
                
            # 按Dimensions和ID分组
            groups = {}
            for row in range(2, sheet.max_row + 1):
                dimension = sheet.cell(row=row, column=col_index["Dimensions"]).value
                id_val = sheet.cell(row=row, column=col_index["ID"]).value
                multi_turn = sheet.cell(row=row, column=col_index["Multi-turn"]).value
                prompt = sheet.cell(row=row, column=col_index["Prompt"]).value
                
                if dimension is None or id_val is None:
                    continue
                    
                # 获取Original ID
                original_id = sheet.cell(row=row, column=col_index["ID"]).value
                
                # 创建分组结构
                dim_key = dimension
                if dim_key not in groups:
                    groups[dim_key] = {}
                    
                if id_val not in groups[dim_key]:
                    groups[dim_key][id_val] = {
                        "original_id": original_id,  # 存储Original ID
                        "turns": []
                    }
                
                if prompt:
                    groups[dim_key][id_val]["turns"].append({
                        "row": row,
                        "multi_turn": multi_turn,
                        "prompt": str(prompt).strip()
                    })
            # 按Dimensions和ID排序
            sorted_dimensions = sorted(groups.keys())
            print(f"共找到 {len(sorted_dimensions)} 个Dimensions组")
            
            # 设置参考图目录
            self.reference_image_dir = os.path.join(self.project_dir, "reference_images")
            os.makedirs(self.reference_image_dir, exist_ok=True)
            self.connect_to_doubao()
            # 处理每个Dimensions组
            for dimension in tqdm(sorted_dimensions, desc="处理Dimensions组", unit="组"):
                print(f"\n{'='*50}")
                print(f"开始处理Dimension: {dimension}")
                dim_group = groups[dimension]
                
                # 按ID排序
                sorted_ids = sorted(dim_group.keys())
                print(f"该Dimension下共有 {len(sorted_ids)} 个ID")
                
                # 处理每个ID组
                
                for group_id in tqdm(sorted_ids, desc=f"处理{dimension}下的ID", unit="组"):
                    group_data = dim_group[group_id]
                    # 按轮次排序
                    sorted_turns = sorted(group_data["turns"], key=lambda x: int(x["multi_turn"]))
                    
                    print(f"\n{'='*50}")
                    print(f"开始处理ID: {group_id} (Dimension: {dimension})")
                    print(f"共有 {len(sorted_turns)} 个轮次")
                    
                    try:
                        # 启动新会话
                        # self.connect_to_doubao()
                        self.create_new_session()
                        
                        # 上传参考图
                        original_id = group_data["original_id"]
                        if original_id:
                            image_path = os.path.join(self.reference_image_dir, original_id)
                            if os.path.exists(image_path):
                                print(f"上传参考图: {image_path}")
                                self.upload_reference_image(image_path)
                            else:
                                print(f"警告: 参考图不存在: {image_path}")
                        else:
                            print("警告: 该组没有Original ID")
                        
                        # 处理每个轮次
                        for turn in sorted_turns:
                            row_num = turn["row"]
                            turn_num = turn["multi_turn"]
                            prompt = turn["prompt"]
                            
                            print(f"\n{'='*50}")
                            print(f"处理轮次 {turn_num} (行号: {row_num})")
                            print(f"Prompt: {prompt}")
                            
                            # 更新状态为"处理中"
                            sheet.cell(row=row_num, column=status_col, value="处理中")
                            wb.save(file_path)
                            
                            try:
                                # 发送问题并获取会话ID
                                session_id = self.send_question(prompt)
                                # 下载生成的图片
                                # success, image_paths, num, error_msg = self.download_generated_images(group_id, turn_num, prompt, row_num)        
                                success, image_paths, num= self.download_generated_images(group_id, turn_num, prompt, row_num, session_id)
                                # 更新状态和图片信息
                                if success:
                                    status = "pass"
                            
                                    sheet.cell(row=row_num, column=status_col, value=status)
                                
                                else:
                                    status = f"fail: {error_msg[:50]}"  # 截取前50个字符
                                    sheet.cell(row=row_num, column=status_col, value=status)
                                    # print(f"下载失败: {error_msg}")
                                # 将图片数量保存到Excel的num列
                                sheet.cell(row=row_num, column=num_col, value=num)
                                print(f"已保存图片数量到Excel: num = {num}")
                                if success: 
                                    # 保存图片路径
                                    for i, path in enumerate(image_paths):
                                        if i < len(image_cols):
                                            sheet.cell(row=row_num, column=image_cols[i], value=path)
                                            print(f"已保存图片路径: image{i+1} = {path}")

                                # # 更新状态
                                # sheet.cell(row=row_num, column=status_col, value=status)
                                
                            except Exception as e:
                                error_msg = f"处理异常: {str(e)}"
                                print(error_msg)
                                sheet.cell(row=row_num, column=status_col, value=f"fail: {error_msg}")
                                try:
                                    # 尝试获取豆包返回的具体错误信息
                                    elements = WebDriverWait(self.driver, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '.auto-hide-last-sibling-br.paragraph-JOTKXA.paragraph-element.br-paragraph-space')))
                                    if elements:
                                        last_element = elements[-1]
                                        specific_error = last_element.text
                                        if specific_error:
                                            print(f"具体错误信息: {specific_error}")
                                            # 可以选择将具体错误信息也写入状态列
                                            sheet.cell(row=row_num, column=status_col, value=f"fail: {specific_error}")
                                except:
                                    # 如果无法获取具体错误信息，则使用通用错误信息
                                    pass
                                # sheet.cell(row=row_num, column=status_col, value="fail:无法生成你要求的图片")
                            # 每处理完一行后保存一次Excel
                            wb.save(file_path)
                            print(f"Excel文件已保存")
                    
                    except Exception as e:
                        print(f"处理ID组 {group_id} 时出错: {str(e)}")
                        self._save_screenshot(f"error_{dimension}_{group_id}_")
                    
                    finally:
                        # 关闭当前ID组的驱动
                        # self.close()
                        time.sleep(5)
            
            print("\n所有处理完成！")
            
        except Exception as e:
            print(f"处理Excel时出错: {type(e).__name__}: {str(e)}")
            raise
        finally:
            try:
                if wb:
                    wb.save(file_path)
                    wb.close()
                    print("Excel文件已保存")
            except Exception as e:
                print(f"保存Excel时出错: {str(e)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="豆包文生图工具")
    parser.add_argument("--excel_path", help="Excel文件路径", default=r"D:\lenovo_yanbin\AI_Lab\tool\20250717\imageEdit_json_to_excel_result.xlsx")
    parser.add_argument("--doubao_path", help="豆包应用路径", default=r"C:\Users\weiyb2\AppData\Local\Doubao\Application\Doubao.exe")
    args = parser.parse_args()
    
    print(f"豆包应用路径: {args.doubao_path}")
    print(f"Excel文件路径: {args.excel_path}")
    
    automator = DoubaoAutomator(args.doubao_path)
    try:
        print(f"开始处理Excel文件")
        automator.process_excel_questions(args.excel_path)
    except Exception as e:
        print(f"运行出错: {type(e).__name__}: {str(e)}")
    finally:
        print("执行结束")