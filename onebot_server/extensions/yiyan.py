"""
一言插件 (Yiyan Extension)
命令: /yiyan [分类]
统计: /yiyan-stats
API: https://v1.hitokoto.cn
特性: 批量预取缓存、循环使用、本地降级兜底
"""
import asyncio
import random
import time
from typing import Dict, List, Optional, Any
import aiohttp

from onebot_server.extension_base import BaseExtension
from onebot_server.events import GroupMessageEvent, PrivateMessageEvent
from onebot_server.actions import SendGroupMsgAction, SendPrivateMsgAction
from onebot_server.segments import build_message, TextSegment
from onebot_server.mixin.log_mixin import LogMixin

# 分类映射表
CATEGORY_MAP = {
    "a": "动画", "b": "漫画", "c": "游戏", "d": "文学",
    "e": "原创", "f": "来自网络", "g": "其他", "h": "影视",
    "i": "诗词", "j": "网易云", "k": "哲学", "l": "抖机灵",
    "动画": "a", "漫画": "b", "游戏": "c", "文学": "d",
    "诗词": "i", "网易云": "j", "哲学": "k", "抖机灵": "l", "其他": "g",
}

# 本地降级库（API挂了的时候用）
FALLBACK_SENTENCES = [
    "「山重水复疑无路，柳暗花明又一村。」 —— 陆游",
    "「路漫漫其修远兮，吾将上下而求索。」 —— 屈原",
    "「代码写得好，Bug 自然少。」 —— 鲁迅（伪）",
    "「Stay hungry, stay foolish.」 —— Steve Jobs",
    "「生活就像一盒巧克力，你永远不知道下一颗是什么味道。」 —— 《阿甘正传》",
]

class YiyanExtension(BaseExtension, LogMixin):
    """一言插件"""
    
    name = "yiyan"
    version = "1.0.0"
    author = "OneBotServer"
    description = "获取一言，支持批量缓存和分类查询"
    
    def __init__(self, handler: Any = None):
        super().__init__(handler)
        # 缓存: {category: [sentence1, sentence2, ...]}
        self._cache: Dict[str, List[str]] = {}
        self._cache_index: Dict[str, int] = {}  # 循环指针
        self._lock: Dict[str, asyncio.Lock] = {}
        self._batch_size = 20
        self._min_cache = 5
        
        # 统计
        self._stats = {
            "hits": 0, "misses": 0, "api_calls": 0, 
            "fallbacks": 0, "start_time": time.time()
        }
        self.session: Optional[aiohttp.ClientSession] = None

    async def on_load(self) -> bool:
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)
        )
        # 预热缓存（后台进行，不阻塞加载）
        asyncio.create_task(self._warmup_cache())
        self.logger.info("YiyanExtension loaded. Warming up cache...")
        return True

    async def on_unload(self) -> None:
        if self.session:
            await self.session.close()
        self.logger.info("YiyanExtension unloaded.")

    async def _warmup_cache(self):
        """预热默认分类缓存"""
        await self._ensure_cache("a")  # 动画
        await self._ensure_cache("i")  # 诗词
        await self._ensure_cache("k")  # 哲学

    async def _ensure_cache(self, category: str):
        """确保缓存充足"""
        if category not in self._cache:
            self._cache[category] = []
            self._cache_index[category] = 0
            self._lock[category] = asyncio.Lock()

        async with self._lock[category]:
            if len(self._cache[category]) < self._min_cache:
                await self._fetch_batch(category)

    async def _fetch_batch(self, category: str):
        """批量拉取一言"""
        self._stats["api_calls"] += 1
        params_list = [{"c": category} for _ in range(self._batch_size)]
        
        try:
            tasks = [
                self.session.get("https://v1.hitokoto.cn", params=p, ssl=False)
                for p in params_list
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            new_sentences = []
            for resp in results:
                if isinstance(resp, Exception):
                    continue
                if resp.status == 200:
                    data = await resp.json()
                    hitokoto = data.get("hitokoto", "")
                    from_who = data.get("from", "")
                    creator = data.get("creator", "")
                    if hitokoto:
                        text = f"「{hitokoto}」"
                        if from_who:
                            text += f" —— {from_who}"
                        elif creator:
                            text += f" —— {creator}"
                        new_sentences.append(text)
                await resp.release()
            
            if new_sentences:
                random.shuffle(new_sentences)
                self._cache[category].extend(new_sentences)
                self.logger.debug(f"Fetched {len(new_sentences)} sentences for {category}")
            else:
                # API没返回有效数据，触发降级
                raise ValueError("No valid data from API")
                
        except Exception as e:
            self.logger.warning(f"Fetch batch failed for {category}: {e}. Using fallback.")
            self._stats["fallbacks"] += 1
            if not self._cache[category]:  # 只有缓存空了才用降级
                self._cache[category].extend(FALLBACK_SENTENCES)

    def _get_next(self, category: str) -> str:
        """循环获取下一句"""
        if category not in self._cache or not self._cache[category]:
            return random.choice(FALLBACK_SENTENCES)
        
        idx = self._cache_index[category]
        sentence = self._cache[category][idx]
        
        # 移动指针
        self._cache_index[category] = (idx + 1) % len(self._cache[category])
        
        # 如果快用完了，后台补充
        if self._cache_index[category] < self._min_cache:
            asyncio.create_task(self._fetch_batch(category))
            
        return sentence

    async def on_group_message(self, event: GroupMessageEvent):
        text = event.get_text().strip()
        
        if text == "/yiyan-stats":
            await self._show_stats(event)
            return
            
        if text.startswith("/yiyan"):
            parts = text.split(maxsplit=1)
            category_input = parts[1].strip() if len(parts) > 1 else "a"
            category = CATEGORY_MAP.get(category_input, "a")
            
            await self._ensure_cache(category)
            sentence = self._get_next(category)
            self._stats["hits"] += 1
            
            await event.reply_text(sentence)
            return

    async def on_private_message(self, event: PrivateMessageEvent):
        text = event.get_text().strip()
        if text.startswith("/yiyan"):
            parts = text.split(maxsplit=1)
            category_input = parts[1].strip() if len(parts) > 1 else "a"
            category = CATEGORY_MAP.get(category_input, "a")
            
            await self._ensure_cache(category)
            sentence = self._get_next(category)
            
            action = SendPrivateMsgAction(
                user_id=event.user_id,
                message=build_message(TextSegment(sentence))
            )
            await self.handler.client.send(action)

    async def _show_stats(self, event: GroupMessageEvent):
        uptime = time.time() - self._stats["start_time"]
        cache_total = sum(len(v) for v in self._cache.values())
        
        msg = (
            f"一言插件统计:\n"
            f"运行时间: {uptime:.1f}s\n"
            f"缓存总量: {cache_total}\n"
            f"命中次数: {self._stats['hits']}\n"
            f"API调用: {self._stats['api_calls']}\n"
            f"降级次数: {self._stats['fallbacks']}"
        )
        await event.reply_text(msg)

    async def on_console_command(self, command: str, args: List[str]) -> Optional[str]:
        """控制台命令支持"""
        if command == "yiyan-stats":
            uptime = time.time() - self._stats["start_time"]
            cache_total = sum(len(v) for v in self._cache.values())
            return (
                f"Yiyan Stats:\n"
                f"Uptime: {uptime:.1f}s\n"
                f"Cache: {cache_total}\n"
                f"Hits: {self._stats['hits']}\n"
                f"API: {self._stats['api_calls']}\n"
                f"Fallback: {self._stats['fallbacks']}"
            )
        return None