# -*- coding: utf-8 -*-
"""桌宠配置快照 / 恢复。

为什么需要它：桌宠设置页里的「重置配置」会把 AI 配置（API 地址 / 模型 / 凭据
引用）连同其它设置一起清空；而 API Key 存在 Windows 凭据管理器里，
config.json 里只有 `api_key_ref`（凭据条目的名字），**备份文件里不含 Key 本身**，
恢复后如果 Key 丢了需要重新填一次。

用法：
    python pet_config_backup.py              # 立即做一份快照
    python pet_config_backup.py --list       # 列出已有快照
    python pet_config_backup.py --restore 1  # 恢复第 1 号快照（0 = 最新）
    python pet_config_backup.py --interactive # 交互式选择恢复
    python pet_config_backup.py --quiet      # 供开机自启调用：静默、只写日志
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("APPDATA", "")) / "dsh-pet-standalone-webm-chat"
BACKUP_ROOT = Path(__file__).resolve().parent.parent / "backups"
LOG_FILE = BACKUP_ROOT / "backup.log"
KEEP = 20

# 这些是"设置"本体；characters/ 和 sessions/ 属于个人数据，体积也可能很大，不纳入。
TARGETS = [
    "config.json",
    "config-slot-0.json",
    "config-slot-1.json",
    ".config-reset-generations.json",
]


def log(msg: str, quiet: bool = False) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    if not quiet:
        print(line, flush=True)
    try:
        BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _summary() -> str:
    """给快照写一页人看的小抄：当前用的是哪家、哪个模型（不含 Key）。"""
    try:
        cfg = json.loads((CONFIG_DIR / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "（读不到 config.json）"
    chat = cfg.get("chat") or {}
    active = chat.get("active_provider")
    prov = (chat.get("providers") or {}).get(active) or {}
    lines = [
        f"桌宠版本: {cfg.get('version', '?')}",
        f"当前 provider: {active}",
        f"  名称  : {prov.get('name', '')}",
        f"  地址  : {prov.get('base_url', '')}",
        f"  模型  : {prov.get('model', '')}",
        f"  凭据条目: {prov.get('api_key_ref', '')}",
        "",
        "注意：API Key 存在 Windows 凭据管理器里，不在此备份内。",
        "      恢复配置后若提示认证失败，请在设置页重新粘贴一次 Key。",
    ]
    return "\n".join(lines)


def snapshot(quiet: bool = False) -> Path | None:
    if not CONFIG_DIR.exists():
        log(f"没找到桌宠配置目录：{CONFIG_DIR}", quiet)
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_ROOT / f"backup-{stamp}"
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in TARGETS:
        src = CONFIG_DIR / name
        if src.exists():
            shutil.copy2(src, dest / name)
            copied.append(name)
    if not copied:
        log("没有可备份的配置文件", quiet)
        return None
    (dest / "说明.txt").write_text(_summary(), encoding="utf-8")
    log(f"已备份 {len(copied)} 个文件 -> {dest}", quiet)
    _rotate(quiet)
    return dest


def _rotate(quiet: bool = False) -> None:
    snaps = sorted(p for p in BACKUP_ROOT.glob("backup-*") if p.is_dir())
    for old in snaps[:-KEEP]:
        shutil.rmtree(old, ignore_errors=True)
        log(f"清理旧快照 {old.name}", quiet=True)


def list_snapshots() -> list[Path]:
    return sorted((p for p in BACKUP_ROOT.glob("backup-*") if p.is_dir()), reverse=True)


def restore(snap: Path, target: Path, quiet: bool = False) -> bool:
    files = [p for p in snap.glob("config*.json")] + [snap / ".config-reset-generations.json"]
    files = [p for p in files if p.exists()]
    if not files:
        log(f"快照里没有配置文件：{snap}", quiet)
        return False
    target.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, target / f.name)
        log(f"恢复 {f.name} -> {target}", quiet)
    return True


def interactive(quiet: bool = False) -> int:
    snaps = list_snapshots()
    if not snaps:
        print("还没有任何快照。先双击一次「备份桌宠配置.bat」。")
        return 1
    print("可用快照（新 -> 旧）：\n")
    for i, s in enumerate(snaps[:15]):
        note = ""
        info = s / "说明.txt"
        if info.exists():
            for line in info.read_text(encoding="utf-8").splitlines():
                if line.startswith("  地址"):
                    note = line.split(":", 1)[-1].strip()
                    break
        print(f"  [{i}] {s.name}   {note}")
    print()
    try:
        raw = input("输入要恢复的序号（回车取消）: ").strip()
    except EOFError:
        return 1
    if not raw:
        print("已取消")
        return 1
    try:
        idx = int(raw)
        snap = snaps[idx]
    except (ValueError, IndexError):
        print("序号无效")
        return 1
    print(f"\n即将把 {snap.name} 写回：{CONFIG_DIR}")
    print("请先关闭桌宠（右键托盘退出），否则可能被正在运行的进程覆盖。")
    if input("输入 yes 确认: ").strip().lower() != "yes":
        print("已取消")
        return 1
    ok = restore(snap, CONFIG_DIR, quiet)
    if ok:
        print("\n完成。启动桌宠后如果提示认证失败，请在设置页重新粘贴一次 API Key。")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="桌宠配置快照/恢复")
    ap.add_argument("--quiet", action="store_true", help="静默（开机自启用）")
    ap.add_argument("--list", action="store_true", help="列出快照")
    ap.add_argument("--restore", type=int, help="恢复指定序号（0=最新）")
    ap.add_argument("--interactive", action="store_true", help="交互式恢复")
    ap.add_argument("--target-dir", default="", help="自测用：恢复到这个目录而不是真实配置目录")
    args = ap.parse_args()

    if args.list:
        snaps = list_snapshots()
        if not snaps:
            print("还没有快照")
        for i, s in enumerate(snaps):
            print(f"[{i}] {s.name}  {s}")
        return 0

    if args.interactive:
        return interactive(args.quiet)

    if args.restore is not None:
        snaps = list_snapshots()
        try:
            snap = snaps[args.restore]
        except IndexError:
            print("序号无效")
            return 1
        target = Path(args.target_dir) if args.target_dir else CONFIG_DIR
        return 0 if restore(snap, target, args.quiet) else 1

    return 0 if snapshot(args.quiet) else 1


if __name__ == "__main__":
    sys.exit(main())
