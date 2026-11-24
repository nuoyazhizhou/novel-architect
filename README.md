# 星火小说架构师 · novel-architect

为长篇历史穿越小说《星火》（主角：2025 年工信部处长林枫，核心魅力 = 《社会系统协议学》专家 + 议题设置者 + 技术官僚）打造的 **写-审-纠-核闭环插件**。

## 解决的核心痛点

长篇历史穿越文在连载/扩纲时最容易恶性崩坏为：

1. **历史滑坡**——按历史时间表打卡，林枫变旁观者或抄作业小兵；
2. **设定遗忘**——忘记自己发表过的协议学论文、忘记二简字 Hash 碰撞警示，开始粗暴拼音化/口号化；
3. **爽点偏移**——把「高维协议降维打击 / 论文武器库 / 制度 CA 竞争」的硬核科技官僚爽点，写成江湖暗杀或地摊打仗。

本插件用一套强约束机制把这些崩坏挡在成稿之前。

## 组件

| 组件 | 文件 | 职责 |
|------|------|------|
| 总调度（总编辑） | `agents/dispatcher.md` | 编排写-审-纠-核工序，汇编交付，门禁裁决 |
| 主笔·天工 | `agents/plot-architect.md` | 情节推进、张力与爽点落地，把协议学论文转成故事冲突 |
| 哨兵·协议学（执宪） | `agents/protocol-sentinel.md` | **最关键**：死防写成历史小说，监督林枫以协议学武器推进 |
| 考据·史官（司历） | `agents/timeline-auditor.md` | 蝴蝶效应时间线因果审计，NPC 反应须随扰动改变；并追踪林枫/配角人物弧光连续性 |
| 文笔·修辞（修辞） | `agents/prose-rhetoric.md` | 去 AI 味 / 代入感 / Show-don't-tell / 视角与节奏——前三者不管的"写得好不好读"维度（Check-10 终判） |
| 引擎 Skill | `skills/sp-novel-engine/` | `sp-novel-engine` 规则集 + 校验脚本 + 活体素材索引 |
| 专家团元数据 | `.codebuddy-plugin/plugin.json` | WorkBuddy team 型声明：lead + 4 成员、members、头像索引 |
| 团队配置 | `settings.json` | team 型必需，指向 lead；客户端会周期性清掉，靠 `--apply` 复原 |
| 头像 | `avatars/*.png` | 6 张 512×512 PNG，由 `tools/gen_avatars.py` 确定性生成 |
| 挂载工具 | `tools/mount.py` | 把本仓投到 WorkBuddy 两个落点，并检出轨 |
| 项目规则 | `rules/AGENTS.md` | IDE 级协作铁律，**不属于**专家包内容 |

## 知识底座（引用活体文件，不复制）

所有正典与素材都**按绝对路径直接读取 `C:\git_work\大纲` 下的活体文件**，见 `skills/sp-novel-engine/references/canon-paths.md`。改了原著，约束自动同步，不会过期。

## 安装为 WorkBuddy 专家团

本仓根目录**本身就是完整专家包**（人格、技能、头像、元数据同处一地），不需要合成步骤。
不要手工拷贝，跑挂载工具：

```bash
python tools/mount.py --check     # 只读比对两个落点 + 注册表，不一致返 2
python tools/mount.py --apply     # 全量写入两个落点，并补回注册表条目
python tools/mount.py --heal      # 轻量自愈：只补被删的 settings.json 与注册项
```

两处都必须写——应用实际加载的是 `~/.workbuddy/plugins/cache/my-experts/novel-architect/1.0.0/`，
只写 `marketplaces/` 不生效（已实测）。`--check` 还会查 `marketplace.json`：这份注册表是应用
auto-generated 的，会周期性重写并把不在视野里的包标成孤儿（落点出现 `.orphaned_at` 标记）、
清掉注册项——**光有落点文件、注册项没了，专家中心照样看不到本团**。注册表条目丢失或版本落后
都由 `--apply` / `--heal` 幂等补回，不动其他包的条目。`.orphaned_at` 是应用运行时标记，
已明确排除在漂移检测之外，不会被误报或删除。

**settings.json 会在应用刷新专家中心时被清掉**（team 型必需，缺了加载不了）。这是应用行为，
改不了源头，所以提供 `--heal`：只补 settings.json 和注册表条目，**不碰落点里的其他文件**——
全量 `--apply` 会删掉应用写进落点的运行时数据，`--heal` 不会。删除后跑一次即可，反复跑幂等。
挂载工具只搬包内容；`rules/`、`tools/`、`tests/`、`.git/` 明确排除，避免把维护工具投进宿主。

**头像**由 `tools/gen_avatars.py` 生成：512×512 PNG、单张 < 500KB、零外部模型依赖、可重跑。
改配色后跑 `python tools/gen_avatars.py`，再 `--apply` 同步落点。
`mount.py` 会在挂载前校验头像规格、team 元数据自洽（`settings.json.agent` 必须等于
`plugin.json.agentName`），不合规就整体拒绝，不产生「铺好了但加载不了」的包。

## 校验

每章成稿跑 `python skills/sp-novel-engine/scripts/lint_chapter.py <章节.md>`，按 Check-1..10 过闸；规则明细见 `references/linter-rules.md` 与 `references/concept-genesis.md`。

仓库自检：

```bash
C:/Python314/python.exe -m pytest tests/ -q              # 20 例：包边界 / 元数据 / 头像 / 漂移 / 写穿 / 注册表 / 自愈
python tools/gen_avatars.py --check                      # 6 张头像规格
python tools/mount.py --check                            # 两个落点 + 注册表与仓一致
python tools/mount.py --check-source                     # CI：只验仓内源，不依赖宿主落点
```

### 常用参数
- 大纲/细纲文件：自动跳过 C6（或显式 `--outline`），避免「口号/标语」规划词误报。
- 跨章公理前置：`python ... <章节.md> --update-ledger` 将本章新铺垫的 B 类超时代名词记入 `.local/axiom_ledger.json`；后序章节引用已解锁概念时 C9 直接 PASS，无需重复脚手架。重置账本删该 json 即可。
- `--json` 输出结构化结果，便于接入 CI / 总调度程序化读取。
- Windows 控制台乱码：脚本已内置 UTF-8 重定向保护。

## 红线

- 不代写整章正文（平台对纯 AI 代写封禁）；
- 哨兵对「历史化/降智/二简字式压缩过头」拥有一票否决；
- 一切结论由对应专家出具，总调度不冒充成员结论。
