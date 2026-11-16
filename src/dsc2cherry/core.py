"""DeepSeek2Cherry 核心转换逻辑：DeepSeek 导出包 → Cherry Studio 可导入的 ChatGPT 格式。"""

from __future__ import annotations

import csv
import datetime
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "DeepSeek2Cherry"
APP_VERSION = "1.0.0"
PROJECT_URL = "https://github.com/CaZaYa/deepseek-chat-history-migrator"

SUPPORTED_EXPORT_VERSION = 3
TEXT_FRAGMENTS = {"REQUEST", "RESPONSE", "TEMPLATE_RESPONSE"}
DEFAULT_CHUNK_SIZE = 200

# (id, 界面名称, 含思考过程, 导出图片附件)
PRESETS = (
    ("text", "仅文本（不含思考过程）", False, False),
    ("thinking", "文本 + 思考过程", True, False),
    ("full", "完整（文本 + 思考过程 + 图片附件）", True, True),
)


class ConversionError(Exception):
    """导出包不合法或无法读取。"""


@dataclass
class Options:
    with_thinking: bool = False
    export_attachments: bool = True
    chunk_size: int = DEFAULT_CHUNK_SIZE

    @classmethod
    def from_preset(cls, preset_id: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> "Options":
        for pid, _label, thinking, attachments in PRESETS:
            if pid == preset_id:
                return cls(with_thinking=thinking, export_attachments=attachments, chunk_size=chunk_size)
        raise ValueError(f"未知的预设：{preset_id}")


@dataclass
class Report:
    conversations: int = 0
    messages: int = 0
    files: int = 0
    missing_files: int = 0
    bytes_written: int = 0
    chunks: int = 0
    output_dir: Path | None = None
    warnings: list[str] = field(default_factory=list)


def parse_ts(value) -> int:
    """ISO 时间 → unix 时间戳，解析失败返回 0。"""
    if not value:
        return 0
    try:
        return int(datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except (ValueError, AttributeError):
        return 0


def safe_name(text: str | None, limit: int = 48) -> str:
    """把会话标题整理成合法的文件夹名。"""
    text = (text or "未命名").strip()
    text = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", text).strip(" .")
    return (text[:limit] or "未命名").rstrip(" .")


def run_directory(base: str | Path, name: str | None = None) -> Path:
    """每次转换单独一个子目录：用户指定名字，或按时间自动命名，避免覆盖上次结果。"""
    base = Path(base)
    folder = (name or "").strip() or datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = base / safe_name(folder, 60)
    counter = 2
    while target.exists():
        target = base / f"{safe_name(folder, 60)}-{counter}"
        counter += 1
    target.mkdir(parents=True, exist_ok=True)
    return target


class Converter:
    """执行一次完整转换。所有输出都落在 out_dir 下。"""

    def __init__(self, zip_path: str | Path, options: Options | None = None,
                 log=None, progress=None):
        self.zip_path = Path(zip_path)
        self.options = options or Options()
        self.log = log or (lambda message: None)
        self.progress = progress or (lambda done, total: None)
        self.report = Report()

        if not self.zip_path.is_file():
            raise ConversionError(f"找不到导出包：{self.zip_path}")

        try:
            self.archive = zipfile.ZipFile(self.zip_path)
        except zipfile.BadZipFile as error:
            raise ConversionError("文件不是有效的 ZIP 压缩包。") from error

        self.entry_names = set(self.archive.namelist())
        self.titles = self._read_titles()

        self._file_cache: dict[str, str] = {}
        self._index_rows: list[list] = []

    # ---------- 元数据 ----------
    def _read_titles(self) -> dict[str, str]:
        try:
            entries = json.loads(self.archive.read("chat_session_index.json"))
        except KeyError as error:
            raise ConversionError("这不是 DeepSeek 导出的数据包（缺少 chat_session_index.json）。") from error

        version = self._export_version()
        if version and version != SUPPORTED_EXPORT_VERSION:
            self.report.warnings.append(
                f"导出包格式版本为 {version}，本工具按版本 {SUPPORTED_EXPORT_VERSION} 解析，"
                "如有字段缺失请更新工具。"
            )
        return {entry.get("id"): entry.get("title") for entry in entries if entry.get("id")}

    def _export_version(self) -> int | None:
        try:
            manifest = json.loads(self.archive.read("manifest.json"))
        except (KeyError, json.JSONDecodeError):
            return None
        return manifest.get("export_format_version")

    def _session_order(self) -> list[dict]:
        """按最近更新时间排序，最新的会话排在第一批。"""
        entries = json.loads(self.archive.read("chat_session_index.json"))
        entries = [e for e in entries if e.get("id") in self.entry_names_of_sessions()]
        entries.sort(key=lambda entry: entry.get("updated_at") or "", reverse=True)
        return entries

    def entry_names_of_sessions(self) -> set[str]:
        return {
            name[len("chat_sessions/"):-len(".json")]
            for name in self.entry_names
            if name.startswith("chat_sessions/") and name.endswith(".json")
        }

    # ---------- 附件 ----------
    def _extract_file(self, session_no: int, session_title: str, file_info: dict) -> tuple[str, bool]:
        """提取附件，返回 (相对路径, 是否成功)。DeepSeek 导出包只带图片原件。"""
        if not self.options.export_attachments:
            return "", False

        source = file_info.get("export_path")
        if not source or source not in self.entry_names:
            return "", False
        if source in self._file_cache:
            return self._file_cache[source], True

        rel_dir = f"{session_no:04d}-{safe_name(session_title)}"
        dest_dir = self.report.output_dir / "attachments" / rel_dir
        base = re.sub(r'[\\/:*?"<>|]+', "_", file_info.get("file_name") or "附件").strip() or "附件"

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / base
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{Path(base).stem}_{counter}{Path(base).suffix}"
            counter += 1

        data = self.archive.read(source)
        dest.write_bytes(data)
        self.report.files += 1
        self.report.bytes_written += len(data)

        rel = f"attachments/{rel_dir}/{dest.name}"
        self._file_cache[source] = rel
        return rel, True

    # ---------- 单个会话 ----------
    def _convert_session(self, session: dict, session_no: int) -> tuple[dict, int]:
        title = session.get("title") or self.titles.get(session.get("id")) or "未命名对话"
        mapping: dict[str, dict] = {}
        order: list[str] = []
        non_empty = 0

        for message in session.get("messages") or []:
            mid = str(message.get("id"))
            role = "user" if message.get("role") == "USER" else "assistant"
            parts: list[str] = []

            for fragment in message.get("fragments") or []:
                kind = fragment.get("type")
                content = fragment.get("content")

                if kind in TEXT_FRAGMENTS and content:
                    parts.append(content.strip())
                elif kind == "THINK" and self.options.with_thinking and content:
                    quoted = "> " + content.replace("\n", "\n> ")
                    parts.append("**思考过程**\n\n" + quoted)
                elif kind == "FILE" and self.options.export_attachments:
                    for info in fragment.get("files") or []:
                        label = "图片" if info.get("is_image") else "附件"
                        name = info.get("file_name") or "附件"
                        rel, ok = self._extract_file(session_no, title, info)
                        if ok:
                            parts.append(f"[{label}：{rel}]")
                        else:
                            self.report.missing_files += 1
                            parts.append(f"[{label}：{name}（导出包未包含原件）]")
                        self._index_rows.append(
                            [session.get("id"), title, message.get("id"), label, rel, name,
                             "已导出" if ok else "缺失"]
                        )

            text = "\n\n".join(part for part in parts if part)
            if text:
                non_empty += 1

            parent = message.get("parent_id")
            mapping[mid] = {
                "id": mid,
                "message": {
                    "id": mid,
                    "author": {"role": role},
                    "create_time": parse_ts(message.get("inserted_at")),
                    "content": {"content_type": "text", "parts": [text] if text else []},
                    "status": "finished_successfully",
                    "recipient": "all",
                },
                "parent": str(parent) if parent is not None else None,
                "children": [],
            }
            order.append(mid)

        # 空消息保留节点：导入器会跳过空内容，但需要它来维持父子链
        for mid in order:
            parent = mapping[mid]["parent"]
            if parent and parent in mapping:
                mapping[parent]["children"].append(mid)

        current = str(session.get("current_message_id"))
        if current not in mapping:
            current = order[-1] if order else None

        conversation = {
            "title": title,
            "create_time": parse_ts(session.get("inserted_at")),
            "update_time": parse_ts(session.get("updated_at")),
            "mapping": mapping,
            "current_node": current,
            "conversation_id": session.get("id") or "unknown",
            "id": session.get("id") or "unknown",
            "is_archived": False,
        }
        return conversation, non_empty

    # ---------- 主流程 ----------
    def run(self, out_dir: str | Path) -> Report:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        self.report.output_dir = out_dir

        sessions = self._session_order()
        total = len(sessions)
        self.log(f"发现 {total} 个会话")

        chunk: list[dict] = []
        chunk_no = 1

        def flush() -> None:
            nonlocal chunk, chunk_no
            if not chunk:
                return
            name = f"conversations-{chunk_no}.json" if self.options.chunk_size > 0 else "conversations.json"
            path = out_dir / name
            path.write_text(json.dumps(chunk, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            self.report.chunks += 1
            self.report.bytes_written += path.stat().st_size
            self.log(f"写出 {name} — {len(chunk)} 个会话（{path.stat().st_size / 1048576:.1f} MB）")
            chunk, chunk_no = [], chunk_no + 1

        for session_no, entry in enumerate(sessions, start=1):
            session = json.loads(self.archive.read(f"chat_sessions/{entry['id']}.json"))
            conversation, non_empty = self._convert_session(session, session_no)
            if non_empty:
                self.report.conversations += 1
                self.report.messages += non_empty
                chunk.append(conversation)

            self.progress(session_no, total)
            if self.options.chunk_size > 0 and len(chunk) >= self.options.chunk_size:
                flush()

        flush()

        if self._index_rows:
            path = out_dir / "附件索引.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["会话ID", "会话标题", "消息ID", "类型", "相对路径", "原始文件名", "状态"])
                writer.writerows(self._index_rows)
            self.log(f"写出 附件索引.csv — {len(self._index_rows)} 条记录")

        self.log(
            f"完成：{self.report.conversations} 个会话 / {self.report.messages} 条消息 / "
            f"{self.report.files} 个附件"
        )
        return self.report
