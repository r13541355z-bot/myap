# -*- coding: utf-8 -*-
"""
دستیار هوشمند فارسی - نسخه‌ی پیشرفته (Kivy)
------------------------------------------------
- مدل هوش مصنوعی روی خود گوشی (Ollama در Termux)
- پاسخ‌های فوری بدون مدل: حساب/معادله (دقیق)، سلام، جوک
- گرم‌کردن مدل هنگام باز شدن برنامه (جواب اول سریع‌تر)
- جواب زنده (stream)، دکمه‌ی توقف، گفتگوی جدید، حافظه‌ی گفتگو
- تحقیق با منبع از ویکی‌پدیای فارسی، کش پاسخ‌ها
"""
import ast
import json
import math
import random
import re
import threading
import time
from collections import OrderedDict
from fractions import Fraction
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

# ═════════════════════════ تنظیمات ═════════════════════════
APP_TITLE = "دستیار هوشمند"
APP_SUBTITLE = "هوش مصنوعی روی گوشی"
SOURCE_NAME = "ویکی‌پدیا"

LabelBase.register(name="Vazir", fn_regular="Vazirmatn-Regular.ttf")
FONT = "Vazir"

# --- مدل (Ollama روی همین گوشی) ---
OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen3:4b-instruct-2507-q4_K_M"   # سریع‌تر: qwen3:1.7b | قوی‌تر (کندتر): qwen3:8b
OLLAMA_TIMEOUT = 300
CONTEXT_SIZE = 3072                  # کوچک‌تر = سریع‌تر
KEEP_ALIVE = "30m"                   # مدل تا ۳۰ دقیقه در حافظه می‌ماند
WIKI_CONTEXT_CHARS = 700
HISTORY_MESSAGES = 6                 # تعداد پیام‌های قبلیِ یادآوری‌شده
MODE_TOKENS = {"math": 300, "joke": 150, "cook": 420, "research": 260, "chat": 340}

HEADERS = {"User-Agent": "SearchAppPersian/1.0 (student project)"}
WIKI_SEARCH_URL = "https://fa.wikipedia.org/w/api.php"
WIKI_SUMMARY_URL = "https://fa.wikipedia.org/api/rest_v1/page/summary/"

NO_RESULT_MSG = "پاسخی پیدا نشد."
NO_CONNECTION_MSG = "اتصال به اینترنت برقرار نشد."
TIMEOUT_MSG = "درخواست بیش از حد طول کشید. دوباره تلاش کنید."
NO_AI_MSG = ("مدل هوش مصنوعی در دسترس نیست. Termux را باز کنید، دستور "
             "ollama serve > /dev/null 2>&1 & را بزنید و دوباره امتحان کنید.")

# --- رنگ‌ها ---
BG = hexc("#0B0D17")
SURFACE = hexc("#141829")
BORDER = hexc("#262C4A")
ACCENT = hexc("#7C5CFF")
ACCENT_2 = hexc("#22D3EE")
TEXT = hexc("#EDEFFA")
MUTED = hexc("#8B91B5")
WHITE = (1, 1, 1, 1)
GREEN = hexc("#34D399")
ORANGE = hexc("#F59E0B")
RED = hexc("#F87171")
ERR_BG = hexc("#2A1620")
ERR_BORDER = hexc("#5B2A3A")
ERR_TEXT = hexc("#FFB4C0")

SUGGESTIONS = [
    "حل کن: 2x + 6 = 14",
    "x^2 - 5x + 6 = 0",
    "برای امروز یک برنامه‌ی مفید پیشنهاد بده",
    "درباره‌ی حافظ شیرازی تحقیق کن",
]

Window.clearcolor = BG
Window.softinput_mode = "below_target"

# ═════════════════════════ متن فارسی ═════════════════════════
def shape(text):
    try:
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


# ═════════════════════════ دستورِ مدل (پرامپت‌ها) ═════════════════════════
RULES = (
    " قوانین: فقط به فارسی ساده و روان بنویس. مستقیم به سؤال جواب بده و حرف بی‌ربط یا شعار نساز. "
    "جمله‌ها کامل و منطقی باشند. اگر مطمئن نیستی، صادقانه بگو نمی‌دانم و چیزی اختراع نکن. "
    "اگر سؤال مبهم است، یک سؤال کوتاه برای روشن شدنش بپرس."
)
MODES = {
    "math": (0.1, "تو معلم ریاضی دقیقی. مسئله را کوتاه و مرحله‌به‌مرحله حل کن و جواب نهایی را "
                  "واضح بنویس. اگر «نتیجه‌ی محاسبه‌ی دقیق» داده شد همان را جواب نهایی بدان." + RULES),
    "joke": (0.9, "تو طنزپرداز بامزه‌ای. یک جوک کوتاه و تمیز بگو." + RULES),
    "cook": (0.4, "تو سرآشپز ایرانی باتجربه‌ای. مواد لازم و مراحل پخت را کوتاه و شماره‌دار بنویس." + RULES),
    "research": (0.2, "تو پژوهشگر دقیقی. فقط بر پایه‌ی متن مرجع پاسخ بده و چیزی خارج از مرجع را "
                      "قطعی ادعا نکن." + RULES),
    "chat": (0.3, "تو دستیار هوشمند و عملی هستی. وقتی کاربر راهنمایی می‌خواهد (مثلاً برنامه‌ی روز)، "
                  "۳ تا ۵ پیشنهاد مشخص، کاربردی و قابل‌انجام بده، نه جمله‌های کلی." + RULES),
}
KW_JOKE = ("جوک", "شوخی", "بخندون", "لطیفه")
KW_COOK = ("دستور پخت", "طرز تهیه", "آشپزی", "غذا", "پخت", "مواد لازم")
KW_MATH = ("حل کن", "مشتق", "انتگرال", "معادله", "ریاضی", "محاسبه", "ساده کن", "حساب کن")
KW_RESEARCH = ("تحقیق", "درباره", "کیست", "چیست", "چه کسی", "تاریخچه", "توضیح بده",
               "کجاست", "چه زمانی", "چه سالی", "پایتخت", "جستجو")

JOKES = [
    "از دانش‌آموزی پرسیدند: چرا دیر آمدی؟ گفت: چون تابلوی «مدرسه، آهسته‌تر برانید» را دیدم!",
    "مریض به دکتر گفت: هر وقت چای می‌خورم چشمم درد می‌گیرد. دکتر گفت: قاشق را از لیوان بیرون بیاور!",
    "معلم: اگر پنج گوسفند داشته باشی و یکی از نرده بپرد، چند تا می‌ماند؟ شاگرد: هیچ‌کدام آقا! گوسفندها همیشه دنبال هم می‌پرند!",
    "پسر به پدرش گفت: بابا، توی امتحان ریاضی ۲۰ شدم! پدر گفت: آفرین! پسر گفت: البته از ۱۰۰.",
    "به مرد گفتند: چرا ساعتت را ده دقیقه جلو گذاشته‌ای؟ گفت: تا همیشه ده دقیقه از زندگی جلو باشم!",
    "یک نفر به دوستش گفت: من فردا از فردا شروع به ورزش می‌کنم. دوستش گفت: یعنی پس‌فردا؟ گفت: نه، فردا از فردا!",
]
GREETINGS = {"سلام", "درود", "hi", "hello", "hey", "های", "سلام علیکم", "سلام خوبی"}
THANKS = {"ممنون", "مرسی", "متشکرم", "تشکر", "ممنونم", "دمت گرم"}

_last_joke = [-1]


# ═════════════════════════ موتور ریاضی دقیق (بدون eval) ═════════════════════════
_FA = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫", "01234567890123456789.")


def _ev(n, x=None):
    """ارزیابی امن عبارت با اعداد کسری (دقیق)."""
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
        return Fraction(str(n.value))
    if isinstance(n, ast.Name) and n.id in ("x", "X"):
        if x is None:
            raise ValueError("var")
        return x
    if isinstance(n, ast.UnaryOp):
        v = _ev(n.operand, x)
        if isinstance(n.op, ast.USub):
            return -v
        if isinstance(n.op, ast.UAdd):
            return v
    if isinstance(n, ast.BinOp):
        l, r = _ev(n.left, x), _ev(n.right, x)
        if isinstance(n.op, ast.Add):
            return l + r
        if isinstance(n.op, ast.Sub):
            return l - r
        if isinstance(n.op, ast.Mult):
            return l * r
        if isinstance(n.op, ast.Div):
            return l / r
        if isinstance(n.op, ast.Pow):
            if r.denominator != 1 or abs(r) > 50:
                raise ValueError("pow")
            return l ** int(r)
    raise ValueError("bad")


def _norm(e):
    e = e.replace("^", "**")
    e = re.sub(r"(\d|\))\s*([xX(])", r"\1*\2", e)   # 2x  2(  )x  )(
    e = re.sub(r"([xX])\s*(\d|\()", r"\1*\2", e)     # x(  x2
    return e


def _fmt(fr):
    if fr.denominator == 1:
        return str(fr.numerator)
    return "%d/%d (≈ %s)" % (fr.numerator, fr.denominator, ("%.6g" % float(fr)))


def _solve(left, right):
    L = ast.parse(_norm(left), mode="eval").body
    R = ast.parse(_norm(right), mode="eval").body

    def f(x):
        return _ev(L, x) - _ev(R, x)

    f0, f1, fm = f(Fraction(0)), f(Fraction(1)), f(Fraction(-1))
    a, b, c = (f1 + fm) / 2 - f0, (f1 - fm) / 2, f0
    for t in (Fraction(2), Fraction(3), Fraction(1, 2)):
        if f(t) != a * t * t + b * t + c:
            return None                       # بالاتر از درجه ۲؛ به مدل بسپار
    if a == 0:
        if b == 0:
            return "به‌ازای هر x برقرار است" if c == 0 else "جواب ندارد"
        return "x = " + _fmt(-c / b)
    D = b * b - 4 * a * c
    if D < 0:
        return "ریشه‌ی حقیقی ندارد"
    sn, sd = math.isqrt(D.numerator), math.isqrt(D.denominator)
    if sn * sn == D.numerator and sd * sd == D.denominator:
        s = Fraction(sn, sd)
        r1, r2 = (-b + s) / (2 * a), (-b - s) / (2 * a)
        if r1 == r2:
            return "x = " + _fmt(r1)
        lo, hi = sorted((r1, r2))
        return "x = %s  یا  x = %s" % (_fmt(lo), _fmt(hi))
    sq = math.sqrt(float(D))
    r1, r2 = (-float(b) + sq) / (2 * float(a)), (-float(b) - sq) / (2 * float(a))
    lo, hi = sorted((r1, r2))
    return "x ≈ %.6g  یا  x ≈ %.6g" % (lo, hi)


def safe_math(text):
    """اگر در متن عبارت عددی یا معادله‌ی ساده باشد حلش می‌کند. خروجی: dict یا None."""
    t = text.translate(_FA).replace("×", "*").replace("÷", "/").replace("−", "-")
    found = re.findall(r"[0-9xX+\-*/^().=\s]{3,}", t)
    if not found:
        return None
    expr = max(found, key=len).strip()
    if len(expr) > 80 or not re.search(r"\d", expr) or not re.search(r"[+\-*/^=]", expr):
        return None
    if re.fullmatch(r"\d{1,4}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*\d{1,4}", expr):
        return None                          # تاریخ
    if re.search(r"\^[^+\-*/=]*\^", expr) or re.search(r"\^\s*\(?\d{3,}", expr) or "**" in expr:
        return None                          # توان‌های خطرناک
    try:
        has_x = bool(re.search(r"[xX]", expr))
        if "=" in expr:
            if expr.count("=") != 1:
                return None
            left, right = [p.strip() for p in expr.split("=")]
            if not left:
                return None
            if has_x:
                if not right:
                    return None
                ans = _solve(left, right)
                if ans is None:
                    return None
            else:
                if right:
                    return None
                ans = _fmt(_ev(ast.parse(_norm(left), mode="eval").body))
        else:
            if has_x:
                return None
            ans = _fmt(_ev(ast.parse(_norm(expr), mode="eval").body))
    except Exception:
        return None
    rest = re.sub(r"[^A-Za-z\u0600-\u06FF]", "", t.replace(expr, " "))
    return {"expr": expr, "answer": ans, "pure": len(rest) <= 14}


# ═════════════════════════ ویکی‌پدیا + کش ═════════════════════════
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
CACHE = OrderedDict()


def wiki_lookup(query):
    def fail(msg):
        return {"text": msg, "title": None, "error": True}
    try:
        r = SESSION.get(WIKI_SEARCH_URL, params={
            "action": "opensearch", "search": query, "limit": 1,
            "namespace": 0, "format": "json"}, timeout=8)
        if r.status_code != 200 or not r.text.strip():
            return fail(NO_RESULT_MSG)
        titles = r.json()[1] if len(r.json()) > 1 else []
        if not titles:
            return fail(NO_RESULT_MSG)
        title = titles[0]
        r2 = SESSION.get(WIKI_SUMMARY_URL + quote(title.replace(" ", "_"), safe=""), timeout=8)
        if r2.status_code != 200 or not r2.text.strip():
            return fail(NO_RESULT_MSG)
        extract = (r2.json().get("extract") or "").strip()
        if not extract:
            return fail(NO_RESULT_MSG)
        return {"text": extract, "title": title, "error": False}
    except requests.exceptions.ConnectionError:
        return fail(NO_CONNECTION_MSG)
    except requests.exceptions.Timeout:
        return fail(TIMEOUT_MSG)
    except Exception:
        return fail(NO_RESULT_MSG)


# ═════════════════════════ مغز: مسیریابی و مدل ═════════════════════════
def strip_think(t):
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.S)
    if "<think>" in t:
        t = t.split("<think>")[0]
    return t.strip()


def ask_ollama(system, user, temperature, max_tokens, push=None, history=None, cancel=None):
    messages = [{"role": "system", "content": system}]
    messages += list(history or [])
    messages.append({"role": "user", "content": user})
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
        "keep_alive": KEEP_ALIVE,
        "options": {"temperature": temperature, "top_p": 0.8, "repeat_penalty": 1.1,
                    "num_predict": max_tokens, "num_ctx": CONTEXT_SIZE},
    }
    if "qwen3" in OLLAMA_MODEL and "instruct" not in OLLAMA_MODEL:
        payload["think"] = False
    acc = ""
    with requests.post(OLLAMA_URL + "/api/chat", json=payload, stream=True,
                       timeout=(10, OLLAMA_TIMEOUT)) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if cancel is not None and cancel.is_set():
                break
            if not line:
                continue
            d = json.loads(line)
            acc += d.get("message", {}).get("content", "")
            shown = strip_think(acc)
            if push and shown:
                push(shown)
            if d.get("done"):
                break
    return strip_think(acc)


def detect_mode(msg):
    if any(k in msg for k in KW_JOKE):
        return "joke"
    if any(k in msg for k in KW_COOK):
        return "cook"
    if any(k in msg for k in KW_MATH) or safe_math(msg) is not None:
        return "math"
    if any(k in msg for k in KW_RESEARCH):
        return "research"
    return "chat"


def instant_reply(q):
    n = re.sub(r"[^\w\s]", "", q.lower()).strip()
    if n in GREETINGS:
        return "سلام! چطور می‌توانم کمکت کنم؟"
    if n in THANKS:
        return "خواهش می‌کنم! سؤال دیگری هست؟"
    return None


def pick_joke():
    i = random.randrange(len(JOKES))
    if i == _last_joke[0]:
        i = (i + 1) % len(JOKES)
    _last_joke[0] = i
    return JOKES[i]


def ask(query, push=None, history=None, cancel=None):
    """سریع‌ترین مسیر ممکن: فوری (بدون مدل) -> کش -> مدل."""
    q = query.strip()
    ok = lambda text, title=None: {"text": text, "title": title, "error": False}

    inst = instant_reply(q)
    if inst:
        return ok(inst)

    mode = detect_mode(q)
    if mode == "joke" and len(q) <= 30:
        return ok(pick_joke())

    math_res = None
    if mode == "math":
        math_res = safe_math(q)
        if math_res and math_res["pure"]:
            return ok("پاسخ دقیق: " + math_res["answer"])

    key = (mode, q)
    if mode in ("research", "cook") and key in CACHE:
        CACHE.move_to_end(key)
        return CACHE[key]

    temperature, system = MODES[mode]
    user, title, wiki = q, None, None
    if mode == "math" and math_res:
        user = q + "\n\nنتیجه‌ی محاسبه‌ی دقیق: " + math_res["answer"]
    elif mode == "research":
        wiki = wiki_lookup(q)
        if not wiki["error"]:
            title = wiki["title"]
            ctx = wiki["text"]
            if len(ctx) > WIKI_CONTEXT_CHARS:
                ctx = ctx[:WIKI_CONTEXT_CHARS].rsplit(" ", 1)[0] + "…"
            user = "متن مرجع (ویکی‌پدیا):\n" + ctx + "\n\nسؤال: " + q

    try:
        answer = ask_ollama(system, user, temperature, MODE_TOKENS[mode], push, history, cancel)
        if answer:
            res = ok(answer, title)
            if mode in ("research", "cook") and not (cancel is not None and cancel.is_set()):
                CACHE[key] = res
                while len(CACHE) > 40:
                    CACHE.popitem(last=False)
            return res
        raise ValueError("empty")
    except requests.exceptions.Timeout:
        return {"text": TIMEOUT_MSG, "title": None, "error": True}
    except Exception:
        if wiki and not wiki["error"]:
            return wiki
        return {"text": NO_AI_MSG, "title": None, "error": True}


# ═════════════════════════ ویجت‌ها ═════════════════════════
class Card(BoxLayout):
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
        self._border_r.pos, self._border_r.size = self.pos, self.size
        self._bg_r.pos = (self.x + dp(1), self.y + dp(1))
        self._bg_r.size = (max(0, self.width - dp(2)), max(0, self.height - dp(2)))

    def set_bg(self, rgba):
        self._bg_c.rgba = rgba


class TapCard(ButtonBehavior, Card):
    def on_press(self):
        r, g, b, a = self.bg
        self.set_bg((min(1, r + 0.07), min(1, g + 0.07), min(1, b + 0.07), a))

    def on_release(self):
        self.set_bg(self.bg)


class SLabel(Label):
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
            self._c = Color(*color)
            self._e = Ellipse(pos=self.pos, size=self.size)
        self.bind(pos=self._u, size=self._u)

    def _u(self, *_):
        self._e.pos, self._e.size = self.pos, self.size

    def set_color(self, color):
        self._c.rgba = color


class StatusPill(TapCard):
    """وضعیت مدل: آماده‌سازی / آماده / خاموش. با لمس، دوباره تلاش می‌کند."""

    def __init__(self, **kwargs):
        super().__init__(bg=SURFACE, border=BORDER, radius=15,
                         size_hint=(None, None), size=(dp(100), dp(30)),
                         padding=[dp(10), 0], spacing=dp(6),
                         pos_hint={"center_y": 0.5}, **kwargs)
        self.dot = Dot(ORANGE, size_hint=(None, None), size=(dp(8), dp(8)), pos_hint={"center_y": 0.5})
        self.lbl = SLabel("آماده‌سازی…", font_size=sp(11.5), color=MUTED, shorten=True)
        self.add_widget(self.dot)
        self.add_widget(self.lbl)

    def set(self, color, text):
        self.dot.set_color(color)
        self.lbl.text = shape(text)


class PlusButton(TapCard):
    """دکمه‌ی گفتگوی جدید (+)."""

    def __init__(self, **kwargs):
        super().__init__(bg=SURFACE, border=BORDER, radius=19, **kwargs)
        with self.canvas.after:
            Color(*TEXT)
            self._h = Line(width=dp(1.6), cap="round")
            self._v = Line(width=dp(1.6), cap="round")
        self.bind(pos=self._d, size=self._d)

    def _d(self, *_):
        cx, cy = self.center
        s = dp(7)
        self._h.points = [cx - s, cy, cx + s, cy]
        self._v.points = [cx, cy - s, cx, cy + s]


class SendButton(TapCard):
    """ارسال (فلش) / توقف (مربع)."""

    def __init__(self, **kwargs):
        super().__init__(bg=ACCENT, border=ACCENT, radius=22, **kwargs)
        self.stop = False
        with self.canvas.after:
            Color(*WHITE)
            self._shaft = Line(width=dp(1.8), cap="round")
            self._head = Line(width=dp(1.8), cap="round", joint="round")
            self._sq = Rectangle(size=(0, 0))
        self.bind(pos=self._draw, size=self._draw)

    def set_stop(self, v):
        self.stop = v
        self._draw()

    def _draw(self, *_):
        cx, cy = self.center
        if self.stop:
            s = dp(7)
            self._shaft.points, self._head.points = [], []
            self._sq.pos, self._sq.size = (cx - s, cy - s), (2 * s, 2 * s)
        else:
            self._sq.size = (0, 0)
            s = min(self.width, self.height) * 0.22
            self._shaft.points = [cx, cy - s, cx, cy + s]
            self._head.points = [cx - s * 0.85, cy + s * 0.1, cx, cy + s * 1.05, cx + s * 0.85, cy + s * 0.1]


class ChatLabel(Label):
    """متن چندخطی فارسی با شکستن خط دستی (هر خط جدا shape می‌شود)."""

    def __init__(self, color=TEXT, font_px=None, **kwargs):
        self._font_px = font_px or sp(15.5)
        super().__init__(font_name=FONT, font_size=self._font_px, color=color,
                         halign="right", valign="top", size_hint=(None, None),
                         line_height=1.45, **kwargs)
        self._core = CoreLabel(font_name=FONT, font_size=self._font_px)

    def _w(self, s):
        return self._core.get_extents(s)[0]

    def set_text(self, raw, max_w):
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
        self.text_size = (None, None)
        self.text = "\n".join(shape(l) for l in lines)
        self.texture_update()
        w, h = self.texture_size
        self.size = (w + dp(2), h)
        self.text_size = self.size


class TypingBubble(Card):
    def __init__(self, **kwargs):
        super().__init__(bg=SURFACE, border=BORDER, radius=18,
                         size_hint=(None, None), size=(dp(70), dp(40)), **kwargs)
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


# ═════════════════════════ برنامه ═════════════════════════
class SearchApp(App):
    title = APP_TITLE

    # ---------- چرخه‌ی زندگی ----------
    def on_pause(self):
        return True            # با رفتن به Termux برنامه بسته نشود

    def on_resume(self):
        if self.status_kind != "ready":
            self.warm_up()

    def on_start(self):
        self.warm_up()

    # ---------- ساخت رابط ----------
    def build(self):
        self.busy = False
        self.welcome = None
        self.typing = None
        self.typing_row = None
        self.stream_bub = None
        self.history = []
        self.req_id = 0
        self.cancel_ev = None
        self.status_kind = "loading"
        self._pending = False
        self._latest = ""
        self._latest_rid = -1
        self._last_query = ""

        root = BoxLayout(orientation="vertical")

        header = BoxLayout(size_hint_y=None, height=dp(72), padding=[dp(14), dp(10)], spacing=dp(10))
        self.plus = PlusButton(size_hint=(None, None), size=(dp(38), dp(38)), pos_hint={"center_y": 0.5})
        self.plus.bind(on_release=lambda *_: self.new_chat())
        self.status = StatusPill()
        self.status.bind(on_release=lambda *_: self.warm_up())
        titles = BoxLayout(orientation="vertical", spacing=dp(1))
        titles.add_widget(SLabel(APP_TITLE, font_size=sp(16.5), shorten=True))
        titles.add_widget(SLabel(APP_SUBTITLE, font_size=sp(11), color=MUTED, shorten=True))
        logo = Card(bg=ACCENT, border=ACCENT, radius=14, size_hint=(None, None),
                    size=(dp(44), dp(44)), pos_hint={"center_y": 0.5})
        logo.add_widget(Label(text="AI", font_name=FONT, font_size=sp(15), color=WHITE))
        for w in (self.plus, self.status, titles, logo):
            header.add_widget(w)
        root.add_widget(header)

        divider = Widget(size_hint_y=None, height=dp(1))
        with divider.canvas:
            Color(*BORDER)
            rect = Rectangle(pos=divider.pos, size=divider.size)
        divider.bind(pos=lambda w, v: setattr(rect, "pos", v), size=lambda w, v: setattr(rect, "size", v))
        root.add_widget(divider)

        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(3),
                                 bar_color=(*ACCENT[:3], 0.45), bar_inactive_color=(*ACCENT[:3], 0.0))
        self.chat = BoxLayout(orientation="vertical", size_hint_y=None,
                              padding=[dp(14), dp(16)], spacing=dp(10))
        self.chat.bind(minimum_height=self.chat.setter("height"))
        self.scroll.add_widget(self.chat)
        root.add_widget(self.scroll)

        bar = BoxLayout(size_hint_y=None, height=dp(78), padding=[dp(12), dp(10)])
        field = Card(bg=SURFACE, border=BORDER, radius=28,
                     padding=[dp(8), dp(6), dp(16), dp(6)], spacing=dp(8))
        self.send_btn = SendButton(size_hint=(None, None), size=(dp(44), dp(44)), pos_hint={"center_y": 0.5})
        self.send_btn.bind(on_release=lambda *_: self.on_send_btn())
        self.input = TextInput(
            hint_text=shape("هر چیزی بپرسید…"), hint_text_color=MUTED, foreground_color=TEXT,
            cursor_color=ACCENT_2, background_normal="", background_active="",
            background_color=(0, 0, 0, 0), font_name=FONT, font_size=sp(15.5),
            multiline=False, write_tab=False, base_direction="rtl", halign="right",
            padding=[dp(4), dp(10), dp(4), dp(10)],
        )
        self.input.bind(height=lambda w, h: setattr(w, "padding_y", [max(0, (h - w.line_height) / 2)] * 2))
        self.input.bind(on_text_validate=lambda *_: self.on_submit())
        field.add_widget(self.send_btn)
        field.add_widget(self.input)
        bar.add_widget(field)
        root.add_widget(bar)

        self._show_welcome()
        return root

    # ---------- وضعیت و گرم‌کردن مدل ----------
    def set_status(self, kind):
        self.status_kind = kind
        table = {
            "loading": (ORANGE, "آماده‌سازی…"),
            "ready": (GREEN, "آماده"),
            "off": (RED, "سرور خاموش"),
            "nomodel": (RED, "مدل نصب نیست"),
        }
        color, text = table[kind]
        self.status.set(color, text)

    def warm_up(self, *_):
        self.set_status("loading")
        threading.Thread(target=self._warm, daemon=True).start()

    def _warm(self):
        def st(kind):
            Clock.schedule_once(lambda dt: self.set_status(kind), 0)

        for _ in range(30):
            try:
                r = requests.get(OLLAMA_URL + "/api/tags", timeout=3)
                if r.status_code == 200:
                    names = [m.get("name", "") for m in r.json().get("models", [])]
                    if OLLAMA_MODEL not in names and OLLAMA_MODEL + ":latest" not in names:
                        st("nomodel")
                        return
                    requests.post(OLLAMA_URL + "/api/generate",
                                  json={"model": OLLAMA_MODEL, "prompt": "", "stream": False,
                                        "keep_alive": KEEP_ALIVE}, timeout=OLLAMA_TIMEOUT)
                    st("ready")
                    return
            except Exception:
                pass
            time.sleep(4)
        st("off")

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
        w.add_widget(SLabel("ریاضی، تحقیق، آشپزی، گفتگو و ...", font_size=sp(13), color=MUTED,
                            halign="center", size_hint_y=None, height=dp(22)))
        w.add_widget(Widget(size_hint_y=None, height=dp(10)))
        w.add_widget(SLabel("پیشنهادها", font_size=sp(12), color=MUTED, size_hint_y=None, height=dp(22)))
        for s in SUGGESTIONS:
            chip = TapCard(bg=SURFACE, border=BORDER, radius=16, size_hint_y=None,
                           height=dp(52), padding=[dp(16), 0])
            chip.add_widget(SLabel(s, font_size=sp(14.5), shorten=True))
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

    def _bubble(self, raw, kind):
        st = self._style(kind)
        padx, pady = dp(st["pad"][0]), dp(st["pad"][1])
        max_inner = Window.width * 0.84 - 2 * padx
        lbl = ChatLabel(color=st["color"], font_px=st["px"])
        lbl.set_text(raw, max_inner)
        bub = Card(bg=st["bg"], border=st["border"], radius=18 if kind != "source" else 12,
                   size_hint=(None, None), padding=[padx, pady],
                   size=(lbl.width + 2 * padx, lbl.height + 2 * pady))
        bub.add_widget(lbl)
        bub.label = lbl
        bub.max_inner, bub.padx, bub.pady = max_inner, padx, pady
        return bub

    def _row(self, widget, side):
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
        Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", 0), 0.04)

    # ---------- گفتگو ----------
    def on_send_btn(self):
        if self.busy:
            self.stop_generation()
        else:
            self.on_submit()

    def on_submit(self, preset=None):
        query = (preset if isinstance(preset, str) else self.input.text).strip()
        if not query or self.busy:
            return
        self.busy = True
        self.send_btn.set_stop(True)
        self.input.text = ""
        if self.welcome is not None:
            self.chat.remove_widget(self.welcome)
            self.welcome = None

        self._row(self._bubble(query, "user"), "right")
        self.typing = TypingBubble()
        self.typing_row = self._row(self.typing, "left")

        self.req_id += 1
        rid = self.req_id
        self.cancel_ev = threading.Event()
        self.stream_bub = None
        self._pending = False
        self._latest = ""
        self._last_query = query

        threading.Thread(target=self._run_query,
                         args=(query, rid, self.cancel_ev, list(self.history)), daemon=True).start()
        Clock.schedule_once(lambda dt: setattr(self.input, "focus", True), 0.1)

    def stop_generation(self):
        self.req_id += 1
        if self.cancel_ev is not None:
            self.cancel_ev.set()
        self._drop_typing()
        self.stream_bub = None
        self.busy = False
        self.send_btn.set_stop(False)

    def new_chat(self):
        self.stop_generation()
        self.chat.clear_widgets()
        self.history = []
        self._show_welcome()

    def _run_query(self, query, rid, ev, history):
        def push(text):
            if rid != self.req_id:
                return
            self._latest, self._latest_rid = text, rid
            if not self._pending:
                self._pending = True
                Clock.schedule_once(self._flush, 0.08)

        result = ask(query, push, history, ev)
        Clock.schedule_once(lambda dt: self._finish(result, rid), 0.15)

    def _drop_typing(self):
        if self.typing is not None:
            self.typing.stop()
            if self.typing_row is not None:
                self.chat.remove_widget(self.typing_row)
            self.typing = None
            self.typing_row = None

    def _set_bot_text(self, text):
        if self.stream_bub is None:
            self._drop_typing()
            self.stream_bub = self._bubble(text, "bot")
            self._row(self.stream_bub, "left")
        else:
            b = self.stream_bub
            b.label.set_text(text, b.max_inner)
            b.size = (b.label.width + 2 * b.padx, b.label.height + 2 * b.pady)
        self._scroll_bottom()

    def _flush(self, dt):
        self._pending = False
        if self._latest and self._latest_rid == self.req_id:
            self._set_bot_text(self._latest)

    def _finish(self, res, rid):
        if rid != self.req_id:
            return
        if res["error"]:
            self._drop_typing()
            if self.stream_bub is None:
                self._row(self._bubble(res["text"], "error"), "left")
        else:
            self._set_bot_text(res["text"])
            self.history += [{"role": "user", "content": self._last_query[:600]},
                             {"role": "assistant", "content": res["text"][:600]}]
            self.history = self.history[-HISTORY_MESSAGES:]
            if res.get("title"):
                short = res["title"] if len(res["title"]) <= 30 else res["title"][:29] + "…"
                self._row(self._bubble("منبع: %s · %s" % (SOURCE_NAME, short), "source"), "left")
        self.stream_bub = None
        self.busy = False
        self.send_btn.set_stop(False)
        self._scroll_bottom()


if __name__ == "__main__":
    SearchApp().run()
