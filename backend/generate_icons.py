"""生成 Kivy 界面所需的 PNG 图标。

参考读书软件风格:填充图标,适配深黑背景。
图标尺寸 64x64,填充白色(运行时可由 Kivy 着色)。

运行: python generate_icons.py
输出: backend/assets/icons/*.png
"""

import os
import math
from PIL import Image, ImageDraw

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icons")
os.makedirs(ICON_DIR, exist_ok=True)

SIZE = 128
WHITE = (255, 255, 255, 255)
TRANSPARENT = (0, 0, 0, 0)


def _new_canvas():
    return Image.new("RGBA", (SIZE, SIZE), TRANSPARENT)


def save_icon(name, img):
    path = os.path.join(ICON_DIR, f"{name}.png")
    img.save(path)
    print(f"[icon] saved {path}")


def icon_more():
    """☰ 汉堡菜单:三条横线(线性)。"""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    y_positions = [18, 32, 46]
    for y in y_positions:
        d.line([16, y, 48, y], fill=WHITE, width=3)
    save_icon("more", img)


def icon_email():
    """✉ 信封(填充)。"""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    d.polygon([(8, 16), (56, 16), (56, 40), (32, 52), (8, 40)], fill=WHITE)
    save_icon("email", img)


def icon_book():
    """📖 书本(填充)。"""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    d.polygon([(8, 12), (30, 18), (30, 54), (8, 48)], fill=WHITE)
    d.polygon([(56, 12), (34, 18), (34, 54), (56, 48)], fill=WHITE)
    save_icon("book", img)


def icon_prev():
    """⏮ 上一曲(填充)。"""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    d.polygon([(16, 14), (46, 32), (16, 50)], fill=WHITE)
    d.rectangle([48, 14, 54, 50], fill=WHITE)
    save_icon("prev", img)


def icon_play():
    """▶ 播放(填充)。"""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    d.polygon([(18, 12), (50, 32), (18, 52)], fill=WHITE)
    save_icon("play", img)


def icon_next():
    """⏭ 下一曲(填充)。"""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    d.rectangle([10, 14, 16, 50], fill=WHITE)
    d.polygon([(18, 32), (48, 14), (48, 50)], fill=WHITE)
    save_icon("next", img)


def icon_mic():
    """🎤 麦克风(填充)。"""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([22, 8, 42, 40], radius=10, fill=WHITE)
    d.arc([16, 22, 48, 50], start=0, end=180, fill=WHITE, width=4)
    d.line([32, 50, 32, 56], fill=WHITE, width=4)
    d.line([22, 56, 42, 56], fill=WHITE, width=4)
    save_icon("mic", img)


def icon_chat():
    """💬 对话气泡(填充)。"""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 10, 56, 44], radius=8, fill=WHITE)
    d.polygon([(20, 44), (20, 54), (32, 44)], fill=WHITE)
    save_icon("chat", img)


def icon_tts():
    """🎵 音符(填充)。"""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    d.ellipse([12, 42, 28, 54], fill=WHITE)
    d.line([26, 44, 26, 14], fill=WHITE, width=4)
    d.polygon([(26, 14), (48, 18), (48, 32), (26, 26)], fill=WHITE)
    save_icon("tts", img)


def icon_books():
    """📚 书堆(填充)。"""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    d.rectangle([8, 38, 56, 54], fill=WHITE)
    d.polygon([(12, 34), (52, 28), (54, 38), (14, 44)], fill=WHITE)
    save_icon("books", img)


def icon_home():
    """🏠 首页(填充)。"""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    d.polygon([(32, 10), (8, 34), (56, 34)], fill=WHITE)
    d.rectangle([12, 34, 52, 54], fill=WHITE)
    d.rectangle([26, 42, 38, 54], fill=(26, 26, 26, 255))
    save_icon("home", img)


def icon_toolbox():
    """🛠 工具箱:锤子(填充)。"""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    d.polygon([(14, 14), (42, 14), (32, 32), (24, 32)], fill=WHITE)
    d.line([28, 32, 28, 52], fill=WHITE, width=5)
    save_icon("toolbox", img)


def icon_settings():
    """⚙ 设置:齿轮(填充)。"""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    cx, cy = 32, 32
    teeth = 8
    outer_r = 26
    inner_r = 16
    points = []
    for i in range(teeth * 2):
        angle = i * math.pi / teeth
        r = outer_r if i % 2 == 0 else inner_r
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        points.append((x, y))
    d.polygon(points, fill=WHITE)
    d.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=(26, 26, 26, 255))
    save_icon("settings", img)


def icon_cover():
    """📖 音频封面占位(填充)。"""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    d.polygon([(8, 12), (30, 18), (30, 54), (8, 48)], fill=WHITE)
    d.polygon([(56, 12), (34, 18), (34, 54), (56, 48)], fill=WHITE)
    save_icon("cover", img)


def icon_diary():
    """📔 日记本(填充):笔记本 + 书签飘带。"""
    img = _new_canvas()
    d = ImageDraw.Draw(img)
    # 笔记本主体(圆角)
    d.rounded_rectangle([14, 10, 52, 54], radius=4, fill=WHITE)
    # 装订线(左侧竖线,镂空效果)
    d.line([20, 10, 20, 54], fill=(26, 26, 26, 255), width=2)
    # 书签飘带(从顶部伸出)
    d.polygon([(38, 10), (46, 10), (46, 28), (42, 24), (38, 28)], fill=WHITE)
    # 横线(日记内容,镂空)
    for y in [36, 42, 48]:
        d.line([26, y, 46, y], fill=(26, 26, 26, 255), width=2)
    save_icon("diary", img)


def main():
    print(f"Generating icons to {ICON_DIR}")
    icon_more()
    icon_email()
    icon_book()
    icon_prev()
    icon_play()
    icon_next()
    icon_mic()
    icon_chat()
    icon_tts()
    icon_books()
    icon_home()
    icon_toolbox()
    icon_settings()
    icon_cover()
    icon_diary()
    print("All icons generated.")


if __name__ == "__main__":
    main()
