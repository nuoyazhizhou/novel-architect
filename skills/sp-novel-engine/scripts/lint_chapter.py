#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sp-novel-engine · 章节过闸脚本 (lint_chapter.py)

对单个章节 .md 文件跑 Check-1..10 启发式初判，输出每条规定 PASS/WARN/FAIL。
退出码: 0 = 无 FAIL, 1 = 存在 FAIL。

用法:
    python lint_chapter.py <章节.md> [--json]

注意: 机器只做初判; C2/C4/C5 的终判仍由协议学哨兵(执宪)与史官(司历)人工裁决。
正典路径见 skills/sp-novel-engine/references/canon-paths.md
"""

import sys
import re
import json

# ---------- 控制台 UTF-8 兼容（Windows cp936 下防中文乱码） ----------
try:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: E402
    pass

# ---------- 术语表 ----------

PROTOCOL_TERMS = [
    "信息带宽", "认证中心", "去中介化", "跨期终局性", "特权环", "Ring 隔离",
    "PDCA", "看板", "甘特图", "流程图", "SWOT", "思维导图", "模拟项目教学", "PVP",
    "四员下乡", "白话文基建", "公差接口", "标准化", "降维", "协议学", "白皮书",
    "制度CA", "认证中心竞争", "逻辑冗余", "物理冗余", "文明数据分析", "社会系统协议学",
    "瓦楞纸箱", "长尾夹", "万向轮", "锅驼机", "堆肥", "省柴灶", "喝开水",
]

DRIVER_TERMS = [
    "PDCA", "看板", "甘特图", "流程图", "SWOT", "思维导图", "模拟项目教学",
    "四员下乡", "堆肥", "省柴灶", "喝开水", "锅驼机", "瓦楞纸箱", "长尾夹",
]

# C3 时代错位否决词（1920-1940s 不应随意出现）
ANCIENTRONISM = [
    "手机", "互联网", "微信", "二维码", "电脑", "电视", "核武器", "原子弹",
    "导弹", "空调", "冰箱", "洗衣机", "高铁", "青霉素", "抗生素",
]

# C5 历史引力捕获词（描述林枫被动/失效）
DRIFT_PASSIVE = [
    "旁观", "看客", "小兵", "随从", "壁上观", "无能为力", "不知所措", "抄作业",
    "目击", "被动挨打", "被迫撤退",
]

# C6 粗暴简化词
CRUDE_TERMS = ["拼音化", "拼音改革", "简体字推行", "口号", "标语", "大字报", "贴标语"]

# C7 爽点偏移词
VIOLENCE_TERMS = ["暗杀", "江湖", "地摊", "械斗", "刺客", "帮派火拼", "单挑"]

# C2 未来年份（用于提示"可能为先知剧透"，交由哨兵裁决）
FUTURE_YEAR_RE = re.compile(r"(19[3-9]\d|20\d\d)\s*年")

# C9 概念溯源闸门：B 类未来名词 -> 1920s 脚手架关键词（命中任一即视为已做类比引入）
# 与 references/concept-genesis.md 的 B 类登记表保持同步
CONCEPT_GENESIS = {
    "特权环隔离": ["分权", "权限分层", "知县", "督抚", "互不兼掌", "兵权", "财权", "层级隔离", "内廷", "外朝"],
    "Ring-0": ["分权", "权限分层", "内核", "层级隔离"],
    "Ring-3": ["分权", "权限分层", "用户层", "层级隔离"],
    "去中介化": ["买办", "盘剥", "洋行", "层级加价", "过一道手", "雁过拔毛", "转口", "中间商", "居间"],
    "中间件": ["买办", "盘剥", "洋行", "中间商", "居间损耗", "过一道手"],
    "认证中心竞争": ["银号", "票号", "见票即付", "保函", "保人", "公信力", "背书", "信任凭证", "商埠信誉"],
    "制度CA": ["银号", "票号", "见票即付", "保函", "公信力", "信任凭证"],
    "跨期终局性": ["远期汇票", "兑付风险", "见票即付", "银根", "长期信用", "跨年契约", "毁约", "赖账", "契约精神"],
    "时间锁": ["远期汇票", "兑付", "长期信用", "跨年契约", "契约精神"],
    "脑裂": ["两省争税", "各发告示", "互不认账", "政出多门", "令不出都门", "各自为政", "双头指挥"],
    "split-brain": ["争税", "互不认账", "政出多门", "各自为政", "双头指挥"],
    "技术债": ["凑合", "权宜", "补丁", "拆东墙", "临时办法", "欠账", "越改越乱"],
    "协议栈": ["从下到上", "地基", "层层支撑", "底层物理", "上层应用", "栈式", "分层架构"],
    "Syscall": ["上层调用", "底层接口", "内核", "接口封装", "系统调用"],
    "ABI": ["接口封装", "底层接口", "上层调用"],
    "Kernel": ["内核", "底层", "接口封装"],
    "Userland": ["用户层", "上层应用"],
    "Agent": ["各怀心思", "各有算盘", "趋利避害", "理性人", "博弈", "各自目标", "激励", "私利"],
    "智能体博弈": ["各怀心思", "各有算盘", "趋利避害", "博弈", "私利", "激励"],
    "TCP/UDP": ["回执", "确认", "有来有回", "单线动员", "无反馈", "石沉大海", "对账"],
    "ACK": ["回执", "确认", "有来有回", "对账"],
    "API": ["接口", "对接", "即插即用", "标准件", "互操作"],
    "哈希": ["重名", "撞名", "同音误读", "辨识混淆", "二简字", "简化混淆"],
    "hash碰撞": ["重名", "撞名", "同音误读", "辨识混淆", "二简字"],
    "PDCA": ["计划执行检查改进", "循环改进", "复盘", "计划-执行-检查-改进"],
    "看板": ["卡片", "看板墙", "任务可视化", "进度牌", "一目了然"],
    "Kanban": ["卡片", "看板墙", "任务可视化", "进度牌"],
    "MVP": ["先做个能用的", "小步快跑", "边试边改", "最小版本", "快速试错"],
    "最小可行产品": ["小步快跑", "边试边改", "快速试错", "最小版本"],
}
# 解释标记：出现即视为已做类比引入/教学讲解（合理铺垫）
EXPLAIN_MARKERS = ["即", "好比", "如同", "说白了", "打个比方", "你可以理解为",
                   "换句话说", "本质上", "通俗讲", "类比", "打比方", "换言之", "也就是"]


# C10 文笔质检：AI 味套路词 + 告知式说理词（仅密度告警，终判交文笔·修辞 agent）
AI_TELLS = [
    "仿佛", "宛如", "宛若", "蓦然", "眸光", "沉声", "低低地", "嘴角勾起", "眼中闪过",
    "心中一凝", "刹那间", "与此同时", "不得不说", "某种意义上", "可以说", "值得一提的是",
    "综上所述", "在其看来", "不难发现", "一抹", "缓缓", "沉吟", "意味深长地", "幽幽",
    "怔了怔", "定了定神", "凝视着", "良久", "不由得", "下意识地", "油然而生", "恍若",
    "暗忖", "心下", "眉心微蹙", "嘴角微扬", "眸光一闪", "一股", "之感",
]
META_TELLS = [
    "这说明", "这意味着", "本质上说", "不难看出", "众所周知", "毋庸置疑",
    "毫不夸张地说", "某种意义上说", "换句话说就是",
]


# ---------- 跨章公理前置清单（State Ledger） ----------
# 概念在某章完成 1920s 脚手架铺垫后，写入 .local/axiom_ledger.json；
# 后序章节直接引用该概念时不再强制重复脚手架（避免每次都打长比方）。
import os
_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_LEDGER_PATH = os.path.join(_PLUGIN_ROOT, ".local", "axiom_ledger.json")


def load_ledger():
    try:
        if os.path.exists(_LEDGER_PATH):
            with open(_LEDGER_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:  # noqa
        pass
    return {}


def save_ledger(ledger):
    try:
        os.makedirs(os.path.dirname(_LEDGER_PATH), exist_ok=True)
        with open(_LEDGER_PATH, "w", encoding="utf-8") as f:
            json.dump(ledger, f, ensure_ascii=False, indent=2)
    except Exception:  # noqa
        pass


def detect_doc_type(path, argv):
    """自动识别大纲/细纲 vs 小说正文，避免 C6 在大纲里误报。"""
    if "--outline" in argv:
        return "outline", "显式 --outline 标记"
    try:
        with open(path, "r", encoding="utf-8") as f:
            head = "".join([next(f, "") for _ in range(3)])
        if "<!-- lint:outline -->" in head:
            return "outline", "文件头 <!-- lint:outline -->"
    except Exception:  # noqa
        pass
    base = os.path.basename(path)
    if re.search(r"(细纲|大纲|任务|幕次|分幕)", base):
        return "outline", "文件名含大纲/细纲/任务特征"
    return "prose", ""


def extract_chapter_id(path):
    """从文件名或显式参数抽取章节标识，用于 ledger 标注解锁位置。"""
    base = os.path.basename(path)
    m = re.search(r"第[^章]*章", base)
    return m.group(0) if m else base


def count_terms(text, terms):
    return sum(text.count(t) for t in terms)


def check_c1(text):
    n = count_terms(text, PROTOCOL_TERMS)
    if n == 0:
        return "FAIL", "整章无协议学工具/论文/白皮书露出"
    if n <= 2:
        return "WARN", "协议学露出偏弱(仅 %d 处)，建议加强具体载体" % n
    return "PASS", "协议学露出 %d 处" % n


def check_c2(text):
    hits = FUTURE_YEAR_RE.findall(text)
    if not hits:
        return "PASS", "未发现明确的未来年份断言"
    # 仅提示, 终判交哨兵
    return "WARN", "出现未来年份表述 %s，需哨兵判定是否先知剧透" % (",".join(sorted(set(hits))))


def check_c3(text):
    hits = [w for w in ANCIENTRONISM if w in text]
    if not hits:
        return "PASS", "未发现明显时代错位词"
    return "FAIL", "疑似机械降神/时代错位: %s" % "、".join(hits)


def check_c5(text):
    if "林枫" not in text:
        return "FAIL", "本章无林枫出场(或为旁观章节)"
    passive = [w for w in DRIFT_PASSIVE if w in text]
    if passive:
        return "FAIL", "林枫呈被动/失效态: %s" % "、".join(passive)
    return "PASS", "林枫具主动施动"


def check_c6(text, doc_type="prose"):
    if doc_type == "outline":
        return "SKIP", "大纲/细纲模式跳过C6（口号/标语属正常规划词）"
    hits = [w for w in CRUDE_TERMS if w in text]
    if not hits:
        return "PASS", "未发现粗暴简化表述"
    return "FAIL", "疑似二简字式压缩过头: %s" % "、".join(hits)


def check_c7(text):
    v = count_terms(text, VIOLENCE_TERMS)
    p = count_terms(text, PROTOCOL_TERMS)
    if v > 0 and v >= p:
        return "FAIL", "暴力/江湖爽点占比压过协议学爽点(暴=%d, 协议=%d)" % (v, p)
    if v > 0:
        return "WARN", "存在暴力/江湖爽点，需确认主爽点仍为协议学降维"
    return "PASS", "主爽点为协议学武器"


def check_c8(text):
    n = count_terms(text, DRIVER_TERMS)
    if n == 0:
        return "FAIL", "无八大驱动工具/基层微观剩余落地"
    if n <= 2:
        return "WARN", "驱动工具仅 %d 处点缀，建议融入情节" % n
    return "PASS", "驱动工具/微观剩余落地 %d 处" % n


def check_c9(text, ledger=None, chapter_id=""):
    """概念溯源闸门。ledger 为跨章已解锁公理清单（dict: term -> {unlocked_in, method}）。
    返回 (result, detail, established)，established 为本章新建立、可回写 ledger 的概念。"""
    ledger = ledger or {}
    hits = {term: sc for term, sc in CONCEPT_GENESIS.items() if term in text}
    if not hits:
        return "PASS", "未检出 B 类超时代名词空降", []
    missing = []
    explained = []
    established = []  # 本章通过脚手架/解释建立的概念，回写 ledger
    for term, sc in hits.items():
        # 已在跨章 ledger 中解锁 → 直接 PASS（无需重复脚手架）
        if term in ledger:
            continue
        has_scaffold = any(s in text for s in sc)
        has_explain = any(m in text for m in EXPLAIN_MARKERS)
        if has_scaffold:
            established.append((term, "scaffold"))
            continue
        if has_explain:
            established.append((term, "explain"))
            explained.append(term)
            continue
        missing.append(term)
    if not missing:
        note = ("(已解释: %s)" % "、".join(explained)) if explained else ""
        if established:
            note += " (本章新铺垫: %s)" % "、".join("%s@%s" % (t, chapter_id) for t, _ in established)
        return "PASS", "B 类名词均有 1920s 铺垫或解释%s" % note, established
    # 区分严重空降：连任何铺垫信号都没有
    any_signal = any(s in text for sc in CONCEPT_GENESIS.values() for s in sc) \
        or any(m in text for m in EXPLAIN_MARKERS)
    if not any_signal:
        return "FAIL", "严重空降术语(无任何铺垫信号): %s —— 须先以1920s语境铺脚手架再点名" % "、".join(missing), established
    return "WARN", "疑似空降术语(缺1920s铺垫): %s —— 建议补类比引入或解释标记" % "、".join(missing), established


def check_c10(text):
    """文笔质检（机器初判）：AI 味套路词密度 + 告知式说理词。仅 WARN/PASS，终判交文笔·修辞 agent。"""
    n_chars = max(len(text), 1)
    ai = sum(text.count(t) for t in AI_TELLS)
    meta = sum(text.count(t) for t in META_TELLS)
    density = ai * 1000.0 / n_chars
    if density >= 6 or meta >= 3:
        return "WARN", "疑似AI味套路词偏高(约%d处/千字, 告知式说理%d处)，建议文笔·修辞做去AI味终判" % (round(density), meta)
    return "PASS", "文笔初判：AI味词密度正常(约%d处/千字)" % round(density)


def main():
    if len(sys.argv) < 2:
        print("Usage: python lint_chapter.py <chapter.md> [--json] [--outline] [--update-ledger] [--chapter-id 第X章]")
        sys.exit(2)
    path = sys.argv[1]
    as_json = "--json" in sys.argv
    update_ledger = "--update-ledger" in sys.argv

    # 文档类型（大纲/细纲 vs 小说正文）
    doc_type, doc_reason = detect_doc_type(path, sys.argv)

    # 章节标识（用于 ledger 标注解锁位置）
    if "--chapter-id" in sys.argv:
        ci = sys.argv[sys.argv.index("--chapter-id") + 1]
    else:
        ci = extract_chapter_id(path)

    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:  # noqa
        print("读取失败: %s" % e)
        sys.exit(2)

    ledger = load_ledger()
    c9_res, c9_detail, c9_established = check_c9(text, ledger, ci)

    # 回写跨章公理前置清单
    if update_ledger and c9_established:
        for term, method in c9_established:
            ledger[term] = {"unlocked_in": ci, "method": method}
        save_ledger(ledger)

    results = [
        ("C1", "协议学露出", *check_c1(text)),
        ("C2", "先知剧透 vs 推演", *check_c2(text)),
        ("C3", "时代物理阻抗", *check_c3(text)),
        ("C5", "历史引力检测", *check_c5(text)),
        ("C6", "二简字式压缩", *check_c6(text, doc_type)),
        ("C7", "爽点偏移", *check_c7(text)),
        ("C8", "驱动工具落地", *check_c8(text)),
        ("C9", "概念溯源闸门", c9_res, c9_detail),
        ("C10", "文笔质检", *check_c10(text)),
    ]

    has_fail = any(r[2] == "FAIL" for r in results)

    if as_json:
        out = [{"check": r[0], "name": r[1], "result": r[2], "detail": r[3]} for r in results]
        print(json.dumps({
            "exit": 1 if has_fail else 0,
            "doc_type": doc_type,
            "chapter_id": ci,
            "checks": out,
            "ledger_updated": (["%s@%s" % (t, ci) for t, _ in c9_established] if update_ledger else []),
        }, ensure_ascii=False, indent=2))
    else:
        print("=" * 48)
        print("sp-novel-engine 章节过闸: %s" % path)
        if doc_type == "outline":
            print("文档类型: 大纲/细纲 (%s) → C6 已跳过" % doc_reason)
        print("=" * 48)
        for cid, name, res, detail in results:
            print("[%s] %-14s %-5s %s" % (cid, name, res, detail))
        print("-" * 48)
        if update_ledger and c9_established:
            print("公理清单已更新: %s" % "、".join("%s@%s" % (t, ci) for t, _ in c9_established))
        print("结论: %s" % ("存在 FAIL，打回重写" if has_fail else "无 FAIL，可送哨兵/史官"))
        print("=" * 48)

    sys.exit(1 if has_fail else 0)


if __name__ == "__main__":
    main()
