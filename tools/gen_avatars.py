# -*- coding: utf-8 -*-
"""生成星火小说架构师的 6 张头像（团队 + 5 人格），零外部模型依赖、可复现。

为什么不用图像生成：每张要消耗积分，且输出常超 500KB 需后处理；头像在这里只是
专家中心的身份标识，确定性脚本更合适——改配色重跑即可，不需要保存提示词或原图。

规格（与专家包校验一致）：512×512 PNG，单张 < 500KB。

用法：
    python tools/gen_avatars.py            # 写入 <repo>/avatars/
    python tools/gen_avatars.py --check    # 只核对头像存在且规格合规，不写盘
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - 环境依赖，不在单测覆盖范围
    raise SystemExit("需要 Pillow：pip install pillow") from exc

ROOT = Path(__file__).resolve().parents[1]
AVATARS = ROOT / "avatars"
SIZE = 512
MAX_BYTES = 500 * 1024

# (文件名, 中心字, 主题色, 强调色, 底部英文标识)
PERSONAS = [
    ("novel-architect-dispatcher", "总", (31, 58, 95), (232, 182, 76), "DISPATCHER"),
    ("novel-plot-architect", "天", (38, 88, 72), (226, 206, 160), "PLOT"),
    ("novel-protocol-sentinel", "宪", (103, 42, 42), (232, 182, 76), "SENTINEL"),
    ("novel-timeline-auditor", "历", (68, 55, 103), (226, 206, 160), "TIMELINE"),
    ("novel-prose-rhetoric", "辞", (88, 68, 42), (226, 206, 160), "PROSE"),
]
TEAM = ("team", "星火", (15, 28, 46), (232, 182, 76), "STARFIRE")


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    """优先微软雅黑，其次黑体；都没有时退回 Pillow 默认位图字体（CI 上不跑生成）。"""
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def _background(tint: tuple[int, int, int], accent: tuple[int, int, int]) -> Image.Image:
    """径向渐变：中心提亮主题色，边缘收黑，避免纯色块的廉价感。"""
    img = Image.new("RGB", (SIZE, SIZE))
    px = img.load()
    cx = cy = SIZE / 2
    max_d = math.hypot(cx, cy)
    for y in range(SIZE):
        for x in range(SIZE):
            d = math.hypot(x - cx, y - cy) / max_d
            k = max(0.0, 1.0 - d) ** 1.7
            px[x, y] = tuple(
                min(255, int(base * (0.34 + 0.66 * k) + hi * 0.12 * k))
                for base, hi in zip(tint, accent)
            )
    return img


def _rings(draw: ImageDraw.ImageDraw, accent: tuple[int, int, int]) -> None:
    """双环 + 24 道刻度：给头像一点「仪表/规章」的工坊气质。"""
    cx = cy = SIZE // 2
    for radius, width, alpha_shift in ((222, 2, 0), (206, 1, -30)):
        color = tuple(max(0, c + alpha_shift) for c in accent)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=color, width=width)
    for i in range(24):
        a = 2 * math.pi * i / 24
        inner = 196 if i % 6 == 0 else 202
        x1, y1 = cx + inner * math.cos(a), cy + inner * math.sin(a)
        x2, y2 = cx + 210 * math.cos(a), cy + 210 * math.sin(a)
        draw.line((x1, y1, x2, y2), fill=accent, width=2 if i % 6 == 0 else 1)


def _center_text(
    draw: ImageDraw.ImageDraw, text: str, accent: tuple[int, int, int]
) -> None:
    """中心汉字/词组，按字数自适应字号并真正居中（bbox 而非固定偏移）。"""
    size = 190 if len(text) == 1 else 104
    font = _font(size)
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((SIZE - w) / 2 - bbox[0], (SIZE - h) / 2 - bbox[1] - 12),
        text,
        font=font,
        fill=accent,
    )


def _footer(draw: ImageDraw.ImageDraw, label: str, accent: tuple[int, int, int]) -> None:
    font = _font(24, bold=False)
    bbox = draw.textbbox((0, 0), label, font=font)
    w = bbox[2] - bbox[0]
    draw.text(((SIZE - w) / 2 - bbox[0], 430), label, font=font, fill=accent)


def render(spec: tuple[str, str, tuple[int, int, int], tuple[int, int, int], str]) -> Image.Image:
    name, glyph, tint, accent, label = spec
    img = _background(tint, accent)
    draw = ImageDraw.Draw(img)
    _rings(draw, accent)
    _center_text(draw, glyph, accent)
    if name == "team":
        # 团队头像多画一排五个小点，对应五个人格
        for i in range(5):
            x = SIZE // 2 + (i - 2) * 34
            draw.ellipse((x - 5, 382, x + 5, 392), fill=accent)
    _footer(draw, label, accent)
    return img


def check() -> int:
    """只读核对：6 张头像都存在、512×512、<500KB。任一不满足返 2。"""
    problems: list[str] = []
    for spec in [*PERSONAS, TEAM]:
        path = AVATARS / f"{spec[0]}.png"
        if not path.is_file():
            problems.append(f"缺失 {path.name}")
            continue
        try:
            with Image.open(path) as img:
                if img.size != (SIZE, SIZE):
                    problems.append(f"{path.name} 尺寸 {img.size}，应为 {(SIZE, SIZE)}")
        except OSError as exc:
            problems.append(f"{path.name} 打不开：{exc}")
        if path.stat().st_size > MAX_BYTES:
            problems.append(f"{path.name} 超过 500KB：{path.stat().st_size}")
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"{len(problems)} 项头像不合规；跑 python tools/gen_avatars.py 重生成。", file=sys.stderr)
        return 2
    print(f"OK: 6 张头像合规（512×512，<500KB）")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成/核对星火小说架构师头像")
    parser.add_argument("--check", action="store_true", help="只核对不写盘")
    args = parser.parse_args(argv)

    if args.check:
        return check()

    AVATARS.mkdir(parents=True, exist_ok=True)
    for spec in [*PERSONAS, TEAM]:
        path = AVATARS / f"{spec[0]}.png"
        render(spec).save(path, format="PNG", optimize=True)
        print(f"WRITE {path.name:<40} {path.stat().st_size:>7} bytes")
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
