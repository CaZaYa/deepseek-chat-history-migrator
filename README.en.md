# DeepSeek2Cherry

Convert **DeepSeek chat exports** into a format **Cherry Studio** can import.

📖 **User manual**: [English PDF](User%20Manual%20%28EN%29.pdf) · [English Word](docs/User%20Manual%20%28EN%29.docx) · [中文 PDF](使用手册.pdf)

> **Quickest start**: double-click `DeepSeek2Cherry.exe` in the repository root.

Cherry Studio only imports official ChatGPT and Claude exports. DeepSeek's export (`export_format_version: 3`) uses a different structure, so this tool bridges the gap: it keeps the message tree and branches, optionally includes reasoning, and extracts image attachments with inline markers.

> Runs fully offline. Standard library only.

## Features

- Three conversion modes: text only / text + reasoning / full (text + reasoning + attachments)
- Preserves regenerated answers as sibling branches
- Extracts image files per conversation and marks them as `[图片：attachments/…]` in the original message
- Writes `附件索引.csv` (session, message, file, status)
- Splits output into 200-conversation JSON files so Cherry Studio does not choke on a single huge file
- GUI and CLI, shipped as standalone Windows executables

## Usage

1. DeepSeek web → avatar → **Settings** → **Data** → **Export all chats**, download `deepseek_data-*.zip`.
2. Run `DeepSeek2Cherry.exe`, pick the zip and an **empty** output folder, choose a mode, start.
3. Cherry Studio → **Settings** → **Data** → **Import external app data** → **Import ChatGPT data**, select each `conversations-*.json`.

> Import each file only once. Windows SmartScreen may warn on first launch (unsigned binary) — choose "More info → Run anyway".

CLI:

```bash
DeepSeek2Cherry-CLI.exe <export.zip> <out_dir> --mode full
```

## Modes

| Mode | Text | Reasoning | Attachments |
| --- | --- | --- | --- |
| `text` | ✅ | ❌ | ❌ |
| `thinking` | ✅ | ✅ | ❌ |
| `full` | ✅ | ✅ | ✅ |

## Limitations

- DeepSeek exports contain **image files only**; PDF/Word attachments keep just their filenames and are marked as missing
- A few images may already be gone server-side and are reported as missing
- Imported assistant messages display a GPT-5 badge in Cherry Studio — hardcoded in Cherry's ChatGPT importer
- Web-search intermediate results are not imported; only the answer text is

## Development

```bash
python -m dsc2cherry
python -m unittest discover -s tests
build.bat
```

## Feedback

This is a small hobby project maintained in spare time. Bug reports, feature requests and documentation fixes are welcome via Issues — please include your OS version, steps to reproduce and any error message. Replies may be slow.

## License

MIT
