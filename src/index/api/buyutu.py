import base64
import hashlib
import requests
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from ..base import BaseSearch
from typing import List, Dict, Any


def decrypt_data(encrypted_data, secret_key):
    """
    解密函数，与 test2.js 中的 _0x2215d5 方法功能一致
    :param encrypted_data: Base64编码的加密数据
    :param secret_key: 解密密钥
    :return: 解密后的字符串
    """
    # 生成SHA256哈希
    sha256 = hashlib.sha256(secret_key.encode()).hexdigest()
    
    # 处理key和iv
    key_hex = sha256[:64]  # 取前64个字符
    iv_hex = sha256[:32]   # 取前32个字符
    
    # 将16进制字符串转换为WordArray类似的结构
    def hex_to_word_array(hex_str):
        words = []
        i = 0
        while i < len(hex_str):
            # 每8个字符(4字节)转换为一个32位整数
            word = int(hex_str[i:i+2], 16) << 24 | \
                   int(hex_str[i+2:i+4], 16) << 16 | \
                   int(hex_str[i+4:i+6], 16) << 8 | \
                   int(hex_str[i+6:i+8], 16)
            words.append(word)
            i += 8
        return words
    
    # 创建AES解密器
    key_words = hex_to_word_array(key_hex)
    iv_words = hex_to_word_array(iv_hex)
    
    # 将WordArray转换为字节
    key_bytes = b''.join([word.to_bytes(4, 'big') for word in key_words])
    iv_bytes = b''.join([word.to_bytes(4, 'big') for word in iv_words])
    
    # 解密
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv=iv_bytes)
    decrypted = cipher.decrypt(base64.b64decode(encrypted_data))
    
    # 移除填充并返回UTF-8字符串
    return unpad(decrypted, AES.block_size).decode('utf-8')


class BuyutuSearch(BaseSearch):
    """捕娱兔搜索实现"""

    def __init__(self, use_playwright: bool = False):
        self.use_playwright = use_playwright
        self._key_cache = {}  # 缓存页面URL到密钥的映射

    def search(self, keyword: str) -> List[Dict[str, Any]]:
        """搜索捕娱兔资源并返回结构化结果

        Args:
            keyword: 搜索关键词

        Returns:
            标准化的结果列表，包含完整元数据
        """
        return self._search_with_api(keyword)

    def _get_real_link(self, detail_url: str, page_url: str) -> str:
        """获取真实的网盘链接
        Args:
            detail_url: 详情页URL
            page_url: 搜索页URL(用于缓存key)
        """
        try:
            # 统一获取详情页内容和密文
            response = requests.get(
                detail_url,
                timeout=10,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'
                }
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            encrypted_data = soup.find('input', {'id': 'encryptedData'})
            if not encrypted_data or 'value' not in encrypted_data.attrs:
                return ""

            # 优先使用缓存密钥
            if page_url in self._key_cache:
                try:
                    decrypted = decrypt_data(encrypted_data['value'], self._key_cache[page_url])
                    print(f"使用缓存密钥解密成功: {self._key_cache[page_url][:8]}...")
                    return decrypted
                except Exception as e:
                    print(f"缓存密钥解密失败({str(e)}), 将重新解析detail.js")
            
            # 提取加密数据
            encrypted_data = soup.find('input', {'id': 'encryptedData'})
            if not encrypted_data or 'value' not in encrypted_data.attrs:
                return ""
                
            # 从页面中提取detail.js路径
            detail_js = soup.find('script', {'src': lambda x: x and 'detail.js' in x})
            if not detail_js:
                return ""
                
            detail_js_path = detail_js['src']
            # 处理相对路径
            if detail_js_path.startswith('../'):
                detail_js_path = detail_js_path.replace('../', '/')
            # 补全为完整URL
            if not detail_js_path.startswith('http'):
                detail_js_url = f"https://buyutu.com{detail_js_path}"
            else:
                detail_js_url = detail_js_path
                
            # 下载detail.js文件
            js_response = requests.get(detail_js_url)
            js_response.raise_for_status()
            
            # 创建临时文件处理反混淆(静默模式)
            import tempfile
            import os
            import subprocess
            
            with tempfile.NamedTemporaryFile(suffix='.js', delete=False) as tmp:
                tmp.write(js_response.content)
                tmp_path = tmp.name
                
            # 设置静默模式环境变量
            env = os.environ.copy()
            env['OBFUSCATOR_SILENT'] = '1'
                
            try:
                # 反混淆JS代码
                output_path = f"{tmp_path}.deobfuscated.js"
                subprocess.run([
                    'obfuscator-io-deobfuscator',
                    tmp_path,
                    '-o', output_path
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # 读取反混淆后的代码
                with open(output_path, 'r') as f:
                    deobfuscated_js = f.read()
                
                # 从JS代码中提取解密密钥
                def extract_secret_key(js_code):
                    import re
                    # 匹配202行附近的解密函数调用模式
                    pattern = r'_0x\w+\(_0x\w+,\s*"([^"]+)"\)'
                    match = re.search(pattern, js_code)
                    if match:
                        return match.group(1)
                    return None
                
                secret_key = extract_secret_key(deobfuscated_js)
                if not secret_key:
                    print("无法从JS代码中提取解密密钥")
                    return encrypted_data['value']
                
                # 成功解析密钥后更新缓存
                self._key_cache[page_url] = secret_key
                
                try:
                    decrypted = decrypt_data(encrypted_data['value'], secret_key)
                    return decrypted
                except Exception as e:
                    print(f"解密失败: {str(e)}")
                    return encrypted_data['value']
            except Exception as e:
                print(f"JS反混淆处理失败: {str(e)}")
                return encrypted_data['value']
            finally:
                # 清理临时文件
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                if os.path.exists(output_path):
                    os.unlink(output_path)
        except Exception as e:
            print(f"获取真实链接失败: {str(e)}")
            return ""

    def _search_with_api(self, keyword: str) -> List[Dict[str, Any]]:
        """通过API搜索"""
        # 先base64编码，再URL编码
        from urllib.parse import quote
        base64_keyword = base64.b64encode(keyword.encode('utf-8')).decode('utf-8')
        encoded_keyword = quote(base64_keyword)
        url = f"https://buyutu.com/s/{encoded_keyword}"
        try:
            # 获取搜索结果页
            response = requests.get(
                url,
                timeout=10,
                headers={
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
                    'cache-control': 'no-cache',
                    'pragma': 'no-cache',
                    'priority': 'u=0, i',
                    'referer': url,  # 使用当前URL作为referer
                    'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"macOS"',
                    'sec-fetch-dest': 'document',
                    'sec-fetch-mode': 'navigate',
                    'sec-fetch-site': 'same-origin',
                    'sec-fetch-user': '?1',
                    'upgrade-insecure-requests': '1',
                    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
                    'origin': 'https://buyutu.com'
                }
            )
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            result_items = soup.select('.card.yinyin-sm')
            
            results = []
            for item in result_items:
                try:
                    # 提取标题部分
                    title_card = item.select_one('#title .card-body')
                    if not title_card:
                        continue
                        
                    title_link = title_card.select_one('a')
                    title_img = title_card.select_one('img')
                    
                    # 提取内容部分
                    body_card = item.select_one('#body .card-body')
                    if not body_card:
                        continue
                        
                    cloud_span = body_card.select_one('#cloud')
                    date_span = body_card.select_one('#calendar')
                    user_span = body_card.select_one('#user')
                    
                    if not all([title_link, cloud_span, date_span, user_span]):
                        continue
                    
                    # 提取文件类型
                    file_type = 'dir'  # 默认为文件夹
                    if title_img and 'src' in title_img.attrs:
                        if 'txt.png' in title_img['src']:
                            file_type = 'txt'
                    
                    # 提取网盘类型
                    cloud_img = cloud_span.find('img')
                    cloud_type = 'unknown'
                    if cloud_img and 'src' in cloud_img.attrs:
                        if 'quark.png' in cloud_img['src']:
                            cloud_type = 'quark'
                        elif 'alipan.png' in cloud_img['src']:
                            cloud_type = 'alipan'
                        elif 'xunlei.png' in cloud_img['src']:
                            cloud_type = 'xunlei'
                        elif 'baidu.png' in cloud_img['src']:
                            cloud_type = 'baidu'
                    
                    # 提取发布日期
                    pub_date = "1970-01-01T00:00:00+00:00"
                    if date_span and date_span.text.strip():
                        date_str = date_span.text.strip().replace('\n', '').replace(' ', '')
                        pub_date = f"{date_str}T00:00:00+00:00"
                    
                    # 提取用户信息
                    user_info = user_span.text.strip().replace('\n', '').replace(' ', '')
                    
                    # 获取真实链接
                    detail_url = f"https://buyutu.com{title_link['href'].replace('../', '/')}"
                    real_link = self._get_real_link(detail_url, url)
                    
                    results.append({
                        "messageId": title_link['href'].split('/')[-1].replace('.html', ''),
                        "title": title_link.get('title', '').strip(),
                        "pubDate": pub_date,
                        "content": title_link.get('title', '').strip(),
                        "fileType": file_type,
                        "uploader": user_info,
                        "cloudLinks": [{
                            "link":real_link,
                            "cloudType": self.detect_cloud_type(real_link)
                        }],
                        "tags": [],
                        "magnetLink": "",
                        "channel": "捕娱兔",
                        "channelId": "buyutu"
                    })
                except Exception as e:
                    print(f"解析结果项失败: {str(e)}")
                    continue
            
            return {
                "list": results,
                "channelInfo": {
                    "id": "buyutu",
                    "name": "捕娱兔",
                    "index": 1001,
                    "channelLogo": ""
                },
                "id": "buyutu_search",
                "index": 15,
                "total": len(results),
                "keyword": keyword
            }

        except Exception as e:
            print(f"捕娱兔搜索失败: {str(e)}")
            return []