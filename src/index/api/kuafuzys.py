from ..base import BaseSearch
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, List
import re
import yaml
from pathlib import Path

class KuafuzysSearch(BaseSearch):
    """
    kuafuzys.com 网页搜索实现，解析搜索结果页面提取资源信息
    """

    def __init__(self):
        self.base_url = "https://www.kuafuzys.com/search-{}.htm"
        self.headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'priority': 'u=0, i',
            'referer': 'https://www.kuafuzys.com/thread-103851.htm',
            'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': self.get_random_ua(),
            'x-forwarded-for': self.generate_random_ip()
        }
        
        # 从配置文件加载cookies
        config_path = Path(__file__).parent.parent.parent.parent / "config.yaml"
        if not config_path.exists():
            config_path = Path(__file__).parent.parent.parent.parent / "config.yaml"
        
        self.cookies = {}
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
                kuafuzys_cookies = config.get("cookies", {}).get("kuafuzys", "")
                # 解析cookie字符串
                if kuafuzys_cookies:
                    for cookie in kuafuzys_cookies.split("; "):
                        if "=" in cookie:
                            key, value = cookie.split("=", 1)
                            self.cookies[key] = value

    def search(self, keyword: str) -> Dict[str, Any]:
        """
        搜索kuafuzys.com资源并返回结构化结果
        """
        try:
            # 对关键词进行十六进制编码，格式为_E6_9C_9D_E9_9B_AA_E5_BD_95
            # 每个UTF-8字节前加下划线，整体以一个下划线开头
            formatted_keyword = ''
            for char in keyword:
                # 将字符编码为UTF-8字节
                utf8_bytes = char.encode('utf-8')
                # 每个字节转换为十六进制并加前缀_
                for byte in utf8_bytes:
                    formatted_keyword += f'_{byte:02X}'
            
            # 构造完整URL
            url = self.base_url.format(formatted_keyword)
            
            
            # 发送GET请求
            resp = requests.get(
                url,
                headers=self.headers,
                cookies=self.cookies,
                timeout=15
            )
            
            resp.raise_for_status()
            
            # 解析HTML
            soup = BeautifulSoup(resp.text, 'html.parser')
           
            # 查找结果容器
            results_container = soup.find('ul', class_='list-unstyled threadlist mb-0')
                
            # 查找所有结果卡片
            result_cards = results_container.find_all('li', class_='media')
            
            # 存储结果的列表
            results = []
            valid_count = 0  # 计数器，用于限制只选择3个结果
            
            # 存储需要异步处理的项
            items_to_process = []
            
            for card in result_cards:
                try:
                    # 检查是否包含已失效标记
                    expired_badge = card.find('span', class_='badge badge-warning ml-2 link-expired-badge')
                    if expired_badge and '【已被多人标记失效】' in expired_badge.get_text():
                        continue  # 跳过已失效的链接
                    
                    # 提取链接和标题
                    link_tag = card.find('div', class_='media-body').find('a')
                    
                    if not link_tag:
                        continue
                        
                    link = link_tag.get('href', '')
                    # 提取标题，从span标签中获取
                    title = link_tag.get_text().strip()
                    if not link or not title:
                        continue

                    # 提取其他信息
                    content = link_tag.get_text().strip()

                    # 初始化夸克链接为空
                    quark_link = ""
                    image = ""
                    
                    # 构造结果对象
                    result = {
                        "messageId": self._extract_message_id(link),
                        "title": self._clean_html(title),
                        "pubDate": "",
                        "content": self._clean_html(content),
                        "image": image,
                        "cloudLinks": [{
                            "link": quark_link,
                            "cloudType": self.detect_cloud_type(quark_link)
                        }],
                        "tags": [],
                        "magnetLink": "",
                        "channel": "Kuafuzys",
                        "channelId": "kuafuzys"
                    }
                    
                    # 添加到待处理列表
                    items_to_process.append((link, result))
                    valid_count += 1  # 增加计数器
                    
                    if valid_count >= 3:  # 如果已经选择了3个结果，则跳出循环
                        break
                except Exception as e:
                    print(f"解析结果项失败: {str(e)}")
                    continue
            
            # 使用异步多线程处理结果项
            processed_results = self._batch_fetch_details(items_to_process, self._process_result_item)
            
            # 过滤掉处理失败的项
            results = [r for r in processed_results if r is not None]
            
            return self._format_results(results, keyword)
            
        except Exception as e:
            print(f"kuafuzys搜索失败: {str(e)}")
            return self._format_results([], keyword)
    def _extract_message_id(self, link: str) -> str:
        """
        从链接中提取唯一标识符
        """
        # 尝试从链接中提取ID
        # 处理 kuafuzys 的链接格式，如 /thread-103851.htm
        match = re.search(r'thread-(\d+)\.htm', link)
        if match:
            return match.group(1)

    def _format_results(self, results: List[Dict[str, Any]], keyword: str) -> Dict[str, Any]:
        """
        格式化结果，与其它搜索插件保持一致
        """
        return {
            "list": results,
            "channelInfo": {
                "id": "kuafuzys",
                "name": "Kuafuzys",
                "index": 1080,
                "channelLogo": ""
            },
            "id": "kuafuzys",
            "index": 1080,
            "total": len(results),
            "keyword": keyword
        }

    def post_comment(self, thread_id: int, message: str) -> bool:
        """
        在指定帖子下发表评论
        :param thread_id: 帖子ID
        :param message: 评论内容
        :return: 是否发表成功
        """
        try:
            # 构造评论URL
            comment_url = f"https://www.kuafuzys.com/post-create-{thread_id}-1.htm"
            
            # 设置评论请求头
            comment_headers = {
                'accept': 'text/plain, */*; q=0.01',
                'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
                'cache-control': 'no-cache',
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'origin': 'https://www.kuafuzys.com',
                'pragma': 'no-cache',
                'priority': 'u=1, i',
                'referer': f'https://www.kuafuzys.com/thread-{thread_id}.htm',
                'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
                'user-agent': self.get_random_ua(),
                'x-requested-with': 'XMLHttpRequest',
                'x-forwarded-for': self.generate_random_ip()
            }
            
            # 构造评论数据
            comment_data = {
                'doctype': '1',
                'return_html': '1',
                'quotepid': '',
                'message': message,
                'quick_reply_message': '1'
            }
            
            # 发送POST请求发表评论
            response = requests.post(
                comment_url,
                headers=comment_headers,
                cookies=self.cookies,
                data=comment_data,
                timeout=15
            )
            
            response.raise_for_status()
            
            # 解析响应JSON并检查"code"字段
            try:
                response_json = response.json()
                # 如果"code"为"0"则认为发表成功
                if response_json.get("code") == "0":
                    return True
                else:
                    return False
            except Exception as json_error:
                # 如果无法解析JSON，则根据状态码判断
                print(f"无法解析响应JSON: {str(json_error)}")
                return False
                
        except Exception as e:
            print(f"发表评论失败: {str(e)}")
            return False

    def _process_result_item(self, item):
        """
        处理单个结果项
        :param item: (link, result) 元组
        :return: 处理后的结果对象
        """
        link, result = item
        
        try:
            # 访问链接
            detail_url = f"https://www.kuafuzys.com/{link.lstrip('/')}"
            detail_response = requests.get(
                detail_url,
                headers=self.headers,
                cookies=self.cookies,
                timeout=15
            )
            detail_response.raise_for_status()
            
            # 从链接中提取帖子ID
            thread_id = self._extract_message_id(link)
            if thread_id and thread_id.isdigit():
                # 发表评论，使用选项1,2,3,4中的一个
                # 选项值到实际评论内容的映射
                comment_options = {
                    "1": "哈哈，不错哦！",
                    "2": "不错的帖子！",
                    "3": "非常棒！！！",
                    "4": "感谢分享，资源太棒了"
                }
                
                # 这里我们随机选择一个选项
                import random
                comment_value = str(random.randint(1, 4))
                comment_message = comment_options[comment_value]
                self.post_comment(int(thread_id), comment_message)
                
                # 再次访问链接
                detail_response = requests.get(
                    detail_url,
                    headers=self.headers,
                    cookies=self.cookies,
                    timeout=15
                )
                detail_response.raise_for_status()
                
                # 解析HTML并提取图片
                detail_soup = BeautifulSoup(detail_response.text, 'html.parser')
                img_tag = detail_soup.find('img', class_='rounded shadow lazy img-responsive')
                if img_tag:
                    image_url = img_tag.get('data-original', '') or img_tag.get('src', '')
                    # 更新结果对象中的图片URL
                    result["image"] = image_url
                
                # 提取夸克链接
                alert_div = detail_soup.find('div', class_='alert alert-success')
                if alert_div:
                    link_tag = alert_div.find('a', href=True)
                    if link_tag:
                        quark_link = link_tag['href']
                        # 更新结果对象中的cloudLinks
                        if quark_link:
                            result["cloudLinks"] = [{
                                "link": quark_link,
                                "cloudType": self.detect_cloud_type(quark_link)
                            }]
            
            # 更新cloudLinks中的原始链接
            if link:
                original_link = f"https://www.kuafuzys.com/{link.lstrip('/')}" if link.startswith('/') else link
                # 如果还没有夸克链接，则保留原始链接
                if not result["cloudLinks"][0]["link"]:
                    result["cloudLinks"][0]["link"] = original_link
                    result["cloudLinks"][0]["cloudType"] = self.detect_cloud_type(original_link)
            
            return result
        except Exception as detail_error:
            print(f"处理结果项失败: {str(detail_error)}")
            return None


