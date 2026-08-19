"""
OneBot 11 Message Segments
==========================

Helper functions to build message segment dictionaries that conform to the
OneBot 11 specification. Use :func:`build_message` to compose them.
"""

from __future__ import annotations

from typing import Any, List, Optional, Union

MessageSegment = dict  # type alias for clarity
Message = List[MessageSegment]


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def text(content: str) -> MessageSegment:
    """Plain text segment."""
    return {"type": "text", "data": {"text": content}}


def emoji(id: str) -> MessageSegment:
    """Emoji / face with numeric QQ face id."""
    return {"type": "face", "data": {"id": str(id)}}


def image(file: str, url: Optional[str] = None, cache: bool = True) -> MessageSegment:
    """
    Image segment.

    :param file: ``http(s)://...`` URL, ``file:///path``, ``base64://...``
    :param url: optional source URL (for QQ to fetch)
    :param cache: whether LLOneBot should cache the file
    """
    data: dict = {"file": file}
    if url:
        data["url"] = url
    data["cache"] = 1 if cache else 0
    return {"type": "image", "data": data}


def record(file: str, url: Optional[str] = None, cache: bool = True) -> MessageSegment:
    """Voice / audio segment."""
    data: dict = {"file": file}
    if url:
        data["url"] = url
    data["cache"] = 1 if cache else 0
    return {"type": "record", "data": data}


def video(file: str, url: Optional[str] = None, cache: bool = True) -> MessageSegment:
    """Video segment."""
    data: dict = {"file": file}
    if url:
        data["url"] = url
    data["cache"] = 1 if cache else 0
    return {"type": "video", "data": data}


def at(user_id: Union[int, str], name: Optional[str] = None) -> MessageSegment:
    """
    ``@`` mention segment.

    :param user_id: QQ number, or ``"all"`` for @全体成员
    """
    data: dict = {"qq": str(user_id)}
    if name:
        data["name"] = name
    return {"type": "at", "data": data}


def reply(message_id: int) -> MessageSegment:
    """Reply-to-message segment (引用回复)."""
    return {"type": "reply", "data": {"id": str(message_id)}}


def poke(user_id: int) -> MessageSegment:
    """Poke / 戳一戳."""
    return {"type": "poke", "data": {"qq": str(user_id)}}


def gift(user_id: int, gift_id: int) -> MessageSegment:
    """Send a QQ gift."""
    return {"type": "gift", "data": {"qq": str(user_id), "id": str(gift_id)}}


def share(url: str, title: str, content: str = "", image: str = "") -> MessageSegment:
    """Share-link card."""
    return {
        "type": "share",
        "data": {"url": url, "title": title, "content": content, "image": image},
    }


def location(lat: float, lon: float, title: str = "", content: str = "") -> MessageSegment:
    """Location / map card."""
    return {
        "type": "location",
        "data": {
            "lat": str(lat),
            "lon": str(lon),
            "title": title,
            "content": content,
        },
    }


def forward(id: str) -> MessageSegment:
    """Forwarded message history (合并转发)."""
    return {"type": "forward", "data": {"id": id}}


def node(user_id: int, nickname: str, content: Union[str, Message]) -> MessageSegment:
    """
    A single node for a forwarded message bundle.

    :param content: plain string or list of message segments
    """
    return {
        "type": "node",
        "data": {
            "user_id": str(user_id),
            "nickname": nickname,
            "content": content,
        },
    }


def xml_message(data: str) -> MessageSegment:
    """Raw XML message (rich cards, etc.)."""
    return {"type": "xml", "data": {"data": data}}


def json_message(data: str) -> MessageSegment:
    """Raw JSON message (rich cards, etc.)."""
    return {"type": "json", "data": {"data": data}}


# ---------------------------------------------------------------------------
# Composer
# ---------------------------------------------------------------------------


def build_message(*segments: Any) -> Message:
    """
    Build a message list from segment helpers (or plain strings).

    Strings are auto-converted to ``text`` segments.
    """
    result: Message = []
    for seg in segments:
        if isinstance(seg, str):
            result.append(text(seg))
        elif isinstance(seg, dict):
            result.append(seg)
        else:
            # Assume it's iterable (e.g. another build_message result)
            try:
                for s in seg:
                    if isinstance(s, str):
                        result.append(text(s))
                    elif isinstance(s, dict):
                        result.append(s)
            except TypeError:
                raise TypeError(f"Unsupported message segment: {seg!r}")
    return result


# ---------------------------------------------------------------------------
# Class-style aliases (for IDE auto-complete lovers)
# ---------------------------------------------------------------------------


class TextSegment:
    """Class-style access: ``TextSegment.hello("world")`` → text segment."""

    @staticmethod
    def plain(s: str) -> MessageSegment:
        return text(s)

    @staticmethod
    def format(template: str, *args, **kwargs) -> MessageSegment:
        return text(template.format(*args, **kwargs))


class ImageSegment:
    @staticmethod
    def from_url(url: str, cache: bool = True) -> MessageSegment:
        return image(url, url=url, cache=cache)

    @staticmethod
    def from_base64(b64: str) -> MessageSegment:
        if b64.startswith("base64://"):
            return image(b64)
        return image(f"base64://{b64}")

    @staticmethod
    def from_file(path: str) -> MessageSegment:
        return image(f"file://{path}")


class AtSegment:
    @staticmethod
    def someone(user_id: Union[int, str]) -> MessageSegment:
        return at(user_id)

    @staticmethod
    def all() -> MessageSegment:
        return at("all")

    @staticmethod
    def me(self_id: int) -> MessageSegment:
        return at(self_id)


class FaceSegment:
    @staticmethod
    def by_id(face_id: int) -> MessageSegment:
        return emoji(face_id)

    # Convenient presets
    smile = emoji(14)
    laugh = emoji(27)
    thumbs_up = emoji(76)
    slap = emoji(78)
    shrug = emoji(102)
    yeah = emoji(177)


class ReplySegment:
    @staticmethod
    def to(message_id: int) -> MessageSegment:
        return reply(message_id)


class RecordSegment:
    @staticmethod
    def from_url(url: str) -> MessageSegment:
        return record(url, url=url)

    @staticmethod
    def from_file(path: str) -> MessageSegment:
        return record(f"file://{path}")
