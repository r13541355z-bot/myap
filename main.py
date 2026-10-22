# -*- coding: utf-8 -*-
"""
دستیار هوشمند جستجو - طراحی مدرن (Kivy)
منطق جستجو (ویکی‌پدیای فارسی) همان نسخه‌ی قبلی است؛ فقط رابط کاربری بازطراحی شده.
برای اتصال به چت‌بات بعداً فقط تابع ask() را عوض کنید.
"""
import ast
import math
import operator
import re
import threading
from urllib.parse import quote

import requests
import arabic_reshaper
from bidi.algorithm import get_display

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import LabelBase, Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex as hexc

# ───────────────────────── تنظیمات ─────────────────────────
APP_TITLE = "دستیار هوشمند"
APP_SUBTITLE = "جستجو در ویکی‌پدیا فارسی"
SOURCE_NAME = "ویکی‌پدیا"

LabelBase.register(name="Vazir", fn_regular="Vazirmatn-Regular.ttf")
FONT = "Vazir"

# پالت رنگ (تیره‌ی مدرن). برای تم دیگر فقط همین‌ها را عوض کنید.
BG = hexc("#0B0D17")
SURFACE = hexc("#141829")
SURFACE_HI = hexc("#1B2036")
BORDER = hexc("#262C4A")
ACCENT = hexc("#7C5CFF")
ACCENT_2 = hexc("#22D3EE")
TEXT = hexc("#EDEFFA")
MUTED = hexc("#8B91B5")
WHITE = (1, 1, 1, 1)
GREEN = hexc("#34D399")
ERR_BG = hexc("#2A1620")
ERR_BORDER = hexc("#5B2A3A")
ERR_TEXT = hexc("#FFB4C0")

HEADERS = {
    "User-Agent": "SearchAppPersian/1.0 (Android search assistant app; contact: myap-project)"
}
WIKI_SEARCH_URL = "https://fa.wikipedia.org/w/api.php"
WIKI_SUMMARY_URL = "https://fa.wikipedia.org/api/rest_v1/page/summary/"

NO_RESULT_MSG = "پاسخی پیدا نشد."
NO_CONNECTION_MSG = "اتصال به اینترنت برقرار نشد. وای‌فای یا دیتای موبایل را بررسی کنید."
TIMEOUT_MSG = "درخواست بیش از حد طول کشید. دوباره تلاش کنید."
EMPTY_RESPONSE_MSG = "پاسخ خالی از سرور دریافت شد. اتصال اینترنت را بررسی کنید."

# ── اتصال به Ollama روی همین گوشی (Termux) ──
OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen2.5:1.5b"    # اگر گوشی قوی است (۸ گیگ+): qwen2.5:3b
OLLAMA_TIMEOUT = 300             # روی گوشی کند است، بار اول لود مدل هم طول می‌کشد
NO_AI_MSG = ("مدل هوش مصنوعی در دسترس نیست. برنامه‌ی Termux را باز کنید و دستور "
             "ollama serve را اجرا کنید، بعد دوباره امتحان کنید.")

MODES = {
    "math": (0.1, "تو معلم ریاضی دقیقی. مسئله را کوتاه و مرحله‌به‌مرحله به فارسی حل کن و "
                  "جواب نهایی را واضح بنویس. اگر «نتیجه‌ی محاسبه‌ی دقیق» داده شد همان را جواب نهایی بدان."),
    "joke": (0.9, "تو طنزپرداز بامزه‌ای. یک جوک کوتاه و تمیز به فارسی بگو."),
    "cook": (0.5, "تو سرآشپز ایرانی باتجربه‌ای. مواد لازم و مراحل پخت را کوتاه و شماره‌دار به فارسی بنویس."),
    "research": (0.3, "تو پژوهشگر دقیقی. با تکیه بر متن مرجع، کوتاه و منظم به فارسی پاسخ بده و چیزی خارج از مرجع را قطعی ادعا نکن."),
    "chat": (0.5, "تو دستیار هوشمند فارسی‌زبانی. روان، کوتاه و دقیق پاسخ بده و اگر نمی‌دانی صادقانه بگو."),
}
KW_JOKE = ("جوک", "شوخی", "بخندون", "لطیفه")
KW_COOK = ("دستور پخت", "طرز تهیه", "آشپزی", "غذا", "پخت", "مواد لازم")
KW_MATH = ("حل کن", "مشتق", "انتگرال", "معادله", "ریاضی", "محاسبه", "ساده کن")
KW_RESEARCH = ("تحقیق", "درباره", "کیست", "چیست", "چه کسی", "تاریخچه", "توضیح بده")

SUGGESTIONS = [
    "حل کن: 2x + 6 = 14",
    "یک جوک بگو",
    "طرز تهیه قورمه‌سبزی",
    "درباره‌ی حافظ شیرازی تحقیق کن",
]

Window.clearcolor = BG
Window.softinput_mode = "below_target"  # کیبورد، نوار ورودی را بالا می‌برد


# ───────────────────────── ابزارهای متن فارسی ─────────────────────────
def shape(text):
    """اتصال حروف + چینش راست‌به‌چپ برای Kivy."""
    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


# ───────────────────────── منطق جستجو (بدون تغییر) ─────────────────────────
def wiki_lookup(query):
    """جستجو در ویکی‌پدیا. خروجی: dict با کلیدهای text, title, error."""
    def fail(msg):
        return {"text": msg, "title": None, "error": True}

    try:
        search_params = {
            "action": "opensearch",
            "search": query,
            "limit": 1,
            "namespace": 0,
            "format": "json",
        }
        r = requests.get(WIKI_SEARCH_URL, params=search_params, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return fail("خطای سرور (" + str(r.status_code) + ")")
        if not r.text.strip():
            return fail(EMPTY_RESPONSE_MSG)

        data = r.json()
        titles = data[1] if len(data) > 1 else []
        if not titles:
            return fail(NO_RESULT_MSG)
        title = titles[0]

        r2 = requests.get(
            WIKI_SUMMARY_URL + quote(title.replace(" ", "_"), safe=""),
            headers=HEADERS,
            timeout=15,
        )
        if r2.status_code != 200:
            return fail("خطای سرور در دریافت خلاصه (" + str(r2.status_code) + ")")
        if not r2.text.strip():
            return fail(EMPTY_RESPONSE_MSG)

        extract = (r2.json().get("extract") or "").strip()
        if not extract:
            return fail(NO_RESULT_MSG)
        return {"text": extract, "title": title, "error": False}

    except requests.exceptions.ConnectionError:
        return fail(NO_CONNECTION_MSG)
    except requests.exceptions.Timeout:
        return fail(TIMEOUT_MSG)
    except ValueError:
        return fail(EMPTY_RESPONSE_MSG)
    except Exception as e:
        return fail("خطا: " + str(e))


# ── محاسبه‌ی دقیق عبارت‌های عددی ساده (بدون eval، فقط ast) ──
_FA = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg}


def _ev(n):
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return n.value
    if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
        l, r = _ev(n.left), _ev(n.right)
        if isinstance(n.op, ast.Pow) and abs(r) > 100:
            raise ValueError("pow")
        return _OPS[type(n.op)](l, r)
    if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
        return _OPS[type(n.op)](_ev(n.operand))
    raise ValueError("bad")


def safe_calc(text):
    t = text.translate(_FA).replace("×", "*").replace("÷", "/").replace("^", "**")
    found = re.findall(r"[0-9+\-*/().\s]{3,}", t)
    if not found:
        return None
    expr = max(found, key=len).strip()
    if len(expr) > 60 or not re.search(r"\d\s*(?:\*\*|[+\-*/])\s*\(?\d", expr):
        return None
    if re.fullmatch(r"\d{1,4}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*\d{1,4}", expr):
        return None  # تاریخ
    try:
        v = _ev(ast.parse(expr, mode="eval").body)
        return str(int(v)) if float(v).is_integer() else str(round(v, 8))
    except Exception:
        return None


def detect_mode(msg):
    if any(k in msg for k in KW_JOKE):
        return "joke"
    if any(k in msg for k in KW_COOK):
        return "cook"
    if any(k in msg for k in KW_MATH) or safe_calc(msg) is not None:
        return "math"
    if any(k in msg for k in KW_RESEARCH):
        return "research"
    return "chat"


def ask_ollama(system, user, temperature):
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "options": {"temperature": temperature},
    }
    r = requests.post(OLLAMA_URL + "/api/chat", json=payload, timeout=OLLAMA_TIMEOUT)
    r.raise_for_status()
    return (r.json().get("message", {}).get("content") or "").strip()


def ask(query):
    """تشخیص نوع سؤال -> (ویکی‌پدیا/محاسبه) -> مدل روی خود گوشی."""
    mode = detect_mode(query)
    temperature, system = MODES[mode]
    user, title, wiki = query, None, None

    if mode == "math":
        exact = safe_calc(query)
        if exact is not None:
            user = query + "\n\nنتیجه‌ی محاسبه‌ی دقیق: " + exact
    elif mode == "research":
        wiki = wiki_lookup(query)
        if not wiki["error"]:
            title = wiki["title"]
            user = "متن مرجع (ویکی‌پدیا):\n" + wiki["text"] + "\n\nسؤال: " + query

    try:
        answer = ask_ollama(system, user, temperature)
        if answer:
            return {"text": answer, "title": title, "error": False}
        raise ValueError("empty")
    except requests.exceptions.Timeout:
        return {"text": TIMEOUT_MSG, "title": None, "error": True}
    except Exception:
        if wiki and not wiki["error"]:  # پشتیبان: خود متن ویکی‌پدیا
            return wiki
        return {"text": NO_AI_MSG, "title": None, "error": True}


# ───────────────────────── ویجت‌های پایه ─────────────────────────
class Card(BoxLayout):
    """جعبه‌ی گوشه‌گرد با حاشیه‌ی ظریف."""

    def __init__(self, bg=SURFACE, border=None, radius=16, **kwargs):
        super().__init__(**kwargs)
        self.bg = bg
        self.border = border or bg
        r = [dp(radius)]
        with self.canvas.before:
            self._border_c = Color(*self.border)
            self._border_r = RoundedRectangle(pos=self.pos, size=self.size, radius=r)
            self._bg_c = Color(*self.bg)
            self._bg_r = RoundedRectangle(pos=self.pos, size=self.size, radius=r)
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *_):
        self._border_r.pos = self.pos
        self._border_r.size = self.size
        self._bg_r.pos = (self.x + dp(1), self.y + dp(1))
        self._bg_r.size = (max(0, self.width - dp(2)), max(0, self.height - dp(2)))

    def set_bg(self, rgba):
        self._bg_c.rgba = rgba


class TapCard(ButtonBehavior, Card):
    """کارت قابل لمس با افکت فشردن."""

    def on_press(self):
        r, g, b, a = self.bg
        self.set_bg((min(1, r + 0.07), min(1, g + 0.07), min(1, b + 0.07), a))

    def on_release(self):
        self.set_bg(self.bg)


class SLabel(Label):
    """برچسب تک‌خطی فارسی (خودکار shape می‌شود)."""

    def __init__(self, raw="", **kwargs):
        kwargs.setdefault("font_name", FONT)
        kwargs.setdefault("halign", "right")
        kwargs.setdefault("valign", "middle")
        kwargs.setdefault("color", TEXT)
        super().__init__(**kwargs)
        self.bind(size=lambda *_: setattr(self, "text_size", self.size))
        self.text = shape(raw)


class Dot(Widget):
    def __init__(self, color, **kwargs):
        super().__init__(**kwargs)
        with self.canvas:
            Color(*color)
            self._e = Ellipse(pos=self.pos, size=self.size)
        self.bind(pos=self._u, size=self._u)

    def _u(self, *_):
        self._e.pos, self._e.size = self.pos, self.size


class SendButton(TapCard):
    """دکمه‌ی گردِ ارسال با فلش رسم‌شده (بدون نیاز به فونت/آیکن)."""

    def __init__(self, **kwargs):
        super().__init__(bg=ACCENT, border=ACCENT, radius=22, **kwargs)
        with self.canvas.after:
            Color(*WHITE)
            self._shaft = Line(width=dp(1.8), cap="round")
            self._head = Line(width=dp(1.8), cap="round", joint="round")
        self.bind(pos=self._arrow, size=self._arrow)

    def _arrow(self, *_):
        cx, cy = self.center
        s = min(self.width, self.height) * 0.22
        self._shaft.points = [cx, cy - s, cx, cy + s]
        self._head.points = [cx - s * 0.85, cy + s * 0.1, cx, cy + s * 1.05, cx + s * 0.85, cy + s * 0.1]


class ChatLabel(Label):
    """
    متن چندخطی فارسی با شکستن خط دستی (هر خط جداگانه shape می‌شود)،
    تا ترتیب خط‌ها و کلمات در متن‌های بلند درست بماند. پشتیبان افکت تایپ.
    """

    def __init__(self, color=TEXT, font_px=None, **kwargs):
        self._font_px = font_px or sp(15.5)
        super().__init__(
            font_name=FONT,
            font_size=self._font_px,
            color=color,
            halign="right",
            valign="top",
            size_hint=(None, None),
            line_height=1.45,
            **kwargs,
        )
        self._core = CoreLabel(font_name=FONT, font_size=self._font_px)
        self.lines = []
        self.shaped = []

    def _w(self, s):
        return self._core.get_extents(s)[0]

    def set_text(self, raw, max_w, show=True):
        lines = []
        for para in raw.split("\n"):
            words = para.split()
            if not words:
                lines.append("")
                continue
            cur = ""
            for w in words:
                trial = w if not cur else cur + " " + w
                if not cur or self._w(shape(trial)) <= max_w:
                    cur = trial
                else:
                    lines.append(cur)
                    cur = w
            lines.append(cur)
        self.lines = lines
        self.shaped = [shape(l) for l in lines]

        self.text_size = (None, None)
        self.text = "\n".join(self.shaped)
        self.texture_update()
        w, h = self.texture_size
        self.size = (w + dp(2), h)
        self.text_size = self.size
        if not show:
            self.text = ""

    def total_chars(self):
        return sum(len(l) for l in self.lines)

    def reveal(self, n):
        out, remaining = [], n
        for l, s in zip(self.lines, self.shaped):
            if remaining <= 0:
                break
            if remaining >= len(l):
                out.append(s)
                remaining -= len(l)
            else:
                out.append(shape(l[:remaining]))
                remaining = 0
        self.text = "\n".join(out)


class TypingBubble(Card):
    """حباب «در حال نوشتن» با سه نقطه‌ی متحرک."""

    def __init__(self, **kwargs):
        super().__init__(
            bg=SURFACE, border=BORDER, radius=18,
            size_hint=(None, None), size=(dp(70), dp(40)), **kwargs
        )
        self._t = 0.0
        self._colors, self._dots = [], []
        with self.canvas.after:
            for _ in range(3):
                self._colors.append(Color(*ACCENT_2[:3], 0.4))
                self._dots.append(Ellipse(size=(dp(8), dp(8))))
        self.bind(pos=self._place, size=self._place)
        self._ev = Clock.schedule_interval(self._tick, 1 / 30.0)

    def _place(self, *_):
        for i, e in enumerate(self._dots):
            e.pos = (self.center_x + (i - 1) * dp(15) - dp(4), self.center_y - dp(4))

    def _tick(self, dt):
        self._t += dt
        for i, c in enumerate(self._colors):
            c.a = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(self._t * 6.5 - i * 0.9))

    def stop(self):
        self._ev.cancel()


# ───────────────────────── خود برنامه ─────────────────────────
class SearchApp(App):
    title = APP_TITLE

    # ---------- ساخت رابط ----------
    def build(self):
        self.busy = False
        self.welcome = None
        self.typing = None

        root = BoxLayout(orientation="vertical")

        # هدر
        header = BoxLayout(
            size_hint_y=None, height=dp(72),
            padding=[dp(16), dp(10)], spacing=dp(12),
        )
        pill = Card(
            bg=SURFACE, border=BORDER, radius=15,
            size_hint=(None, None), size=(dp(104), dp(30)),
            padding=[dp(11), 0], spacing=dp(7),
            pos_hint={"center_y": 0.5},
        )
        pill.add_widget(Dot(GREEN, size_hint=(None, None), size=(dp(8), dp(8)), pos_hint={"center_y": 0.5}))
        pill.add_widget(SLabel(SOURCE_NAME, font_size=sp(12), color=MUTED))
        header.add_widget(pill)
        header.add_widget(Widget())

        titles = BoxLayout(orientation="vertical", size_hint_x=None, width=dp(190), spacing=dp(1))
        titles.add_widget(SLabel(APP_TITLE, font_size=sp(17)))
        titles.add_widget(SLabel(APP_SUBTITLE, font_size=sp(11.5), color=MUTED))
        header.add_widget(titles)

        logo = Card(
            bg=ACCENT, border=ACCENT, radius=14,
            size_hint=(None, None), size=(dp(44), dp(44)),
            pos_hint={"center_y": 0.5},
        )
        logo.add_widget(Label(text="AI", font_name=FONT, font_size=sp(15), color=WHITE))
        header.add_widget(logo)
        root.add_widget(header)

        # خط جداکننده
        divider = Widget(size_hint_y=None, height=dp(1))
        with divider.canvas:
            Color(*BORDER)
            rect = Rectangle(pos=divider.pos, size=divider.size)
        divider.bind(
            pos=lambda w, v: setattr(rect, "pos", v),
            size=lambda w, v: setattr(rect, "size", v),
        )
        root.add_widget(divider)

        # ناحیه‌ی گفتگو
        self.scroll = ScrollView(
            do_scroll_x=False, bar_width=dp(3),
            bar_color=(*ACCENT[:3], 0.45), bar_inactive_color=(*ACCENT[:3], 0.0),
        )
        self.chat = BoxLayout(
            orientation="vertical", size_hint_y=None,
            padding=[dp(14), dp(16)], spacing=dp(10),
        )
        self.chat.bind(minimum_height=self.chat.setter("height"))
        self.scroll.add_widget(self.chat)
        root.add_widget(self.scroll)

        # نوار ورودی
        bar = BoxLayout(size_hint_y=None, height=dp(78), padding=[dp(12), dp(10)])
        field = Card(
            bg=SURFACE, border=BORDER, radius=28,
            padding=[dp(8), dp(6), dp(16), dp(6)], spacing=dp(8),
        )
        self.send_btn = SendButton(size_hint=(None, None), size=(dp(44), dp(44)), pos_hint={"center_y": 0.5})
        self.send_btn.bind(on_release=lambda *_: self.on_submit())
        self.input = TextInput(
            hint_text=shape("هر چیزی بپرسید…"),
            hint_text_color=MUTED,
            foreground_color=TEXT,
            cursor_color=ACCENT_2,
            background_normal="", background_active="",
            background_color=(0, 0, 0, 0),
            font_name=FONT, font_size=sp(15.5),
            multiline=False, write_tab=False,
            base_direction="rtl", halign="right",
            padding=[dp(4), dp(10), dp(4), dp(10)],
        )
        self.input.bind(
            height=lambda w, h: setattr(w, "padding_y", [max(0, (h - w.line_height) / 2)] * 2)
        )
        self.input.bind(on_text_validate=lambda *_: self.on_submit())
        field.add_widget(self.send_btn)
        field.add_widget(self.input)
        bar.add_widget(field)
        root.add_widget(bar)

        self._show_welcome()
        return root

    # ---------- صفحه‌ی خوش‌آمد ----------
    def _show_welcome(self):
        w = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(10), padding=[0, dp(10)])
        w.bind(minimum_height=w.setter("height"))

        logo_row = BoxLayout(size_hint_y=None, height=dp(72))
        logo_row.add_widget(Widget())
        big = Card(bg=ACCENT, border=ACCENT_2, radius=22, size_hint=(None, None), size=(dp(72), dp(72)))
        big.add_widget(Label(text="AI", font_name=FONT, font_size=sp(24), color=WHITE))
        logo_row.add_widget(big)
        logo_row.add_widget(Widget())
        w.add_widget(logo_row)

        w.add_widget(SLabel("سلام! چه می‌خواهید بدانید؟", font_size=sp(21),
                            halign="center", size_hint_y=None, height=dp(44)))
        w.add_widget(SLabel("پاسخ سؤال‌هایتان را از", font_size=sp(13), color=MUTED,
                            halign="center", size_hint_y=None, height=dp(20)))
        w.add_widget(SLabel("ویکی‌پدیای فارسی پیدا می‌کنم", font_size=sp(13), color=MUTED,
                            halign="center", size_hint_y=None, height=dp(20)))
        w.add_widget(Widget(size_hint_y=None, height=dp(10)))
        w.add_widget(SLabel("پیشنهادها", font_size=sp(12), color=MUTED, size_hint_y=None, height=dp(22)))

        for s in SUGGESTIONS:
            chip = TapCard(
                bg=SURFACE, border=BORDER, radius=16,
                size_hint_y=None, height=dp(52), padding=[dp(16), 0],
            )
            chip.add_widget(SLabel(s, font_size=sp(15)))
            chip.bind(on_release=lambda _w, q=s: self.on_submit(q))
            w.add_widget(chip)

        self.welcome = w
        self.chat.add_widget(w)

    # ---------- حباب‌ها ----------
    def _style(self, kind):
        return {
            "user": dict(bg=ACCENT, border=ACCENT, color=WHITE, px=sp(15.5), pad=(14, 10)),
            "bot": dict(bg=SURFACE, border=BORDER, color=TEXT, px=sp(15.5), pad=(14, 11)),
            "error": dict(bg=ERR_BG, border=ERR_BORDER, color=ERR_TEXT, px=sp(15), pad=(14, 10)),
            "source": dict(bg=BG, border=BORDER, color=MUTED, px=sp(12), pad=(12, 6)),
        }[kind]

    def _bubble(self, raw, kind, animate=False):
        st = self._style(kind)
        padx, pady = dp(st["pad"][0]), dp(st["pad"][1])
        max_inner = Window.width * 0.84 - 2 * padx
        lbl = ChatLabel(color=st["color"], font_px=st["px"])
        lbl.set_text(raw, max_inner, show=not animate)
        bub = Card(
            bg=st["bg"], border=st["border"], radius=18 if kind != "source" else 12,
            size_hint=(None, None), padding=[padx, pady],
            size=(lbl.width + 2 * padx, lbl.height + 2 * pady),
        )
        bub.add_widget(lbl)
        bub.label = lbl
        return bub

    def _row(self, widget, side):
        """side='right' برای کاربر، 'left' برای دستیار (چینش فارسی)."""
        row = BoxLayout(size_hint_y=None, height=widget.height)
        widget.bind(height=lambda _w, h: setattr(row, "height", h))
        if side == "right":
            row.add_widget(Widget())
            row.add_widget(widget)
        else:
            row.add_widget(widget)
            row.add_widget(Widget())
        self.chat.add_widget(row)
        self._scroll_bottom()
        return row

    def _scroll_bottom(self):
        Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", 0), 0.05)

    # ---------- جریان گفتگو ----------
    def on_submit(self, preset=None):
        query = (preset if isinstance(preset, str) else self.input.text).strip()
        if not query or self.busy:
            return
        self.busy = True
        self.input.text = ""
        self.send_btn.opacity = 0.5

        if self.welcome is not None:
            self.chat.remove_widget(self.welcome)
            self.welcome = None

        self._row(self._bubble(query, "user"), "right")

        self.typing = TypingBubble()
        self.typing_row = self._row(self.typing, "left")

        threading.Thread(target=self._run_query, args=(query,), daemon=True).start()
        Clock.schedule_once(lambda dt: setattr(self.input, "focus", True), 0.1)

    def _run_query(self, query):
        result = ask(query)
        Clock.schedule_once(lambda dt: self._show_answer(result), 0)

    def _show_answer(self, res):
        if self.typing is not None:
            self.typing.stop()
            self.chat.remove_widget(self.typing_row)
            self.typing = None

        kind = "error" if res["error"] else "bot"
        bub = self._bubble(res["text"], kind, animate=not res["error"])
        self._row(bub, "left")

        def done():
            self.busy = False
            self.send_btn.opacity = 1
            if res.get("title"):
                short = res["title"] if len(res["title"]) <= 30 else res["title"][:29] + "…"
                self._row(self._bubble("منبع: %s · %s" % (SOURCE_NAME, short), "source"), "left")
            self._scroll_bottom()

        if res["error"]:
            done()
            return

        lbl, total = bub.label, bub.label.total_chars()
        step = max(3, total // 90)
        state = {"n": 0}

        def tick(dt):
            state["n"] += step
            lbl.reveal(state["n"])
            self._scroll_bottom()
            if state["n"] >= total:
                lbl.reveal(total)
                done()
                return False

        Clock.schedule_interval(tick, 0.02)


if __name__ == "__main__":
    SearchApp().run()
