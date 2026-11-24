"""``tools/mount.py`` 单测：包边界、元数据自洽、头像规格、漂移与写穿防御。

fixture 全部 tmp_path 临时构建，不读真实仓、不碰宿主落点。

回归锚：本包的人格**文件名与身份 id 不同名**（``dispatcher.md`` vs
``novel-architect-dispatcher``），所以成员声明核对必须读 frontmatter 的 ``name``，
不能像公共库那样按 basename 猜——首版就在这里误报了五个「角色未声明」。
"""

import importlib.util
import json
import struct
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TOOL = _REPO_ROOT / "tools" / "mount.py"

_spec = importlib.util.spec_from_file_location("novel_mount", _TOOL)
mount = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mount  # 模块内注解/异常反查需要，否则 exec_module 失败
_spec.loader.exec_module(mount)

ID = "novel-architect-dispatcher"
PERSONAS = (
    ("dispatcher", ID, "总调度"),
    ("plot-architect", "novel-plot-architect", "天工"),
    ("protocol-sentinel", "novel-protocol-sentinel", "执宪"),
    ("timeline-auditor", "novel-timeline-auditor", "司历"),
    ("prose-rhetoric", "novel-prose-rhetoric", "修辞"),
)
AVATARS = (ID, "novel-plot-architect", "novel-protocol-sentinel", "novel-timeline-auditor", "novel-prose-rhetoric", "team")


def _png(width=512, height=512) -> bytes:
    """最小合法 PNG 头：mount 只读 IHDR，不需要真实像素数据。

    布局固定：8 字节 signature + 4 长度 + b'IHDR' + 宽 + 高 + 5 字节参数；
    ``_png_size`` 从 [16:24] 取宽高，所以长度与 IHDR 四个字节不能省。
    """
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00"
    )


def _plugin() -> dict:
    return {
        "name": "novel-architect",
        "version": "1.2.3",
        "agents": [f"./agents/{filename}.md" for filename, _, _ in PERSONAS],
        "skills": ["./skills/sp-novel-engine"],
        "expertType": "team",
        "agentName": ID,
        "teamInfo": {
            "leadAgent": ID,
            "memberAgents": [agent_id for _, agent_id, _ in PERSONAS[1:]],
        },
        "avatar": "avatars/team.png",
        "quickPrompts": [{"zh": "a", "en": "a"}, {"zh": "b", "en": "b"}, {"zh": "c", "en": "c"}],
    }


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """造一个「根目录即完整包」的仓，并指向临时落点。"""
    (tmp_path / ".codebuddy-plugin").mkdir()
    (tmp_path / "agents").mkdir()
    (tmp_path / "avatars").mkdir()
    (tmp_path / "skills" / "sp-novel-engine" / "references").mkdir(parents=True)
    (tmp_path / "tools").mkdir()
    (tmp_path / "rules").mkdir()
    (tmp_path / "tests").mkdir()

    _write_plugin(tmp_path, _plugin())
    (tmp_path / "settings.json").write_text(json.dumps({"agent": ID}), encoding="utf-8")
    (tmp_path / "README.md").write_text("r", encoding="utf-8")
    (tmp_path / "skills" / "sp-novel-engine" / "SKILL.md").write_text("s", encoding="utf-8")
    (tmp_path / "skills" / "sp-novel-engine" / "references" / "r.md").write_text("x", encoding="utf-8")
    for filename, agent_id, zh in PERSONAS:
        (tmp_path / "agents" / f"{filename}.md").write_text(
            f'---\nname: {agent_id}\ndisplayName:\n  zh: "{zh}"\n---\n', encoding="utf-8"
        )
    for name in AVATARS:
        (tmp_path / "avatars" / f"{name}.png").write_bytes(_png())

    # 不属于包的内容：必须被排除在计划外
    (tmp_path / "tools" / "mount.py").write_text("x", encoding="utf-8")
    (tmp_path / "rules" / "AGENTS.md").write_text("x", encoding="utf-8")
    (tmp_path / "tests" / "test_mount.py").write_text("x", encoding="utf-8")
    (tmp_path / "plugin.json").write_text("legacy", encoding="utf-8")

    monkeypatch.setattr(mount, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mount, "WB_MARKET", tmp_path / "market")
    monkeypatch.setattr(mount, "WB_CACHE", tmp_path / "cache")
    return tmp_path


def _write_plugin(root: Path, data: dict) -> None:
    (root / ".codebuddy-plugin" / "plugin.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def test_plan_includes_package_only(repo):
    """包内容齐全，维护工具/规则/测试/旧简版 plugin.json 一律不入包。"""
    plan = mount.expert_plan(repo)
    assert ".codebuddy-plugin/plugin.json" in plan
    assert "settings.json" in plan and "README.md" in plan
    assert "agents/dispatcher.md" in plan
    assert "skills/sp-novel-engine/SKILL.md" in plan
    assert "skills/sp-novel-engine/references/r.md" in plan
    assert "avatars/team.png" in plan
    assert not any(k.startswith(("tools/", "rules/", "tests/")) for k in plan)
    assert "plugin.json" not in plan


def test_persona_id_matches_frontmatter_name_not_filename(repo):
    """回归锚：文件名 dispatcher.md 与 id novel-architect-dispatcher 不同名也要通过。"""
    assert mount.expert_plan(repo)["agents/dispatcher.md"].is_file()


def test_lead_mismatch_rejected(repo):
    data = _plugin()
    data["teamInfo"]["leadAgent"] = "novel-plot-architect"
    _write_plugin(repo, data)
    with pytest.raises(ValueError, match="leadAgent"):
        mount.expert_plan(repo)


def test_member_not_in_agents_declared_rejected(repo):
    """成员 id 没写进 agents 声明 → 报错，不许铺出缺人格的团队。"""
    data = _plugin()
    data["teamInfo"]["memberAgents"].append("ghost")
    _write_plugin(repo, data)
    with pytest.raises(ValueError, match="ghost"):
        mount.expert_plan(repo)


def test_missing_settings_rejected(repo):
    (repo / "settings.json").unlink()
    with pytest.raises(ValueError, match="settings.json"):
        mount.expert_plan(repo)


def test_settings_agent_mismatch_rejected(repo):
    (repo / "settings.json").write_text(json.dumps({"agent": "ghost"}), encoding="utf-8")
    with pytest.raises(ValueError, match="不一致"):
        mount.expert_plan(repo)


def test_bad_avatar_size_rejected(repo):
    (repo / "avatars" / "team.png").write_bytes(_png(256, 256))
    with pytest.raises(ValueError, match="尺寸"):
        mount.expert_plan(repo)


def test_oversized_avatar_rejected(repo):
    (repo / "avatars" / "team.png").write_bytes(_png() + b"x" * (mount.AVATAR_MAX_BYTES + 1))
    with pytest.raises(ValueError, match="500KB"):
        mount.expert_plan(repo)


def test_declared_agent_file_missing_rejected(repo):
    (repo / "agents" / "dispatcher.md").unlink()
    with pytest.raises(ValueError, match="文件不存在"):
        mount.expert_plan(repo)


def test_diff_detects_all_three_kinds(repo):
    plan = mount.expert_plan(repo)
    dest = repo / "dest"
    mount.apply(plan, dest)
    assert mount.diff(plan, dest) == []
    (dest / "README.md").write_text("drifted", encoding="utf-8")
    (dest / "agents" / "dispatcher.md").unlink()
    (dest / "stale.txt").write_text("x", encoding="utf-8")
    problems = mount.diff(plan, dest)
    assert any(p.startswith("内容不同 README.md") for p in problems)
    assert any(p.startswith("缺失 agents/dispatcher.md") for p in problems)
    assert any(p.startswith("多余 stale.txt") for p in problems)


def test_apply_is_idempotent_and_cleans_extra(repo):
    plan = mount.expert_plan(repo)
    dest = repo / "dest"
    written, stripped = mount.apply(plan, dest)
    assert written == len(plan) and stripped == []
    (dest / "agents" / "leftover.md").write_text("x", encoding="utf-8")
    mount.apply(plan, dest)
    assert not (dest / "agents" / "leftover.md").exists()
    assert mount.diff(plan, dest) == []


def test_apply_prunes_stray_empty_dirs(repo):
    """错误版本留下的空壳目录要清掉；哈希比对只看文件，不会报这种残留。"""
    plan = mount.expert_plan(repo)
    dest = repo / "dest"
    mount.apply(plan, dest)
    (dest / "sp-novel-engine" / "references").mkdir(parents=True)
    (dest / "agents" / "stray-empty").mkdir()
    mount.apply(plan, dest)
    assert not (dest / "sp-novel-engine").exists()
    assert not (dest / "agents" / "stray-empty").exists()
    # 真正承载文件的目录仍在（清理空壳不能误伤包的骨架）
    assert (dest / "agents" / "dispatcher.md").is_file()
    assert (dest / "avatars" / "team.png").is_file()


def test_walk_does_not_follow_links(repo, monkeypatch):
    dest = repo / "dest"
    (dest / "skills").mkdir(parents=True)
    fake = dest / "skills" / "sp-novel-engine"
    fake.mkdir()
    (fake / "SKILL.md").write_text("s", encoding="utf-8")
    real = mount._is_link
    monkeypatch.setattr(mount, "_is_link", lambda p: True if p == fake else real(p))
    rels = {rel.as_posix() for _, rel in mount._walk(dest)}
    assert "skills/sp-novel-engine" in rels
    assert "skills/sp-novel-engine/SKILL.md" not in rels


def test_registry_missing_is_detected_and_repaired(repo, monkeypatch):
    """注册表缺本团条目 → check 报漂移，apply 补回；其他包条目不动。"""
    reg = repo / "registry.json"
    monkeypatch.setattr(mount, "MARKET_JSON", reg)
    reg.write_text(
        json.dumps(
            {
                "name": "my-experts",
                "plugins": [
                    {
                        "name": "other-team",
                        "source": "./plugins/other-team",
                        "version": "2.0.0",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plugin = mount.read_plugin(repo)
    problems = mount.registry_problems(plugin, reg, repo)
    assert any("缺" in p for p in problems)

    assert mount.registry_apply(plugin, reg, repo) is True
    assert mount.registry_problems(plugin, reg, repo) == []
    data = json.loads(reg.read_text(encoding="utf-8"))
    assert {p["name"] for p in data["plugins"]} == {"other-team", "novel-architect"}
    # 幂等：再 apply 一次不产生写入
    assert mount.registry_apply(plugin, reg, repo) is False


def test_registry_version_drift_repaired(repo, monkeypatch):
    """注册表 version 落后于 plugin.json 时纠偏，不覆盖已有 description。"""
    reg = repo / "registry.json"
    monkeypatch.setattr(mount, "MARKET_JSON", reg)
    reg.write_text(
        json.dumps(
            {
                "plugins": [
                    {
                        "name": "novel-architect",
                        "source": "./plugins/novel-architect",
                        "description": "人工维护的文案",
                        "version": "0.9.0",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    plugin = mount.read_plugin(repo)
    assert any("version" in p for p in mount.registry_problems(plugin, reg, repo))
    mount.registry_apply(plugin, reg, repo)
    entry = json.loads(reg.read_text(encoding="utf-8"))["plugins"][0]
    assert entry["version"] == "1.2.3"
    assert entry["description"] == "人工维护的文案"


def test_orphaned_at_is_runtime_noise_not_drift(repo):
    """应用写的 .orphaned_at 是运行时标记，不能报多余，也不能被 apply 删。"""
    plan = mount.expert_plan(repo)
    dest = repo / "dest"
    mount.apply(plan, dest)
    (dest / ".orphaned_at").write_text("1795506906585", encoding="utf-8")
    assert mount.diff(plan, dest) == []
    mount.apply(plan, dest)
    assert (dest / ".orphaned_at").is_file()


def test_heal_restores_only_settings(repo):
    """settings 被删/改后只补它，不碰其他文件的应用侧改动。"""
    plan = mount.expert_plan(repo)
    dest = repo / "dest"
    mount.apply(plan, dest)
    (dest / "settings.json").unlink()
    (dest / "README.md").write_text("应用改写的内容", encoding="utf-8")

    assert mount.heal_settings(plan, dest) is not None
    assert (dest / "settings.json").is_file()
    assert mount.heal_settings(plan, dest) is None  # 幂等
    # heal 只管 settings，不动 README
    assert (dest / "README.md").read_text(encoding="utf-8") == "应用改写的内容"


def test_heal_cli_restores_registry_and_settings(repo, monkeypatch):
    reg = repo / "registry.json"
    monkeypatch.setattr(mount, "MARKET_JSON", reg)
    reg.write_text(json.dumps({"plugins": []}), encoding="utf-8")
    mount.main(["--apply"])  # 先铺好两个落点
    (repo / "market" / "novel-architect" / "settings.json").unlink()
    reg.write_text(json.dumps({"plugins": []}), encoding="utf-8")

    assert mount.main(["--heal"]) == mount.EXIT_OK
    assert (repo / "market" / "novel-architect" / "settings.json").is_file()
    assert mount.registry_problems(mount.read_plugin(repo), reg, repo) == []


def test_usage_error_returns_64(repo):
    assert mount.main(["--nope"]) == mount.EXIT_USAGE


def test_check_drift_then_apply_then_clean(repo):
    assert mount.main(["--check"]) == mount.EXIT_VIOLATION
    assert mount.main(["--apply"]) == mount.EXIT_OK
    assert (repo / "market" / "novel-architect" / "settings.json").is_file()
    assert (repo / "cache" / "novel-architect" / "1.2.3" / "settings.json").is_file()
    assert mount.main(["--check"]) == mount.EXIT_OK
