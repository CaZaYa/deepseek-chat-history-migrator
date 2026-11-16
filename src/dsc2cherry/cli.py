"""命令行入口：python -m dsc2cherry <导出包.zip> <输出目录>"""

from __future__ import annotations

import argparse
import sys

from .core import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_CHUNK_SIZE,
    PRESETS,
    ConversionError,
    Converter,
    Options,
    run_directory,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="把 DeepSeek C 端导出包转换成 Cherry Studio 可导入的 ChatGPT 格式。",
    )
    parser.add_argument("zip_path", help="DeepSeek 导出的 deepseek_data-*.zip")
    parser.add_argument("out_dir", help="输出目录（建议使用空目录）")
    parser.add_argument(
        "--mode",
        choices=[preset[0] for preset in PRESETS],
        default="thinking",
        help="转换模式：text=仅文本，thinking=文本+思考（默认），full=完整（含图片附件）",
    )
    parser.add_argument("--with-thinking", action="store_true", help="包含思考过程（覆盖 --mode）")
    parser.add_argument("--no-attachments", action="store_true", help="不导出图片和附件（覆盖 --mode）")
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help=f"每个 JSON 文件包含的会话数，0 表示不拆分（默认 {DEFAULT_CHUNK_SIZE}）",
    )
    parser.add_argument("--name", default=None, help="本次输出子文件夹名（默认按时间戳）")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv:
        print(f"{APP_NAME} {APP_VERSION} —— 命令行版本")
        print("这是命令行工具，需要提供导出包和输出目录。")
        print(r'示例：DeepSeek2Cherry-CLI.exe "D:\deepseek_data.zip" "D:\输出目录" --mode full')
        print("图形界面请双击 DeepSeek2Cherry.exe。")
        try:
            input("\n按回车键退出…")
        except EOFError:
            pass
        return 2

    if len(argv) == 1 and argv[0].lower().endswith(".zip"):
        return interactive(argv[0])

    args = build_parser().parse_args(argv)

    options = Options.from_preset(args.mode, chunk_size=args.chunk_size)
    if args.with_thinking:
        options.with_thinking = True
    if args.no_attachments:
        options.export_attachments = False

    try:
        target = run_directory(args.out_dir, args.name)
        report = Converter(args.zip_path, options, log=print).run(target)
    except ConversionError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1

    for warning in report.warnings:
        print(f"提示：{warning}")

    print(
        f"\n完成：{report.conversations} 个会话 / {report.messages} 条消息 / "
        f"{report.files} 个附件（缺失 {report.missing_files}，多为 PDF 等非图片附件）"
    )
    print(f"输出目录：{report.output_dir}")
    print("下一步：Cherry Studio → 设置 → 数据 → 导入外部应用数据 → 导入 ChatGPT 数据")
    return 0


def interactive(zip_arg: str) -> int:
    """把 zip 拖到 exe 上时：问一下模式，其余用默认值。"""
    from pathlib import Path

    zip_path = Path(zip_arg)
    print(f"导出包：{zip_path}")
    print("选择转换模式：")
    print("  1  完整（文本 + 思考 + 图片附件，默认）")
    print("  2  文本 + 思考过程")
    print("  3  仅文本")
    try:
        choice = input("输入 1-3 后回车：").strip() or "1"
    except EOFError:
        choice = "1"
    preset = {"1": "full", "2": "thinking", "3": "text"}.get(choice, "full")

    out_dir = zip_path.with_name(zip_path.stem + "_cherry")
    try:
        target = run_directory(out_dir)
        report = Converter(str(zip_path), Options.from_preset(preset), log=print).run(target)
    except ConversionError as error:
        print(f"错误：{error}", file=sys.stderr)
        try:
            input("按回车键退出…")
        except EOFError:
            pass
        return 1

    print(f"\n输出目录：{report.output_dir}")
    try:
        input("按回车键退出…")
    except EOFError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
