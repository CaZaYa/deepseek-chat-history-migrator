import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dsc2cherry.core import Converter, Options  # noqa: E402


def build_export(path: Path) -> None:
    session = {
        "id": "s1",
        "title": "测试会话",
        "current_message_id": 4,
        "inserted_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "messages": [
            {
                "id": 1,
                "parent_id": None,
                "role": "USER",
                "inserted_at": "2026-01-01T00:00:01Z",
                "fragments": [
                    {"type": "REQUEST", "content": "看图回答"},
                    {
                        "type": "FILE",
                        "files": [
                            {
                                "file_name": "a.png",
                                "is_image": True,
                                "export_path": "chat_sessions/s1_files/f1_a.png",
                            }
                        ],
                    },
                ],
            },
            {
                "id": 2,
                "parent_id": 1,
                "role": "ASSISTANT",
                "inserted_at": "2026-01-01T00:00:02Z",
                "fragments": [
                    {"type": "THINK", "content": "先想一下", "elapsed_secs": 1},
                    {"type": "RESPONSE", "content": "答案一"},
                ],
            },
            {
                "id": 3,
                "parent_id": 1,
                "role": "ASSISTANT",
                "inserted_at": "2026-01-01T00:00:03Z",
                "fragments": [{"type": "RESPONSE", "content": "答案二"}],
            },
            {
                "id": 4,
                "parent_id": 3,
                "role": "USER",
                "inserted_at": "2026-01-01T00:00:04Z",
                "fragments": [{"type": "REQUEST", "content": "继续"}],
            },
        ],
    }
    index = [
        {"id": "s1", "title": "测试会话", "message_count": 4,
         "inserted_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-02T00:00:00Z"},
        {"id": "s2", "title": "空会话", "message_count": 0,
         "inserted_at": "2026-01-03T00:00:00Z", "updated_at": "2026-01-03T00:00:00Z"},
    ]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"export_format_version": 3}))
        archive.writestr("chat_session_index.json", json.dumps(index))
        archive.writestr("chat_sessions/s1.json", json.dumps(session))
        archive.writestr("chat_sessions/s1_files/f1_a.png", b"\x89PNG\r\n")


class ConverterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.zip = self.root / "export.zip"
        build_export(self.zip)

    def tearDown(self):
        self.tmp.cleanup()

    def convert(self, **kwargs):
        out = self.root / "out"
        kwargs.setdefault("chunk_size", 0)  # 不拆分，方便断言
        report = Converter(self.zip, Options(**kwargs)).run(out)
        data = json.loads((out / "conversations.json").read_text(encoding="utf-8"))
        return report, data[0], out

    def test_text_only_drops_thinking_and_attachments(self):
        report, conv, _ = self.convert(with_thinking=False, export_attachments=False)
        texts = [n["message"]["content"]["parts"][0] for n in conv["mapping"].values()
                 if n["message"]["content"]["parts"]]
        self.assertNotIn("思考过程", "\n".join(texts))
        self.assertNotIn("[图片", "\n".join(texts))
        self.assertEqual(report.conversations, 1)  # 空会话被跳过
        self.assertEqual(report.files, 0)

    def test_thinking_mode(self):
        _, conv, _ = self.convert(with_thinking=True, export_attachments=False)
        joined = "\n".join(n["message"]["content"]["parts"][0] for n in conv["mapping"].values()
                           if n["message"]["content"]["parts"])
        self.assertIn("思考过程", joined)
        self.assertIn("先想一下", joined)

    def test_full_mode_extracts_image(self):
        report, conv, out = self.convert(with_thinking=True, export_attachments=True)
        self.assertEqual(report.files, 1)
        marker = [p for n in conv["mapping"].values() for p in n["message"]["content"]["parts"]
                  if "[图片：" in p][0]
        rel = marker.split("]", 1)[0].split("：", 1)[1]
        self.assertTrue((out / rel).is_file())
        self.assertTrue((out / "附件索引.csv").is_file())

    def test_tree_is_preserved(self):
        _, conv, _ = self.convert(with_thinking=True, export_attachments=True)
        mapping = conv["mapping"]
        self.assertEqual(mapping["1"]["children"], ["2", "3"])
        self.assertIn(conv["current_node"], mapping)
        self.assertEqual(conv["title"], "测试会话")

    def test_invalid_zip_reports_error(self):
        bad = self.root / "bad.zip"
        bad.write_bytes(b"not a zip")
        with self.assertRaises(Exception):
            Converter(bad, Options()).run(self.root / "bad")


if __name__ == "__main__":
    unittest.main()
