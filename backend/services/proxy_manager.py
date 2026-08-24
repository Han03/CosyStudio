"""代理服务管理器。

用于获取维基百科等外部数据,支持自动获取配置、节点测试、最优节点选择。

功能特性:
- 项目启动时异步获取代理订阅配置并缓存
- 解析代理节点(支持多种协议)
- 测试节点延迟并选出最优节点
- 每隔5分钟重新测试节点并更新最优节点
- 提供统一的代理访问方法

注意:代理协议(如 ss/vmess/trojan)需要外部代理客户端支持,
本管理器通过启动 xray-core 子进程创建本地 SOCKS5 代理。
"""

import os
import json
import time
import asyncio
import logging
import subprocess
import socket
import base64
import urllib.parse
from typing import Optional, List, Dict, Any, Tuple

import requests
import gzip
from io import BytesIO

import aiohttp
from aiohttp_socks import ProxyConnector

logger = logging.getLogger(__name__)

_SUBSCRIPTION_URL = "https://maxh.ccwu.cc/sub?token=5919063a43aed3e43afb81c08f59eeb8"
from core.paths import CACHE_DIR as _CACHE_DIR, BIN_DIR
_CACHE_FILE = os.path.join(_CACHE_DIR, "proxy_config.json")
_TEST_URL = "https://www.google.com/generate_204"
_TEST_TIMEOUT = 10
_REFRESH_INTERVAL = 600
_LOCAL_SOCKS_PORT = 10808
_TOP_CANDIDATES = 3


class ProxyManager:
    """代理服务管理器。"""

    def __init__(self):
        self._nodes: List[Dict[str, Any]] = []
        self._best_node: Optional[Dict[str, Any]] = None
        self._proxy_process: Optional[subprocess.Popen] = None
        self._refresh_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._is_initialized = False
        self._is_initializing = False

    async def initialize(self):
        """异步初始化:加载缓存、获取配置、测试节点。"""
        await self._load_cache()
        await self._fetch_and_parse_config()
        await self._test_and_select_best_node()
        self._start_refresh_loop()
        self._is_initialized = True
        logger.info("[Proxy] 代理管理器初始化完成")

    async def lazy_initialize(self):
        """懒加载初始化:仅在首次需要时初始化。"""
        async with self._lock:
            if self._is_initialized:
                return
            if self._is_initializing:
                while not self._is_initialized:
                    await asyncio.sleep(0.1)
                return
            self._is_initializing = True
        try:
            await self._load_cache()
            await self._fetch_and_parse_config()
            await self._test_and_select_best_node()
            self._start_refresh_loop()
            self._is_initialized = True
            logger.info("[Proxy] 代理管理器懒加载初始化完成")
        finally:
            self._is_initializing = False

    async def fetch(self, url: str, timeout: int = 30) -> Optional[str]:
        """通过代理访问指定 URL 并返回响应内容(文本)。"""
        if not self._is_initialized:
            await self.lazy_initialize()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        if self._best_node:
            try:
                connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{_LOCAL_SOCKS_PORT}")
                async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                    async with session.get(url, headers=headers, ssl=False) as response:
                        return await response.text()
            except Exception as e:
                logger.warning(f"[Proxy] 通过代理访问失败,尝试直接连接: {e}")

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                async with session.get(url, headers=headers, ssl=False) as response:
                    return await response.text()
        except Exception as e:
            logger.warning(f"[Proxy] 直接连接也失败: {e}")
            return None

    async def fetch_with_meta(self, url: str, timeout: int = 30) -> Optional[Dict[str, Any]]:
        """通过代理访问指定 URL，返回响应文本、Content-Type 与状态码。

        返回: {"content": str, "content_type": str, "status": int} 或 None。
        用于第二步接口校验（判断是否 application/json）。
        """
        if not self._is_initialized:
            await self.lazy_initialize()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        async def _do(session):
            async with session.get(url, headers=headers, ssl=False) as response:
                content = await response.text()
                return {
                    "content": content,
                    "content_type": response.headers.get("Content-Type", ""),
                    "status": response.status,
                }

        if self._best_node:
            try:
                connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{_LOCAL_SOCKS_PORT}")
                async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                    return await _do(session)
            except Exception as e:
                logger.warning(f"[Proxy] 通过代理访问失败,尝试直接连接: {e}")

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                return await _do(session)
        except Exception as e:
            logger.warning(f"[Proxy] 直接连接也失败: {e}")
            return None

    async def fetch_post(self, url: str, data: Dict[str, str], timeout: int = 30) -> Optional[str]:
        """通过代理 POST 请求并返回响应内容(文本)。

        data: 表单字段字典，以 application/x-www-form-urlencoded 发送。
        用于 DuckDuckGo 分页搜索等需要 POST 的场景。
        """
        if not self._is_initialized:
            await self.lazy_initialize()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        async def _do(session):
            async with session.post(url, data=data, headers=headers, ssl=False) as response:
                return await response.text()

        if self._best_node:
            try:
                connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{_LOCAL_SOCKS_PORT}")
                async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                    return await _do(session)
            except Exception as e:
                logger.warning(f"[Proxy] 通过代理 POST 失败,尝试直接连接: {e}")

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                return await _do(session)
        except Exception as e:
            logger.warning(f"[Proxy] 直接 POST 也失败: {e}")
            return None

    async def fetch_html(self, url: str, timeout: int = 30) -> Optional[str]:
        """通过代理 GET 请求 HTML 页面并返回响应文本。

        与 fetch() 的区别：使用简单 UA + text/html Accept 头，
        专门用于搜索引擎 HTML 抓取（DuckDuckGo/Bing）。

        关键：DuckDuckGo 会检测 Accept: application/json 的请求为爬虫并返回验证码页，
        必须使用 text/html Accept 才能正常获取搜索结果。
        """
        if not self._is_initialized:
            await self.lazy_initialize()
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        async def _do(session):
            async with session.get(url, headers=headers, ssl=False, allow_redirects=True) as response:
                return await response.text()

        if self._best_node:
            try:
                connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{_LOCAL_SOCKS_PORT}")
                async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                    return await _do(session)
            except Exception as e:
                logger.warning(f"[Proxy] 通过代理获取HTML失败,尝试直接连接: {e}")

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                return await _do(session)
        except Exception as e:
            logger.warning(f"[Proxy] 直接获取HTML也失败: {e}")
            return None

    async def fetch_binary(self, url: str, timeout: int = 30) -> Optional[bytes]:
        """通过代理访问指定 URL 并返回响应内容(二进制)。"""
        if not self._is_initialized:
            await self.lazy_initialize()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        if self._best_node:
            try:
                connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{_LOCAL_SOCKS_PORT}")
                async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                    async with session.get(url, headers=headers) as response:
                        return await response.read()
            except Exception as e:
                logger.warning(f"[Proxy] 通过代理下载二进制失败,尝试直接连接: {e}")

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                async with session.get(url, headers=headers) as response:
                    return await response.read()
        except Exception as e:
            logger.warning(f"[Proxy] 直接下载也失败: {e}")
            return None

    async def close(self):
        """关闭代理管理器,清理资源。"""
        if self._refresh_task:
            self._refresh_task.cancel()
        self._stop_local_proxy()

    async def _load_cache(self):
        """从缓存文件加载代理配置。"""
        if os.path.exists(_CACHE_FILE):
            try:
                with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._nodes = data.get("nodes", [])
                    self._best_node = data.get("best_node")
                logger.info(f"[Proxy] 从缓存加载 {len(self._nodes)} 个节点")
            except Exception as e:
                logger.warning(f"[Proxy] 加载缓存失败: {e}")

    async def _fetch_and_parse_config(self):
        """从订阅 URL 获取配置并解析节点。"""
        try:
            logger.info("[Proxy] 正在获取代理配置...")
            response = requests.get(_SUBSCRIPTION_URL)
            encoding = response.headers.get('Content-Encoding')
            if encoding == 'gzip':
                try:
                    buf = BytesIO(response.content)
                    gf = gzip.GzipFile(fileobj=buf)
                    content = gf.read().decode('utf-8')
                except gzip.BadGzipFile:
                    content = response.text
            else:
                content = response.text
            await self._parse_config(content)
            await self._save_cache()
            logger.info(f"[Proxy] 获取配置成功,解析出 {len(self._nodes)} 个节点")
        except Exception as e:
            logger.warning(f"[Proxy] 获取配置失败: {e}, 使用缓存配置")

    async def _parse_config(self, content: str):
        """解析订阅配置内容。

        订阅内容格式:
        - Base64 编码的文本,解码后每行一个代理链接
        - 支持 vless://, vmess://, ss:// 等格式
        """
        self._nodes = []

        decoded = content
        try:
            decoded = base64.b64decode(content).decode("utf-8")
            logger.debug("[Proxy] 配置是 Base64 编码格式")
        except Exception:
            logger.debug("[Proxy] 配置是纯文本格式")

        for line in decoded.strip().splitlines():
            line = line.strip()
            if not line:
                continue

            node = None
            if line.startswith("vless://"):
                node = self._parse_vless_link(line)
            elif line.startswith("vmess://"):
                node = self._parse_vmess_link(line)
            elif line.startswith("ss://"):
                node = self._parse_ss_link(line)
            elif line.startswith("trojan://"):
                node = self._parse_trojan_link(line)

            if node:
                self._nodes.append(node)

    def _parse_vless_link(self, link: str) -> Optional[Dict[str, Any]]:
        """解析 vless 格式的代理链接。

        格式: vless://<uuid>@<host>:<port>?<params>#<remark>

        示例: vless://4993466f-7c4b-4b70-8e7d-1c73daf88011@162.159.37.183:2087?security=tls&type=ws&host=maxh.ccwu.cc&fp=chrome&sni=maxh.ccwu.cc&path=%2F&encryption=none#CF电信优选1

        参数说明:
        - security: tls 或 none
        - type: ws(websocket), tcp, http, grpc
        - host: ws host header
        - path: ws path
        - sni: TLS SNI
        - fp: fingerprint
        - encryption: none
        """
        try:
            url = link.replace("vless://", "http://")
            parsed = urllib.parse.urlparse(url)

            uuid = parsed.username or ""
            host = parsed.hostname or ""
            port = parsed.port or 443

            params = urllib.parse.parse_qs(parsed.query)
            remark = urllib.parse.unquote(parsed.fragment) if parsed.fragment else ""

            proxy_type = params.get("type", ["tcp"])[0]
            security = params.get("security", ["tls"])[0]

            node = {
                "name": remark if remark else f"{host}:{port}",
                "type": "vless",
                "server": host,
                "port": port,
                "uuid": uuid,
                "security": security,
                "network": proxy_type,
                "sni": params.get("sni", [host])[0],
                "fp": params.get("fp", ["chrome"])[0],
            }

            if proxy_type == "ws":
                node["ws-opts"] = {
                    "path": urllib.parse.unquote(params.get("path", ["/"])[0]),
                    "headers": {"Host": params.get("host", [host])[0]},
                }
            elif proxy_type == "http":
                node["ws-opts"] = {
                    "path": urllib.parse.unquote(params.get("path", ["/"])[0]),
                }

            return node
        except Exception as e:
            logger.debug(f"[Proxy] 解析 vless 链接失败: {e}")
            return None

    def _parse_vmess_link(self, link: str) -> Optional[Dict[str, Any]]:
        """解析 vmess 格式的代理链接。"""
        try:
            encoded = link[8:]
            padding = 4 - (len(encoded) % 4)
            if padding != 4:
                encoded += "=" * padding
            decoded = base64.b64decode(encoded).decode("utf-8")
            data = json.loads(decoded)

            return {
                "name": data.get("ps", ""),
                "type": "vmess",
                "server": data.get("add", ""),
                "port": int(data.get("port", 0)),
                "uuid": data.get("id", ""),
                "alterId": int(data.get("aid", 0)),
                "cipher": data.get("scy", "auto"),
                "network": data.get("net", "tcp"),
                "security": data.get("tls", ""),
                "sni": data.get("sni", ""),
            }
        except Exception as e:
            logger.debug(f"[Proxy] 解析 vmess 链接失败: {e}")
            return None

    def _parse_ss_link(self, link: str) -> Optional[Dict[str, Any]]:
        """解析 shadowsocks 格式的代理链接。"""
        try:
            encoded = link[5:]
            if "#" in encoded:
                encoded, name = encoded.rsplit("#", 1)
                name = urllib.parse.unquote(name)
            else:
                name = ""

            padding = 4 - (len(encoded) % 4)
            if padding != 4:
                encoded += "=" * padding

            decoded = base64.b64decode(encoded).decode("utf-8")
            if ":" in decoded:
                cipher_pwd, server_port = decoded.rsplit("@", 1)
                cipher, password = cipher_pwd.split(":", 1)
                server, port = server_port.split(":", 1)

                return {
                    "name": name if name else f"{server}:{port}",
                    "type": "ss",
                    "server": server,
                    "port": int(port),
                    "password": password,
                    "cipher": cipher,
                }
        except Exception as e:
            logger.debug(f"[Proxy] 解析 ss 链接失败: {e}")
            return None

    def _parse_trojan_link(self, link: str) -> Optional[Dict[str, Any]]:
        """解析 trojan 格式的代理链接。"""
        try:
            url = link.replace("trojan://", "http://")
            parsed = urllib.parse.urlparse(url)

            password = parsed.username or ""
            host = parsed.hostname or ""
            port = parsed.port or 443

            params = urllib.parse.parse_qs(parsed.query)
            remark = urllib.parse.unquote(parsed.fragment) if parsed.fragment else ""

            return {
                "name": remark if remark else f"{host}:{port}",
                "type": "trojan",
                "server": host,
                "port": port,
                "password": password,
                "sni": params.get("sni", [host])[0],
                "network": params.get("type", ["tcp"])[0],
            }
        except Exception as e:
            logger.debug(f"[Proxy] 解析 trojan 链接失败: {e}")
            return None

    async def _save_cache(self):
        """保存配置到缓存文件。"""
        try:
            os.makedirs(_CACHE_DIR, exist_ok=True)
            with open(_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "nodes": self._nodes,
                    "best_node": self._best_node,
                    "updated_at": time.time(),
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[Proxy] 保存缓存失败: {e}")

    async def _test_and_select_best_node(self):
        """测试所有节点延迟,选择最优节点。"""
        if not self._nodes:
            logger.warning("[Proxy] 没有可用节点")
            return

        logger.info(f"[Proxy] 正在测试 {len(self._nodes)} 个节点...")

        if len(self._nodes) <= _TOP_CANDIDATES:
            candidates = self._nodes
        else:
            candidates = await self._quick_tcp_test(self._nodes)

        if not candidates:
            logger.warning("[Proxy] 没有可达节点")
            return

        best_node = None
        best_latency = float("inf")

        for node in candidates:
            latency = await self._test_node_http(node)
            if latency < best_latency:
                best_latency = latency
                best_node = node

        if best_node:
            self._best_node = best_node
            logger.info(f"[Proxy] 最优节点: {best_node['name']}, 延迟: {best_latency:.2f}ms")
            await self._start_local_proxy(best_node)
            await self._save_cache()
        else:
            logger.warning("[Proxy] 没有可用节点")

    async def _quick_tcp_test(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """快速 TCP 连接测试,返回延迟最低的 Top N 个节点。"""
        async def test_tcp(node):
            latency = await self._tcp_ping(node["server"], node["port"])
            return node, latency

        tasks = [test_tcp(node) for node in nodes]
        results = await asyncio.gather(*tasks)

        results = [(node, latency) for node, latency in results if latency != float("inf")]
        results.sort(key=lambda x: x[1])

        top_results = results[:_TOP_CANDIDATES]
        logger.info(f"[Proxy] TCP测试完成,筛选出 {len(top_results)} 个候选节点")
        return [node for node, _ in top_results]

    async def _tcp_ping(self, host: str, port: int) -> float:
        """TCP 连接延迟测试(毫秒)。"""
        start = time.time()
        try:
            loop = asyncio.get_event_loop()
            await loop.sock_connect(socket.socket(socket.AF_INET, socket.SOCK_STREAM), (host, port))
            return (time.time() - start) * 1000
        except Exception:
            return float("inf")

    async def _test_node_http(self, node: Dict[str, Any]) -> float:
        """通过 xray 测试节点的完整 HTTP 延迟。"""
        start = time.time()
        try:
            await self._start_local_proxy(node)
            await asyncio.sleep(0.5)

            connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{_LOCAL_SOCKS_PORT}")
            async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=_TEST_TIMEOUT)) as session:
                async with session.get(_TEST_URL):
                    pass

            latency = (time.time() - start) * 1000
            logger.debug(f"[Proxy] 节点 {node['name']} HTTP延迟: {latency:.2f}ms")
            return latency
        except Exception:
            self._stop_local_proxy()
            return float("inf")

    async def _start_local_proxy(self, node: Dict[str, Any]):
        """启动本地代理客户端(xray-core)。"""
        self._stop_local_proxy()

        xray_config = self._generate_xray_config(node)
        config_path = os.path.join(_CACHE_DIR, "xray_config.json")

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(xray_config, f, ensure_ascii=False, indent=2)

            xray_path = self._find_xray_binary()
            if not xray_path:
                logger.warning("[Proxy] 未找到 xray-core 二进制文件,跳过启动")
                return

            self._proxy_process = subprocess.Popen(
                [xray_path, "run", "-c", config_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info(f"[Proxy] 本地代理启动,端口 {_LOCAL_SOCKS_PORT}")
        except Exception as e:
            logger.warning(f"[Proxy] 启动本地代理失败: {e}")

    def _stop_local_proxy(self):
        """停止本地代理客户端。"""
        if self._proxy_process:
            try:
                self._proxy_process.terminate()
                self._proxy_process.wait(timeout=5)
            except Exception:
                try:
                    self._proxy_process.kill()
                except Exception:
                    pass
            self._proxy_process = None
            logger.info("[Proxy] 本地代理已停止")

    def _generate_xray_config(self, node: Dict[str, Any]) -> Dict[str, Any]:
        """生成 xray-core 配置文件。"""
        proxy_type = node["type"]
        outbounds = []

        if proxy_type == "ss":
            outbounds.append({
                "tag": "proxy",
                "protocol": "shadowsocks",
                "settings": {
                    "servers": [{
                        "address": node["server"],
                        "port": node["port"],
                        "method": node["cipher"],
                        "password": node["password"],
                    }]
                },
            })
        elif proxy_type == "vmess":
            outbounds.append({
                "tag": "proxy",
                "protocol": "vmess",
                "settings": {
                    "vnext": [{
                        "address": node["server"],
                        "port": node["port"],
                        "users": [{
                            "id": node["uuid"],
                            "alterId": node.get("alterId", 0),
                            "security": node.get("cipher", "auto"),
                        }]
                    }]
                },
                "streamSettings": self._get_stream_settings(node),
            })
        elif proxy_type == "vless":
            outbounds.append({
                "tag": "proxy",
                "protocol": "vless",
                "settings": {
                    "vnext": [{
                        "address": node["server"],
                        "port": node["port"],
                        "users": [{
                            "id": node["uuid"],
                            "encryption": "none",
                            "security": node.get("security", "tls"),
                        }]
                    }]
                },
                "streamSettings": self._get_stream_settings(node),
            })
        elif proxy_type == "trojan":
            outbounds.append({
                "tag": "proxy",
                "protocol": "trojan",
                "settings": {
                    "servers": [{
                        "address": node["server"],
                        "port": node["port"],
                        "password": node["password"],
                    }]
                },
                "streamSettings": self._get_stream_settings(node),
            })
        else:
            outbounds.append({
                "tag": "proxy",
                "protocol": "freedom",
            })

        return {
            "log": {
                "loglevel": "warning",
            },
            "inbounds": [{
                "port": _LOCAL_SOCKS_PORT,
                "protocol": "socks",
                "settings": {
                    "auth": "noauth",
                    "udp": True,
                },
            }],
            "outbounds": outbounds + [{
                "tag": "direct",
                "protocol": "freedom",
            }],
            "routing": {
                "rules": [{
                    "type": "field",
                    "outboundTag": "proxy",
                    "network": "tcp,udp",
                }],
            },
        }

    def _get_stream_settings(self, node: Dict[str, Any]) -> Dict[str, Any]:
        """获取流设置。"""
        network = node.get("network", "tcp")
        settings = {"network": network}

        security = node.get("security", "")
        if security == "tls":
            settings["security"] = "tls"
            settings["tlsSettings"] = {
                "serverName": node.get("sni", node.get("server", "")),
                "fingerprint": node.get("fp", "chrome"),
            }

        if network == "ws":
            ws_opts = node.get("ws-opts", {})
            settings["wsSettings"] = {
                "path": ws_opts.get("path", "/"),
                "headers": ws_opts.get("headers", {}),
            }
        elif network == "http":
            settings["httpSettings"] = {
                "path": "/",
            }

        return settings

    def _find_xray_binary(self) -> Optional[str]:
        """查找 xray-core 二进制文件。"""
        candidates = [
            os.path.join(BIN_DIR, "xray", "xray.exe"),
        ]

        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate

        return None

    def _start_refresh_loop(self):
        """启动定时刷新循环。"""
        async def refresh_loop():
            while True:
                await asyncio.sleep(_REFRESH_INTERVAL)
                logger.info("[Proxy] 定时刷新节点测试")
                await self._fetch_and_parse_config()
                await self._test_and_select_best_node()

        self._refresh_task = asyncio.create_task(refresh_loop())

    def get_best_node(self) -> Optional[Dict[str, Any]]:
        """获取当前最优节点。"""
        return self._best_node

    def get_nodes(self) -> List[Dict[str, Any]]:
        """获取所有节点列表。"""
        return self._nodes

    def is_initialized(self) -> bool:
        """检查管理器是否已初始化。"""
        return self._is_initialized


_proxy_manager = None


def get_proxy_manager() -> ProxyManager:
    """获取全局代理管理器单例。"""
    global _proxy_manager
    if _proxy_manager is None:
        _proxy_manager = ProxyManager()
    return _proxy_manager


async def init_proxy_manager():
    """异步初始化代理管理器(供启动时调用)。"""
    manager = get_proxy_manager()
    await manager.initialize()
