# -*- coding: utf-8 -*-
"""把本仓作为一个完整 WorkBuddy 专家包挂载到两个落点，并检出轨。

与 cw-alm / agent-commons 的差别：本仓根目录**本身就是完整包**（人格、技能、头像、
元数据同处一地），没有「公共池 → 合成」这一步；`rules/` 是项目级 IDE 规则、
`tools/` 与 `tests/` 是维护工具，都不属于包内容，计划里明确排除。

WorkBuddy 只从固定路径加载，仓根不能当加载路径，所以形态仍是「仓 = 源，落点 = 投影」。
应用实际读的是 `cache/<market>/<name>/<version>/`，只写 marketplaces 不生效（已实测）。

退出码三态：0=一致/成功，2=漂移或前置缺失，64=用法错误。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_USAGE = 64

REPO_ROOT = Path(__file__).resolve().parents[1]
WB_HOME = Path.home() / ".workbuddy"
WB_MARKET_ROOT = WB_HOME / "plugins" / "marketplaces" / "my-experts"
WB_MARKET = WB_MARKET_ROOT / "plugins"
WB_CACHE = WB_HOME / "plugins" / "cache" / "my-experts"
MARKET_JSON = WB_MARKET_ROOT / ".codebuddy-plugin" / "marketplace.json"

EXPERT_NAME = "novel-architect"
PLUGIN_REL = ".codebuddy-plugin/plugin.json"
# 明确列出包的组成，而不是「除 .git 外全拷」——漏掉这条会把 tools/tests 投到宿主。
INCLUDE = (".codebuddy-plugin", "agents", "skills", "avatars")
EXTRA_FILES = ("README.md", "settings.json")
SKIP_DIRS = frozenset({"__pycache__", ".in_use"})
SKIP_SUFFIXES = frozenset({".pyc", ".pyo"})
# 应用自己写的运行时标记：不是包内容，既不能报「多余」，也不能被 --apply 删掉，
# 否则应用下次刷新又会重建，制造永远清不掉的 DRIFT。
SKIP_NAMES = frozenset({".orphaned_at"})
AVATAR_SIZE = (512, 512)
AVATAR_MAX_BYTES = 500 * 1024


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ignored(rel: Path) -> bool:
    return (
        bool(set(rel.parts) & SKIP_DIRS)
        or rel.suffix in SKIP_SUFFIXES
        or rel.name in SKIP_NAMES
    )


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def _walk(base: Path) -> list[tuple[Path, Path]]:
    """遍历但遇链接剪枝；穿进 Junction 会把源目录文件误当成落点已有文件。"""
    if not base.is_dir():
        return []
    out: list[tuple[Path, Path]] = []
    stack = [base]
    while stack:
        current = stack.pop()
        for item in current.iterdir():
            rel = item.relative_to(base)
            if _ignored(rel):
                continue
            if _is_link(item):
                out.append((item, rel))
            elif item.is_dir():
                out.append((item, rel))  # 目录也要暴露给空壳清理，但仍继续下钻
                stack.append(item)
            else:
                out.append((item, rel))
    return out


def _png_size(path: Path) -> tuple[int, int] | None:
    """只读 PNG IHDR 拿宽高，不引 Pillow（CI 上没装也能校验）。"""
    try:
        with path.open("rb") as fh:
            head = fh.read(24)
    except OSError:
        return None
    if head[:8] != b"\x89PNG\r\n\x1a\n" or len(head) < 24:
        return None
    return struct.unpack(">II", head[16:24])


def read_plugin(root: Path | None = None) -> dict:
    path = (root or REPO_ROOT) / PLUGIN_REL
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _check_metadata(root: Path, plugin: dict) -> list[str]:
    """合成/挂载前的硬约束：team 元数据自洽 + settings.json + 头像规格。"""
    problems: list[str] = []
    if str(plugin.get("expertType") or "") != "team":
        return problems

    agent_name = str(plugin.get("agentName") or "")
    team = plugin.get("teamInfo") or {}
    if str(team.get("leadAgent") or "") != agent_name:
        problems.append(f"teamInfo.leadAgent 与 agentName 不一致：{team.get('leadAgent')!r} / {agent_name!r}")

    # 声明里的路径是文件名（./agents/dispatcher.md），而 memberAgents 用的是人格 id
    # （novel-architect-dispatcher）——两者不同名。按 frontmatter 的 name 匹配，
    # 不能像公共库那样靠 basename 猜，否则会误报「角色未声明」。
    declared: set[str] = set()
    for item in plugin.get("agents") or []:
        path = root / str(item).replace("\\", "/")
        if not path.is_file():
            problems.append(f"声明的 agent 文件不存在：{item}")
            continue
        match = re.search(r'^name:\s*["\']?([\w.\-]+)', path.read_text(encoding="utf-8-sig"), re.M)
        if match:
            declared.add(match.group(1))
        else:
            problems.append(f"agent 缺 frontmatter name：{item}")
    for member in [agent_name, *(team.get("memberAgents") or [])]:
        if member not in declared:
            problems.append(f"团队角色 {member!r} 未出现在 agents 声明的 name 里")

    settings = root / "settings.json"
    if not settings.is_file():
        problems.append("team 型缺 settings.json")
    else:
        try:
            agent = str(json.loads(settings.read_text(encoding="utf-8-sig")).get("agent") or "")
        except ValueError as exc:
            problems.append(f"settings.json 不是合法 JSON：{exc}")
        else:
            if agent != agent_name:
                problems.append(f"settings.json 的 agent={agent!r} 与 agentName={agent_name!r} 不一致")

    avatars = root / "avatars"
    for path in sorted(avatars.glob("*.png")) if avatars.is_dir() else []:
        if _png_size(path) != AVATAR_SIZE:
            problems.append(f"{path.name} 尺寸不是 {AVATAR_SIZE}：{_png_size(path)}")
        if path.stat().st_size > AVATAR_MAX_BYTES:
            problems.append(f"{path.name} 超过 500KB：{path.stat().st_size}")
    return problems


def expert_plan(root: Path | None = None) -> dict[str, Path]:
    """本包的「应有文件」映射：相对路径 → 源文件；只含包内容，不含维护工具。"""
    root = root or REPO_ROOT
    plugin = read_plugin(root)
    problems = _check_metadata(root, plugin)
    if problems:
        raise ValueError("；".join(problems))

    plan: dict[str, Path] = {}
    for folder in INCLUDE:
        # rel 是相对各 folder 的，必须补回 folder 前缀；漏掉会把 agents/*.md、
        # avatars/*.png 全部平铺到落点根目录，专家包结构直接失效。
        for item, rel in _walk(root / folder):
            if item.is_file() and not _is_link(item):
                plan[f"{folder}/{rel.as_posix()}"] = item
    for name in EXTRA_FILES:
        if (root / name).is_file():
            plan[name] = root / name
    return plan


def expert_version(root: Path | None = None) -> str:
    try:
        return str(read_plugin(root).get("version") or "")
    except (OSError, ValueError):
        return ""


def read_registry(path: Path | None = None) -> dict:
    path = path or MARKET_JSON
    return json.loads(path.read_text(encoding="utf-8-sig"))


def registry_problems(
    plugin: dict, path: Path | None = None, root: Path | None = None
) -> list[str]:
    """检查 marketplace.json 是否登记本包。

    应用会周期性重写这份注册表（它自称 auto-generated），把不在它视野里的包
    标成孤儿并清掉注册项。只写落点不查注册表，专家中心照样看不到本团。
    """
    path = path or MARKET_JSON
    if not path.is_file():
        return [f"注册表不存在 {path}"]
    try:
        data = read_registry(path)
    except (OSError, ValueError) as exc:
        return [f"注册表不是合法 JSON：{exc}"]
    plugins = data.get("plugins")
    if not isinstance(plugins, list):
        return ["注册表缺 plugins 数组"]

    entry = next(
        (p for p in plugins if isinstance(p, dict) and p.get("name") == EXPERT_NAME),
        None,
    )
    if entry is None:
        return [f"注册表缺 {EXPERT_NAME} 条目（专家中心看不到本团）"]

    problems: list[str] = []
    want_source = f"./plugins/{EXPERT_NAME}"
    if str(entry.get("source") or "") != want_source:
        problems.append(f"注册表 source={entry.get('source')!r}，应为 {want_source!r}")
    version = str(plugin.get("version") or expert_version(root))
    if version and str(entry.get("version") or "") != version:
        problems.append(f"注册表 version={entry.get('version')!r}，应为 {version!r}")
    return problems


def registry_apply(plugin: dict, path: Path | None = None, root: Path | None = None) -> bool:
    """幂等补回/修正注册表条目；其他包条目一律不动。返回是否发生写入。"""
    path = path or MARKET_JSON
    if path.is_file():
        data = read_registry(path)
    else:
        data = {}
    plugins = data.get("plugins")
    if not isinstance(plugins, list):
        plugins = []
        data["plugins"] = plugins

    version = str(plugin.get("version") or expert_version(root))
    want = {
        "name": EXPERT_NAME,
        "source": f"./plugins/{EXPERT_NAME}",
        "description": str(plugin.get("displayDescription") or plugin.get("description") or ""),
        "version": version,
    }
    entry = next(
        (p for p in plugins if isinstance(p, dict) and p.get("name") == EXPERT_NAME),
        None,
    )
    if entry is None:
        plugins.append(want)
    else:
        for key, value in want.items():
            if key == "description":
                continue  # 不覆盖已有文案，只补关键的 name/source/version
            if str(entry.get(key) or "") != value:
                entry[key] = value

    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8-sig") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def heal_settings(plan: dict[str, Path], dest: Path) -> str | None:
    """只复原被应用清掉的 settings.json；其他文件一律不碰。

    与 ``apply`` 的区别：apply 是全量对齐（会删落点里应用写入的运行时数据），
    heal 只补 team 型的必需配置，适合在专家中心刷新后反复跑。
    """
    src = plan.get("settings.json")
    if src is None:
        return None
    target = dest / "settings.json"
    if target.is_file() and sha256(target) == sha256(src):
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    return str(target)


def _strip_links(dest: Path) -> list[str]:
    """先断链再铺文件：往 Junction 里写等于改源，清理更会从源里删文件。"""
    if not dest.is_dir():
        return []
    links = [(item, rel) for item, rel in _walk(dest) if _is_link(item)]
    removed: list[str] = []
    for item, rel in sorted(links, key=lambda pair: len(pair[1].parts), reverse=True):
        removed.append(rel.as_posix())
        try:
            os.rmdir(item)
        except OSError:
            item.unlink(missing_ok=True)
    return removed


def diff(plan: dict[str, Path], dest: Path) -> list[str]:
    problems: list[str] = []
    if not dest.is_dir():
        return [f"落点不存在 {dest}"] if plan else []
    entries = _walk(dest)
    for item, rel in entries:
        if _is_link(item):
            problems.append(f"残留链接 {rel.as_posix()}（会写穿源仓，须 --apply 重挂）")
    existing = {rel.as_posix() for item, rel in entries if item.is_file() and not _is_link(item)}
    for rel, src in sorted(plan.items()):
        target = dest / rel
        if not target.is_file():
            problems.append(f"缺失 {rel}")
        elif sha256(target) != sha256(src):
            problems.append(f"内容不同 {rel}")
    for rel in sorted(existing - set(plan)):
        problems.append(f"多余 {rel}")
    return problems


def _prune_empty_dirs(dest: Path, plan: dict[str, Path]) -> None:
    """清掉计划外的**空**目录。

    漂移比对只看文件，早期错误版本铺出的空壳目录（如平铺的 ``sp-novel-engine/``）
    既不会报 DRIFT，也不会被按文件清理，会永久留在落点里。非空目录一律不动——
    落点里可能有应用写入的运行时数据，不能替用户删。
    """
    keep: set[str] = set()
    for rel in plan:
        parts = rel.split("/")
        for i in range(1, len(parts)):
            keep.add("/".join(parts[:i]))

    dirs = [item for item, _ in _walk(dest) if item.is_dir() and not _is_link(item)]
    for item in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        rel = item.relative_to(dest).as_posix()
        if rel not in keep and not any(item.iterdir()):
            item.rmdir()


def apply(plan: dict[str, Path], dest: Path) -> tuple[int, list[str]]:
    stripped = _strip_links(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for rel in sorted(_dir_files(dest)):
        if rel not in plan:
            (dest / rel).unlink()
    for rel, src in sorted(plan.items()):
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    _prune_empty_dirs(dest, plan)
    return len(plan), stripped


def _dir_files(dest: Path) -> dict[str, Path]:
    return {rel.as_posix(): item for item, rel in _walk(dest) if item.is_file() and not _is_link(item)}


def targets(root: Path | None = None) -> list[tuple[str, Path, dict[str, Path]]]:
    root = root or REPO_ROOT
    plan = expert_plan(root)
    version = expert_version(root)
    out = [(f"workbuddy-market/{EXPERT_NAME}", WB_MARKET / EXPERT_NAME, plan)]
    if version:
        out.append(
            (f"workbuddy-cache/{EXPERT_NAME}@{version}", WB_CACHE / EXPERT_NAME / version, plan)
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="挂载星火小说架构师专家包到 WorkBuddy，或只检漂移")
    parser.add_argument("--check", action="store_true", help="只比对不落盘（默认行为）")
    parser.add_argument("--apply", action="store_true", help="写入落点（含注册表）")
    parser.add_argument(
        "--heal",
        action="store_true",
        help="轻量自愈：只补被删的 settings.json 与注册表条目，不动其他文件",
    )
    parser.add_argument(
        "--check-source",
        action="store_true",
        help="只校验仓内包可挂载（不依赖宿主落点，CI 用）",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON（CI 解析用）")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_OK if not exc.code else EXIT_USAGE

    try:
        plan = expert_plan()  # 前置校验：元数据/头像不合规时不碰落点
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return EXIT_VIOLATION

    if args.check_source:
        # CI 没有 ~/.workbuddy 落点；只验证仓内包自身完整（含头像规格与 team 元数据）。
        print(f"SOURCE OK {EXPERT_NAME:<40} files={len(plan)}")
        return EXIT_OK

    plugin = read_plugin()
    reg_problems = registry_problems(plugin)
    reg_label = "workbuddy-registry/novel-architect"

    if args.heal:
        healed: list[str] = []
        for _, dest, target_plan in targets():
            restored = heal_settings(target_plan, dest)
            if restored:
                healed.append(restored)
        if reg_problems:
            registry_apply(plugin)
            healed.append(str(MARKET_JSON))
        for item in healed:
            print(f"HEAL {item}")
        if not healed:
            print("HEAL 无需修复：settings.json 与注册表均正常")
        return EXIT_OK

    results = []
    drifted = 0
    for label, dest, target_plan in targets():
        problems = diff(target_plan, dest)
        drifted += bool(problems)
        results.append(
            {"target": label, "path": str(dest), "files": len(target_plan), "ok": not problems, "problems": problems}
        )
        if args.apply:
            written, stripped = apply(target_plan, dest)
            print(f"APPLY {label:<44} files={written}")
            for rel in stripped:
                print(f"       已剥离链接 {rel}（防写穿源仓）", file=sys.stderr)
    results.append(
        {
            "target": reg_label,
            "path": str(MARKET_JSON),
            "files": 1,
            "ok": not reg_problems,
            "problems": reg_problems,
        }
    )
    drifted += bool(reg_problems)

    if args.apply and reg_problems:
        registry_apply(plugin)
        print(f"APPLY {reg_label:<44} 已补回注册项")

    if args.json:
        print(json.dumps({"ok": not drifted, "targets": results}, ensure_ascii=False, indent=2))
    elif not args.apply:
        for r in results:
            print(f"{'OK   ' if r['ok'] else 'DRIFT'} {r['target']:<44} files={r['files']}")
        for r in results:
            for p in r["problems"]:
                print(f"       - {r['target']}: {p}", file=sys.stderr)

    if args.apply:
        print(f"\n挂载完成：{len(results) - 1} 个落点 + 注册表 → {WB_HOME}")
        return EXIT_OK
    if drifted:
        print(
            f"\n{drifted} 处与仓库不一致；全量同步跑 --apply，只补被删配置跑 --heal。",
            file=sys.stderr,
        )
        return EXIT_VIOLATION
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
