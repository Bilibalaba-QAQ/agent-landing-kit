#!/usr/bin/env python3
"""本机配置层 loader(能力分层规范 §四)。
读取优先级:进程环境变量 > ~/.config/opc/<capability>.env > 代码默认值。
打包时随包复制进用到它的 skill 的 scripts/lib/。
"""
import os
from pathlib import Path


def get(capability: str, key: str, default=None):
    if key in os.environ:
        return os.environ[key]
    envf = Path.home() / ".config" / "opc" / f"{capability}.env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip()
    return default


def state_dir(capability: str) -> Path:
    """运行态目录 ~/.local/state/opc/<capability>/(不存在则建,700)。"""
    d = Path(os.environ.get("OPC_STATE_DIR") or (Path.home() / ".local" / "state" / "opc" / capability))
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    return d
