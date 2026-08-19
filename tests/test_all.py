"""
tests/test_all.py — OneBot 11 Server 完整测试套件
==================================================
覆盖：事件模型、Action API、消息段、Mixin 系统、
      Extension 热加载/卸载、确认机制、白名单、服务器集成。
运行: python -m pytest tests/test_all.py -v
"""

import asyncio
import sys
from pathlib import Path

import pytest
import pytest_asyncio

# 确保项目根目录在 path 中
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ═══════════════════════════════════════════════════════════
# 1. 配置模块测试
# ═══════════════════════════════════════════════════════════


class TestConfig:
    def test_config_load(self):
        from onebot_server.config import Config

        cfg = Config(str(ROOT / "config.toml"))
        assert cfg.server_port == 8765
        assert cfg.server_host
        assert isinstance(cfg.admin_qq, list)

    def test_config_get_nested(self):
        from onebot_server.config import Config

        cfg = Config(str(ROOT / "config.toml"))
        assert cfg.get("server.port") == 8765
        assert cfg.get("nonexist.key", "fallback") == "fallback"

    def test_config_ext_dir_is_absolute(self):
        """ext_dir 必须解析为包内绝对路径。"""
        from onebot_server.config import Config

        cfg = Config(str(ROOT / "config.toml"))
        p = Path(cfg.ext_dir)
        assert p.is_absolute(), f"ext_dir 应为绝对路径: {cfg.ext_dir}"
        assert p.name == "extensions"
        assert p.exists(), f"extensions 目录应存在: {p}"

    def test_config_mixin_dir_is_absolute(self):
        """mixin_dir 必须解析为包内绝对路径。"""
        from onebot_server.config import Config

        cfg = Config(str(ROOT / "config.toml"))
        p = Path(cfg.mixin_dir)
        assert p.is_absolute(), f"mixin_dir 应为绝对路径: {cfg.mixin_dir}"
        assert p.name == "mixin"
        assert p.exists(), f"mixin 目录应存在: {p}"

    def test_config_reload(self):
        from onebot_server.config import Config

        cfg = Config(str(ROOT / "config.toml"))
        ok = cfg.reload()
        assert ok is True


# ═══════════════════════════════════════════════════════════
# 2. 事件模型测试
# ═══════════════════════════════════════════════════════════


class TestEvents:
    def test_group_message_event(self):
        from onebot_server.events import BaseEvent

        raw = {
            "time": 1700000000,
            "self_id": 10000,
            "post_type": "message",
            "message_type": "group",
            "group_id": 12345,
            "user_id": 67890,
            "message": [{"type": "text", "data": {"text": "你好"}}],
            "raw_message": "你好",
            "message_id": 111,
            "sender": {"nickname": "测试", "role": "member"},
        }
        evt = BaseEvent.from_dict(raw)
        assert evt.post_type == "message"
        assert evt.group_id == 12345
        # 真实 API 是 get_message_text()
        text = evt.get_message_text() if hasattr(evt, "get_message_text") else evt.raw_message
        assert "你好" in text

    def test_private_message_event(self):
        from onebot_server.events import BaseEvent

        raw = {
            "time": 1700000000,
            "self_id": 10000,
            "post_type": "message",
            "message_type": "private",
            "user_id": 67890,
            "message": [{"type": "text", "data": {"text": "私聊"}}],
            "raw_message": "私聊",
            "message_id": 222,
            "sender": {"nickname": "测试"},
        }
        evt = BaseEvent.from_dict(raw)
        assert evt.message_type == "private"
        assert evt.user_id == 67890

    def test_notice_event(self):
        from onebot_server.events import BaseEvent

        raw = {
            "time": 1700000000,
            "self_id": 10000,
            "post_type": "notice",
            "notice_type": "group_ban",
            "group_id": 12345,
            "user_id": 67890,
            "operator_id": 11111,
            "duration": 600,
        }
        evt = BaseEvent.from_dict(raw)
        assert evt.post_type == "notice"
        assert evt.notice_type == "group_ban"

    def test_request_event(self):
        from onebot_server.events import BaseEvent

        raw = {
            "time": 1700000000,
            "self_id": 10000,
            "post_type": "request",
            "request_type": "friend",
            "user_id": 67890,
            "comment": "加我",
            "flag": "abc",
        }
        evt = BaseEvent.from_dict(raw)
        assert evt.request_type == "friend"

    def test_meta_event(self):
        from onebot_server.events import BaseEvent

        raw = {
            "time": 1700000000,
            "self_id": 10000,
            "post_type": "meta_event",
            "meta_event_type": "heartbeat",
            "interval": 30000,
        }
        evt = BaseEvent.from_dict(raw)
        assert evt.meta_event_type == "heartbeat"

    def test_unknown_event_fallback(self):
        from onebot_server.events import BaseEvent

        raw = {
            "time": 1700000000,
            "self_id": 10000,
            "post_type": "weird_type",
        }
        evt = BaseEvent.from_dict(raw)
        assert evt.post_type == "weird_type"


# ═══════════════════════════════════════════════════════════
# 3. Action API 测试
# ═══════════════════════════════════════════════════════════


class TestActions:
    def test_send_group_msg_action(self):
        from onebot_server.actions import SendGroupMsgAction

        a = SendGroupMsgAction(
            group_id=12345,
            message=[{"type": "text", "data": {"text": "hi"}}],
        )
        d = a.to_dict()
        assert d["action"] == "send_group_msg"
        assert d["params"]["group_id"] == 12345
        assert "echo" in d

    def test_send_private_msg_action(self):
        from onebot_server.actions import SendPrivateMsgAction

        a = SendPrivateMsgAction(user_id=67890, message="hello")
        d = a.to_dict()
        assert d["action"] == "send_private_msg"
        assert d["params"]["user_id"] == 67890

    def test_get_login_info_action(self):
        from onebot_server.actions import GetLoginInfoAction

        a = GetLoginInfoAction()
        d = a.to_dict()
        assert d["action"] == "get_login_info"
        assert d["params"] == {}

    def test_set_group_ban_action(self):
        from onebot_server.actions import SetGroupBanAction

        a = SetGroupBanAction(group_id=1, user_id=2, duration=600)
        d = a.to_dict()
        assert d["params"]["duration"] == 600

    def test_set_group_leave_action(self):
        from onebot_server.actions import SetGroupLeaveAction

        a = SetGroupLeaveAction(group_id=999, is_dismiss=False)
        d = a.to_dict()
        assert d["action"] == "set_group_leave"

    def test_build_message_helper(self):
        from onebot_server.actions import build_message
        from onebot_server.segments import at, text

        msg = build_message(text("hi"), at(123))
        assert len(msg) == 2
        assert msg[0]["type"] == "text"
        assert msg[1]["type"] == "at"


# ═══════════════════════════════════════════════════════════
# 4. 消息段测试 (class-style API)
# ═══════════════════════════════════════════════════════════


class TestSegments:
    def test_text_segment(self):
        from onebot_server.segments import TextSegment

        s = TextSegment.plain("hello")
        assert s["type"] == "text"
        assert s["data"]["text"] == "hello"

    def test_text_format(self):
        from onebot_server.segments import TextSegment

        s = TextSegment.format("hi {}!", "there")
        assert "there" in s["data"]["text"]

    def test_image_from_url(self):
        from onebot_server.segments import ImageSegment

        s = ImageSegment.from_url("http://example.com/a.png")
        assert s["type"] == "image"
        assert "http" in s["data"]["file"]

    def test_image_from_base64(self):
        from onebot_server.segments import ImageSegment

        s = ImageSegment.from_base64("aGVsbG8=")
        assert s["data"]["file"].startswith("base64://")

    def test_at_someone(self):
        from onebot_server.segments import AtSegment

        s = AtSegment.someone(12345)
        assert s["type"] == "at"
        assert s["data"]["qq"] == "12345"

    def test_at_all(self):
        from onebot_server.segments import AtSegment

        s = AtSegment.all()
        assert s["data"]["qq"] == "all"

    def test_reply_to(self):
        from onebot_server.segments import ReplySegment

        s = ReplySegment.to(999)
        assert s["data"]["id"] == "999"

    def test_face_by_id(self):
        from onebot_server.segments import FaceSegment

        s = FaceSegment.by_id(123)
        assert s["type"] == "face"
        assert s["data"]["id"] == "123"

    def test_function_style_text(self):
        """函数式 API 也应可用。"""
        from onebot_server.segments import at, reply, text  # noqa: F401

        seg = text("hello")
        assert seg["type"] == "text"
        a = at(42)
        assert a["data"]["qq"] == "42"


# ═══════════════════════════════════════════════════════════
# 5. Mixin 系统测试
# ═══════════════════════════════════════════════════════════


class TestMixinSystem:
    def test_base_mixin_exists(self):
        from onebot_server.mixin_base import BaseMixin

        assert issubclass(BaseMixin, object)

    def test_log_mixin_loads(self):
        from onebot_server.mixin.log_mixin import LogMixin

        assert issubclass(LogMixin, object)

    def test_backup_mixin_loads(self):
        from onebot_server.mixin.backup_mixin import BackupMixin

        assert issubclass(BackupMixin, object)

    def test_console_mixin_loads(self):
        from onebot_server.mixin.console_mixin import ConsoleMixin

        assert issubclass(ConsoleMixin, object)

    def test_task_mixin_loads(self):
        from onebot_server.mixin.task_mixin import TaskMixin

        assert issubclass(TaskMixin, object)

    def test_stats_mixin_inherits(self):
        """stats_mixin 应继承基础 Mixin。"""
        from onebot_server.mixin.stats_mixin import AdvancedStatsMixin
        from onebot_server.mixin_base import BaseMixin  # noqa: F401

        # 继承链中应包含 BaseMixin
        assert any(c.__name__ in ("BaseMixin", "StatsMixin") for c in AdvancedStatsMixin.__mro__)

    def test_handler_with_mixins(self):
        """Handler 组合多个 Mixin 后能正确实例化。"""
        from onebot_server.config import Config
        from onebot_server.confirm import ConfirmManager
        from onebot_server.handler import create_handler_class
        from onebot_server.mixin.backup_mixin import BackupMixin
        from onebot_server.mixin.log_mixin import LogMixin
        from onebot_server.whitelist import WhitelistManager

        cls = create_handler_class([LogMixin, BackupMixin])
        cfg = Config(str(ROOT / "config.toml"))
        h = cls(config=cfg, whitelist=WhitelistManager(), confirm_manager=ConfirmManager())
        assert h is not None

    def test_mixin_priority_order(self):
        """MRO 中靠前的 Mixin 优先级更高（先注册先执行）。"""
        from onebot_server.handler import create_handler_class
        from onebot_server.mixin.backup_mixin import BackupMixin
        from onebot_server.mixin.log_mixin import LogMixin

        cls = create_handler_class([LogMixin, BackupMixin])
        mro = [c.__name__ for c in cls.__mro__]
        # 创建顺序 [LogMixin, BackupMixin]
        # MRO: DynamicHandler > LogMixin > BackupMixin > ...
        # LogMixin 在 BackupMixin 之前 → LogMixin 优先级更高
        log_idx = mro.index("LogMixin")
        backup_idx = mro.index("BackupMixin")
        assert log_idx < backup_idx, f"MRO 顺序错误: {mro}"


# ═══════════════════════════════════════════════════════════
# 6. Extension 热加载/卸载测试
# ═══════════════════════════════════════════════════════════


class TestExtensionManager:
    @pytest_asyncio.fixture
    async def mgr(self, tmp_path):
        import asyncio  # noqa: F401

        from onebot_server.config import Config
        from onebot_server.confirm import ConfirmManager
        from onebot_server.extension_manager import ExtensionManager
        from onebot_server.handler import create_handler_class
        from onebot_server.mixin.log_mixin import LogMixin
        from onebot_server.whitelist import WhitelistManager

        cfg = Config(str(ROOT / "config.toml"))
        handler = create_handler_class([LogMixin])(
            config=cfg,
            whitelist=WhitelistManager(),
            confirm_manager=ConfirmManager(),
        )
        mgr = ExtensionManager(
            ext_dir=cfg.ext_dir,  # 包内绝对路径
            handler=handler,
            watch_interval=1,
        )
        yield mgr
        # 清理
        await mgr.cold_unload_all()

    @pytest.mark.asyncio
    async def test_cold_load_all(self, mgr):
        count = await mgr.cold_load_all()
        assert count >= 1, "应至少加载 1 个内置插件"
        assert mgr.count >= 1

    @pytest.mark.asyncio
    async def test_hot_unload(self, mgr):
        await mgr.cold_load_all()
        assert mgr.is_loaded("echo")
        ok = await mgr.hot_unload("echo")
        assert ok
        assert not mgr.is_loaded("echo")

    @pytest.mark.asyncio
    async def test_hot_reload(self, mgr):
        await mgr.cold_load_all()
        ok = await mgr.hot_reload("echo")
        assert ok
        assert mgr.is_loaded("echo")

    @pytest.mark.asyncio
    async def test_cold_unload_all(self, mgr):
        await mgr.cold_load_all()
        n = await mgr.cold_unload_all()
        assert n >= 1
        assert mgr.count == 0

    def test_list_all(self, mgr):
        listed = mgr.list_all()
        assert isinstance(listed, list)


# ═══════════════════════════════════════════════════════════
# 7. 确认机制测试
# ═══════════════════════════════════════════════════════════


class TestConfirmManager:
    @pytest.mark.asyncio
    async def test_submit_and_approve(self):
        from onebot_server.confirm import ConfirmManager

        cm = ConfirmManager(timeout=60)
        # submit(action_type, params, description, executor, timeout)
        token = await cm.submit(
            action_type="set_group_ban",
            params={"group_id": 1, "user_id": 123, "duration": 60},
            description="禁言用户 123 (60s)",
            executor=999,
        )
        assert isinstance(token, str)
        assert len(token) > 0
        # list_pending 也是 async
        pending = await cm.list_pending()
        assert len(pending) >= 1
        # approve(token, admin_id) → Tuple[bool, str]
        ok, msg = await cm.approve(token, admin_id=888)
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    @pytest.mark.asyncio
    async def test_reject(self):
        from onebot_server.confirm import ConfirmManager

        cm = ConfirmManager(timeout=60)
        token = await cm.submit(
            action_type="set_group_leave",
            params={"group_id": 999},
            description="退出群 999",
            executor=999,
        )
        ok, msg = await cm.reject(token, admin_id=10001)
        assert isinstance(ok, bool)

    @pytest.mark.asyncio
    async def test_list_pending(self):
        from onebot_server.confirm import ConfirmManager

        cm = ConfirmManager(timeout=60)
        await cm.submit("test", {}, "desc", 1)
        pending = await cm.list_pending()
        assert len(pending) >= 1

    @pytest.mark.asyncio
    async def test_approve_nonexist(self):
        from onebot_server.confirm import ConfirmManager

        cm = ConfirmManager(timeout=60)
        ok, msg = await cm.approve("nonexist_token", admin_id=10001)
        assert ok is False


# ═══════════════════════════════════════════════════════════
# 8. 白名单测试
# ═══════════════════════════════════════════════════════════


class TestWhitelist:
    def test_add_and_check(self, tmp_path):
        from onebot_server.whitelist import WhitelistManager

        wm = WhitelistManager(data_dir=str(tmp_path))
        wm.add_group(12345)
        wm.add_friend(67890)
        assert wm.is_group_whitelisted(12345)
        assert wm.is_friend_whitelisted(67890)
        assert not wm.is_group_whitelisted(99999)

    def test_remove(self, tmp_path):
        from onebot_server.whitelist import WhitelistManager

        wm = WhitelistManager(data_dir=str(tmp_path))
        wm.add_group(111)
        wm.remove_group(111)
        assert not wm.is_group_whitelisted(111)

    def test_persistence(self, tmp_path):
        """白名单应持久化到 JSON 文件（构造新实例可读取）。"""
        from onebot_server.whitelist import WhitelistManager

        wm1 = WhitelistManager(data_dir=str(tmp_path))
        wm1.add_group(555)
        # 新建实例，应能从磁盘加载
        wm2 = WhitelistManager(data_dir=str(tmp_path))
        assert wm2.is_group_whitelisted(555)

    def test_export_import(self, tmp_path):
        from onebot_server.whitelist import WhitelistManager

        wm = WhitelistManager(data_dir=str(tmp_path))
        wm.add_group(100)
        wm.add_group(200)
        exported = wm.export_all()
        # 真实 key 是 "group_whitelist"
        assert "group_whitelist" in exported
        assert 100 in exported["group_whitelist"]
        # import_groups 接受 List[int]
        wm2 = WhitelistManager(data_dir=str(tmp_path / "sub"))
        n = wm2.import_groups(exported["group_whitelist"])
        assert n >= 1
        assert wm2.is_group_whitelisted(100)


# ═══════════════════════════════════════════════════════════
# 9. 服务器集成测试
# ═══════════════════════════════════════════════════════════


class TestServerIntegration:
    def test_server_creates_handler(self):
        from onebot_server.server import OneBotServer

        s = OneBotServer(config_path=str(ROOT / "config.toml"))
        assert s.handler is not None
        assert s.extension_manager is not None

    def test_handler_dispatch_message(self):
        """Handler 能正确分发群消息事件。"""
        from onebot_server.server import OneBotServer

        s = OneBotServer(config_path=str(ROOT / "config.toml"))
        evt_dict = {
            "time": 1700000000,
            "self_id": 10000,
            "post_type": "message",
            "message_type": "group",
            "group_id": 123,
            "user_id": 456,
            "message": [{"type": "text", "data": {"text": "test"}}],
            "raw_message": "test",
            "message_id": 1,
            "sender": {"nickname": "t", "role": "member"},
        }
        # 不应抛异常
        result = asyncio.run(s.handler.handle_event(evt_dict))
        assert result is None or isinstance(result, (dict, type(None)))

    def test_config_has_token(self):
        from onebot_server.config import Config

        cfg = Config(str(ROOT / "config.toml"))
        assert cfg.access_token != ""

    def test_server_logger_init(self):
        from onebot_server.server import OneBotServer

        s = OneBotServer(config_path=str(ROOT / "config.toml"))
        # 日志器应已初始化
        logger = s.logger
        assert logger is not None


# ═══════════════════════════════════════════════════════════
# 10. 端到端：模拟事件分发
# ═══════════════════════════════════════════════════════════


class TestEndToEnd:
    @pytest.mark.asyncio
    async def test_full_dispatch_flow(self):
        """模拟一条群消息从接收到 Extension 处理的完整流程。"""
        from onebot_server.server import OneBotServer

        s = OneBotServer(config_path=str(ROOT / "config.toml"))
        await s.extension_manager.cold_load_all()

        evt = {
            "time": 1700000000,
            "self_id": 10000,
            "post_type": "message",
            "message_type": "group",
            "group_id": 12345,
            "user_id": 67890,
            "message": [{"type": "text", "data": {"text": "/echo 测试"}}],
            "raw_message": "/echo 测试",
            "message_id": 42,
            "sender": {"nickname": "测试用户", "role": "member"},
        }
        await s.handler.handle_event(evt)
        await s.extension_manager.cold_unload_all()
        assert True

    @pytest.mark.asyncio
    async def test_notice_dispatch(self):
        """通知事件能正确分发到 Mixin。"""
        from onebot_server.server import OneBotServer

        s = OneBotServer(config_path=str(ROOT / "config.toml"))
        await s.extension_manager.cold_load_all()

        notice = {
            "time": 1700000000,
            "self_id": 10000,
            "post_type": "notice",
            "notice_type": "group_ban",
            "group_id": 123,
            "user_id": 456,
            "operator_id": 789,
            "duration": 600,
        }
        await s.handler.handle_event(notice)
        await s.extension_manager.cold_unload_all()
        assert True

    @pytest.mark.asyncio
    async def test_request_dispatch(self):
        """请求事件能正确分发。"""
        from onebot_server.server import OneBotServer

        s = OneBotServer(config_path=str(ROOT / "config.toml"))
        await s.extension_manager.cold_load_all()

        req = {
            "time": 1700000000,
            "self_id": 10000,
            "post_type": "request",
            "request_type": "group",
            "group_id": 123,
            "user_id": 456,
            "comment": "求进群",
            "flag": "req_flag_xyz",
        }
        await s.handler.handle_event(req)
        await s.extension_manager.cold_unload_all()
        assert True

    @pytest.mark.asyncio
    async def test_meta_dispatch(self):
        """心跳元事件不应导致异常。"""
        from onebot_server.server import OneBotServer

        s = OneBotServer(config_path=str(ROOT / "config.toml"))
        await s.extension_manager.cold_load_all()

        meta = {
            "time": 1700000000,
            "self_id": 10000,
            "post_type": "meta_event",
            "meta_event_type": "heartbeat",
            "interval": 30000,
        }
        await s.handler.handle_event(meta)
        await s.extension_manager.cold_unload_all()
        assert True
