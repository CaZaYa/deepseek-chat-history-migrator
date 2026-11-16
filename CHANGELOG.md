# Changelog

## 1.0.0

- 支持 DeepSeek 导出包（`export_format_version: 3`）转换为 ChatGPT `conversations.json`
- 三种转换模式：仅文本 / 文本 + 思考过程 / 完整（含图片附件）
- 保留消息树、分支和当前活跃节点
- 图片原件按会话导出，消息内标注相对路径
- 输出 `附件索引.csv`
- 分批输出（默认每 200 个会话一个文件）
- 图形界面与命令行，可打包为独立 exe
