"""python -m dsc2cherry：带参数走命令行，不带参数打开图形界面。"""

import sys


def main() -> int:
    if len(sys.argv) > 1:
        from .cli import main as cli_main

        return cli_main()
    from .gui import main as gui_main

    gui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
