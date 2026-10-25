# -*- coding: utf-8 -*-
"""
دستیار هوشمند فارسی - نسخه‌ی پیشرفته (Kivy)
------------------------------------------------
- مدل هوش مصنوعی روی خود گوشی (Ollama در Termux) یا Cloudflare Workers AI
- پاسخ‌های فوری بدون مدل: حساب/معادله (دقیق)، سلام، جوک
- گرم‌کردن مدل هنگام باز شدن برنامه (جواب اول سریع‌تر)
- جواب زنده (stream)، دکمه‌ی توقف، گفتگوی جدید، حافظه‌ی گفتگو
- تحقیق با منبع از ویکی‌پدیای فارسی، کش پاسخ‌ها

اصلاحات این نسخه (جواب نصفه):
  1) سقف توکن‌ها (MODE_TOKENS) چند برابر شد.
  2) اگر Cloudflare جواب را به‌خاطر سقف توکن قطع کند (finish_reason=length)،
     برنامه خودکار «ادامه بده» می‌فرستد و جواب را کامل می‌کند.
  3) متن‌های بلند در چند تکه‌ی کوچک نمایش داده می‌شوند (محدودیت اندازه‌ی تکسچر Kivy).
  4) پرامپت‌ها دیگر مدل را به جواب خیلی کوتاه مجبور نمی‌کنند.
  5) حافظه‌ی گفتگو جواب‌های بلندتری نگه می‌دارد (600 به‌جای 300 نویسه).
"""
import ast
import json
import math
import os
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
from kivy.uix.popup import Popup
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

# --- مدل ---
# توکن و Account ID را داخل کد نگذارید؛ از «تنظیمات اتصال» داخل برنامه وارد کنید.
CF_ACCOUNT_ID = ""
CF_API_TOKEN = ""
CF_MODELS = ["@cf/qwen/qwen3-30b-a3b-fp8", "@cf/meta/llama-3.2-3b-instruct"]
CLOUD_URL = ""                       # آدرس Worker کلودفلر (اختیاری). خالی = غیرفعال
CLOUD_KEY = ""                       # کلید ساده‌ی برنامه (APP_KEY در Worker؛ اختیاری)
SERVER_URL = ""                      # آدرس سرور عمومی شما. خالی = بدون سرور
SERVER_MODEL = "qwen3:4b-instruct-2507-q4_K_M"
SERVER_KEY = ""                      # اگر سرور کلید دارد
OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen3:4b-instruct-2507-q4_K_M"   # سریع‌تر: qwen3:1.7b | قوی‌تر (کندتر): qwen3:8b
OLLAMA_TIMEOUT = 300
CONTEXT_SIZE = 4096                  # کوچک‌تر = سریع‌تر (برای جواب‌های بلندتر کمی بیشتر شد)
KEEP_ALIVE = "30m"                   # مدل تا ۳۰ دقیقه در حافظه می‌ماند
RETRIEVE_DOCS = 1                    # تعداد مقاله‌ی مرجع برای هر سؤال
DOC_CHARS = 380                      # طول خلاصه‌ی هر مقاله
HISTORY_MESSAGES = 4                 # تعداد پیام‌های قبلیِ یادآوری‌شده
# فارسی ~۲ تا ۳ توکن برای هر کلمه مصرف می‌کند؛ سقف‌ها بر همین اساس بالا رفتند.
MODE_TOKENS = {"math": 800, "joke": 300, "cook": 1000, "research": 700, "chat": 1000}
MAX_CONTINUE = 2                     # حداکثر دفعات «ادامه بده» وقتی جواب قطع شود
RESEARCH_CHARS = 1300                # طول متن مقاله‌ی ویکی‌پدیا برای تحقیق

HEADERS = {"User-Agent": "SearchAppPersian/1.0 (student project)"}
WIKI_SEARCH_URL = "https://fa.wikipedia.org/w/api.php"
WIKI_SUMMARY_URL = "https://fa.wikipedia.org/api/rest_v1/page/summary/"

NO_RESULT_MSG = "پاسخی پیدا نشد."
NO_CONNECTION_MSG = "اتصال به اینترنت برقرار نشد."
TIMEOUT_MSG = "درخواست بیش از حد طول کشید. دوباره تلاش کنید."
NO_AI_MSG = ("گفتگوی آزاد فعلاً در دسترس نیست، ولی تحقیق، ریاضی، جوک و سلام کار می‌کنند. "
             "مثلاً بنویسید: «درباره‌ی حافظ تحقیق کن» یا «حل کن: 2x + 6 = 14».")

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

# ═════════════════════════ انتخاب سرور: گوشی / کامپیوتر / ابر ═════════════════════════
BACKEND = {"url": OLLAMA_URL, "model": OLLAMA_MODEL, "pc": False, "cloud": False, "cf_account": "", "cf_token": ""}


def _settings_path():
    try:
        return os.path.join(App.get_running_app().user_data_dir, "settings.json")
    except Exception:
        return None


def load_settings():
    path = _settings_path()
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data):
    path = _settings_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def apply_settings():
    """اگر آدرس کامپیوتر ذخیره شده باشد از آن استفاده می‌کند، وگرنه Cloudflare، وگرنه خود گوشی."""
    st = load_settings()
    pc = (st.get("pc_url") or "").strip()
    if pc:
        if not pc.startswith("http"):
            pc = "http://" + pc
        if ":" not in pc.split("//", 1)[1]:
            pc += ":11434"
        BACKEND.update(url=pc.rstrip("/"), model=(st.get("pc_model") or "qwen3:8b").strip(), pc=True, cloud=False)
    elif (st.get("cf_account") or CF_ACCOUNT_ID).strip() and (st.get("cf_token") or CF_API_TOKEN).strip():
        BACKEND.update(url="https://api.cloudflare.com", model="cf", pc=False, cloud="direct",
                       cf_account=(st.get("cf_account") or CF_ACCOUNT_ID).strip(),
                       cf_token=(st.get("cf_token") or CF_API_TOKEN).strip())
    elif CLOUD_URL:
        BACKEND.update(url=CLOUD_URL.rstrip("/"), model="cloud", pc=False, cloud=True)
    elif SERVER_URL:
        BACKEND.update(url=SERVER_URL.rstrip("/"), model=SERVER_MODEL, pc=False, cloud=False)
    else:
        BACKEND.update(url=OLLAMA_URL, model=OLLAMA_MODEL, pc=False, cloud=False)


# ═════════════════════════ متن فارسی ═════════════════════════
def shape(text):
    try:
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


# ═════════════════════════ دستورِ مدل (پرامپت‌ها) ═════════════════════════
RULES = (" فقط فارسی ساده و درست بنویس (بدون حروف چینی). اول جواب مستقیم، بعد توضیح کافی و کامل. "
         "جواب را همیشه تا انتها و با جمله‌ی کامل تمام کن. چیزی اختراع نکن؛ اگر نمی‌دانی بگو.")
REF_RULE = " از «متن مرجع» برای پاسخ استفاده کن؛ اگر نامرتبط بود نادیده بگیر."
MODES = {
    "math": (0.1, "تو معلم ریاضی دقیقی. مرحله‌به‌مرحله و روشن حل کن. اگر «نتیجه‌ی دقیق» داده شد همان جواب نهایی است." + RULES),
    "joke": (0.9, "تو طنزپرداز بامزه‌ای. یک جوک کوتاه و تمیز بگو." + RULES),
    "cook": (0.4, "تو سرآشپز ایرانی هستی. مواد و مراحل را شماره‌دار و کامل بنویس." + RULES),
    "research": (0.2, "تو پژوهشگر دقیقی. پاسخی روشن و منظم بده." + RULES),
    "chat": (0.5, "تو دستیار هوشمند، صمیمی و باسواد هستی. آزادانه و طبیعی گفتگو کن، منطقی فکر کن و کامل و درست جواب بده؛ "
                  "اگر سؤال ساده بود کوتاه، اگر نیاز به توضیح داشت مفصل‌تر پاسخ بده." + RULES),
}
KW_JOKE = ("جوک", "شوخی", "بخندون", "لطیفه")
KW_COOK = ("دستور پخت", "طرز تهیه", "آشپزی", "غذا", "پخت", "مواد لازم")
KW_MATH = ("حل کن", "مشتق", "انتگرال", "معادله", "ریاضی", "محاسبه", "ساده کن", "حساب کن")
KW_RESEARCH = ("تحقیق", "مقاله", "جستجو کن")   # فقط وقتی کاربر صریحاً بخواهد

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


_STOP_Q = {"چیست", "کیست", "کجاست", "چه", "چی", "کی", "کجا", "آیا", "درباره", "تحقیق", "کن", "توضیح",
           "بده", "بگو", "لطفا", "لطفاً", "را", "رو", "من", "برام", "برای", "جستجو", "چه‌کسی", "کسی",
           "زمانی", "سالی", "چطور", "چگونه", "چرا", "چند", "کدام", "هست", "است", "؟", "?"}


def clean_query(q):
    words = re.sub(r"[؟?.,!:؛،]", " ", q).split()
    keep = [w for w in words if w not in _STOP_Q]
    return " ".join(keep) or q


def _relevant(title, q):
    qn = q.replace("ي", "ی").replace("ك", "ک")
    return any(len(w) >= 4 and w in qn for w in re.split(r"[\s\u200c()\-]+", title))


def _wiki_fulltext(query, lang="fa"):
    """جستجوی متن‌کامل + خلاصه‌ی چند مقاله در یک درخواست. خروجی: [(عنوان، خلاصه)]"""
    r = SESSION.get("https://%s.wikipedia.org/w/api.php" % lang, params={
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": query, "gsrlimit": RETRIEVE_DOCS + 1, "gsrnamespace": 0,
        "prop": "extracts", "exintro": 1, "explaintext": 1,
        "exchars": DOC_CHARS, "exlimit": RETRIEVE_DOCS + 1}, timeout=8)
    if r.status_code != 200:
        return []
    pages = (r.json().get("query") or {}).get("pages") or {}
    out = []
    for pg in sorted(pages.values(), key=lambda x: x.get("index", 99)):
        ex = (pg.get("extract") or "").strip()
        if ex:
            out.append((pg.get("title", ""), ex))
    return out[:RETRIEVE_DOCS]


def english_keywords(q, cancel=None):
    """کلیدواژه‌ی انگلیسی برای جستجو در ویکی‌پدیای انگلیسی (دانش بسیار بیشتر)."""
    try:
        out = ask_ollama("Convert the user's question into 2-5 English Wikipedia search keywords. "
                         "Output only the keywords, nothing else.", q, 0.0, 40, None, None, cancel)
        return re.sub(r"[^A-Za-z0-9 \-]", " ", out).strip()
    except Exception:
        return ""


# ═════════════════════════ مغز: مسیریابی و مدل ═════════════════════════
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]+")


def strip_think(t):
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.S)
    if "<think>" in t:
        t = t.split("<think>")[0]
    return _CJK.sub("", t).strip()


def _cf_call(model, msgs, max_tokens, temperature):
    """یک درخواست به Cloudflare Workers AI. خروجی: (متن، آیا_بخاطر_سقف_توکن_قطع_شد)."""
    r = requests.post(
        "https://api.cloudflare.com/client/v4/accounts/%s/ai/run/%s" % (BACKEND["cf_account"], model),
        json={"messages": msgs, "max_tokens": max_tokens, "temperature": temperature},
        headers={"Authorization": "Bearer " + BACKEND["cf_token"]}, timeout=90)
    r.raise_for_status()
    res = r.json().get("result") or {}
    ch = (res.get("choices") or [{}])[0]
    text = res.get("response") or (ch.get("message") or {}).get("content") or ""
    cut = ch.get("finish_reason") == "length"
    return strip_think(str(text)), cut


def ask_ollama(system, user, temperature, max_tokens, push=None, history=None, cancel=None):
    messages = [{"role": "system", "content": system}]
    messages += list(history or [])
    messages.append({"role": "user", "content": user})
    if BACKEND.get("cloud") == "direct":
        last = None
        for model in CF_MODELS:
            try:
                msgs = [dict(m) for m in messages]
                is_qwen = "qwen3" in model
                if is_qwen:
                    for m in reversed(msgs):
                        if m["role"] == "user":
                            m["content"] += " /no_think"
                            break
                text, cut = _cf_call(model, msgs, max_tokens, temperature)
                # اگر جواب به‌خاطر سقف توکن قطع شد، ادامه‌اش را بگیر
                n = 0
                while text and cut and n < MAX_CONTINUE and not (cancel is not None and cancel.is_set()):
                    n += 1
                    if push:
                        push(text)
                    nxt = "ادامه بده؛ دقیقاً از همان‌جا که قطع شد، بدون تکرار."
                    if is_qwen:
                        nxt += " /no_think"
                    more, cut = _cf_call(
                        model,
                        msgs + [{"role": "assistant", "content": text}, {"role": "user", "content": nxt}],
                        max_tokens, temperature)
                    if not more:
                        break
                    text += (" " if not text.endswith("\n") else "") + more
                if text:
                    if push:
                        push(text)
                    return text
            except Exception as e:
                last = e
        raise last or ValueError("empty")
    if BACKEND.get("cloud"):
        r = requests.post(BACKEND["url"] + "/chat",
                          json={"messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                          headers={"X-App-Key": CLOUD_KEY}, timeout=90)
        r.raise_for_status()
        text = strip_think(r.json().get("answer", ""))
        if push and text:
            push(text)
        return text
    payload = {
        "model": BACKEND["model"],
        "messages": messages,
        "stream": True,
        "keep_alive": KEEP_ALIVE,
        "options": {"temperature": temperature, "top_p": 0.8, "repeat_penalty": 1.1,
                    "num_predict": max_tokens, "num_ctx": CONTEXT_SIZE},
    }
    if "qwen3" in BACKEND["model"] and "instruct" not in BACKEND["model"]:
        payload["think"] = False
    acc = ""
    hdr = {"Authorization": "Bearer " + SERVER_KEY} if (SERVER_KEY and BACKEND["url"] == SERVER_URL.rstrip("/")) else None
    with requests.post(BACKEND["url"] + "/api/chat", json=payload, stream=True, headers=hdr,
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
    if any(k in msg for k in KW_RESEARCH):
        return "research"
    if any(k in msg for k in KW_COOK):
        return "cook"
    if any(k in msg for k in KW_MATH) or safe_math(msg) is not None:
        return "math"
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


_TOPIC_STOP = {"تحقیق", "کن", "کنید", "بکن", "درباره", "درباره‌ی", "درمورد", "مقاله", "جستجو", "لطفا", "لطفاً",
               "یک", "بنویس", "بده", "برام", "برایم", "بگو", "در", "مورد", "راجع", "به", "را", "رو", "خلاصه",
               "کامل", "و", "من", "می‌خوام", "می‌خواهم", "میخوام", "ازش", "از", "اش", "ی"}


def extract_topic(q):
    words = re.sub(r"[؟?.,!:؛،]", " ", q).split()
    keep = [w for w in words if w not in _TOPIC_STOP]
    return " ".join(keep).strip() or q


def _wiki_titles(query, lang):
    r = SESSION.get("https://%s.wikipedia.org/w/api.php" % lang, params={
        "action": "opensearch", "search": query, "limit": 5, "namespace": 0, "format": "json"}, timeout=8)
    if r.status_code != 200 or not r.text.strip():
        return []
    data = r.json()
    return data[1] if len(data) > 1 else []


def _wiki_intro(title, lang, chars):
    r = SESSION.get("https://%s.wikipedia.org/w/api.php" % lang, params={
        "action": "query", "format": "json", "prop": "extracts", "exintro": 1, "explaintext": 1,
        "exchars": chars, "titles": title, "redirects": 1}, timeout=8)
    if r.status_code != 200:
        return ""
    pages = (r.json().get("query") or {}).get("pages") or {}
    for pg in pages.values():
        ex = (pg.get("extract") or "").strip()
        if ex:
            return ex
    return ""


def research_lookup(topic, q, cancel=None, stage=None):
    """مقاله‌ی ویکی‌پدیا را پیدا می‌کند: فارسی، و اگر نبود انگلیسی. خروجی: dict یا None."""
    try:
        title = None
        for t in _wiki_titles(topic, "fa"):
            if _relevant(t, topic):
                title = t
                break
        if title is None:
            docs = _wiki_fulltext(clean_query(topic), "fa")
            if docs:
                title = docs[0][0]
        if title:
            text = _wiki_intro(title, "fa", RESEARCH_CHARS)
            if text:
                return {"title": title, "text": text, "lang": "fa"}
        if cancel is None or not cancel.is_set():
            if stage:
                stage("search_en")
            kw = english_keywords(q, cancel)
            if kw:
                titles = _wiki_titles(kw, "en")
                if titles:
                    text = _wiki_intro(titles[0], "en", 900)
                    if text:
                        return {"title": titles[0], "text": text, "lang": "en"}
    except requests.exceptions.ConnectionError:
        return {"error": NO_CONNECTION_MSG}
    except Exception:
        pass
    return None


def format_article(title, text, limit=900):
    """متن ویکی‌پدیا را به یک مقاله‌ی کوتاه (خلاصه + توضیح بیشتر) تبدیل می‌کند. بدون مدل = سریع و دقیق."""
    text = re.sub(r"[ \t]+", " ", re.sub(r"\s*\n\s*", " ", text)).strip()
    sentences = [x.strip() for x in re.split(r"(?<=[.!؟?])\s+", text) if x.strip()]
    summary, i = "", 0
    while i < len(sentences) and (not summary or len(summary) + len(sentences[i]) <= 380):
        summary += (" " if summary else "") + sentences[i]
        i += 1
    details = ""
    while i < len(sentences) and len(summary) + len(details) + len(sentences[i]) <= limit:
        details += (" " if details else "") + sentences[i]
        i += 1
    out = "«%s»\n\nخلاصه:\n%s" % (title, summary)
    if details:
        out += "\n\nتوضیح بیشتر:\n" + details
    return out


def _ask_impl(query, push=None, history=None, cancel=None, stage=None):
    """دو حالت روشن: گفتگوی آزاد (فقط مدل) و تحقیق (مقاله‌ی ویکی‌پدیا)."""
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

    # ── حالت تحقیق ──
    note = ""
    if mode == "research":
        topic = extract_topic(q)
        key = ("research", topic)
        if key in CACHE:
            CACHE.move_to_end(key)
            return CACHE[key]
        if stage:
            stage("search")
        info = research_lookup(topic, q, cancel, stage)
        if info and info.get("error"):
            return {"text": info["error"], "title": None, "error": True}
        if info and info["lang"] == "fa":
            res = ok(format_article(info["title"], info["text"]), info["title"])
            CACHE[key] = res
            while len(CACHE) > 40:
                CACHE.popitem(last=False)
            return res
        if info and info["lang"] == "en":
            if stage:
                stage("think")
            try:
                ans = ask_ollama(
                    "Summarize the text below accurately in simple Persian (Farsi), 4-5 complete sentences. "
                    "Use only the text. Do not use Chinese characters. Always finish your last sentence.",
                    info["text"], 0.2, MODE_TOKENS["research"], push, None, cancel)
                if ans:
                    res = ok("«%s»\n\nخلاصه:\n%s" % (info["title"], ans), info["title"] + " (EN)")
                    CACHE[key] = res
                    return res
            except Exception:
                pass
            return ok("«%s»\n\n%s" % (info["title"], info["text"]), info["title"] + " (EN)")
        # مقاله‌ای پیدا نشد: با احتیاط از دانش خود مدل (سؤال اصلی کاربر حفظ می‌شود)
        mode = "chat"
        note = "\n\n(در ویکی‌پدیا منبعی پیدا نشد؛ فقط اگر مطمئنی جواب بده و بگو منبع نداری.)"

    temperature, system = MODES[mode]
    user = q
    if mode == "math" and math_res:
        user = q + "\n\nنتیجه‌ی دقیق: " + math_res["answer"]
    user += note

    if stage:
        stage("think")
    try:
        answer = ask_ollama(system, user, temperature, MODE_TOKENS[mode], push, history, cancel)
        if answer:
            return ok(answer)
        raise ValueError("empty")
    except requests.exceptions.Timeout:
        return {"text": TIMEOUT_MSG, "title": None, "error": True}
    except Exception:
        if mode == "chat" and len(q) >= 6:           # بدون مدل: دست‌کم از ویکی‌پدیا جواب بده
            try:
                info = research_lookup(extract_topic(q), q, None, None)
                if info and not info.get("error") and info["lang"] == "fa":
                    return ok(format_article(info["title"], info["text"]), info["title"])
            except Exception:
                pass
        return {"text": NO_AI_MSG, "title": None, "error": True}


def ask(query, push=None, history=None, cancel=None, stage=None):
    try:
        return _ask_impl(query, push, history, cancel, stage)
    except Exception as e:                      # هرگز بی‌صدا گیر نکند
        return {"text": "خطای غیرمنتظره: " + str(e), "title": None, "error": True}


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


class ChatText(BoxLayout):
    """
    متن چندخطی فارسی با شکستن خط دستی (هر خط جدا shape می‌شود).
    متن بلند در چند Label کوچک (هرکدام حداکثر CHUNK_LINES خط) چیده می‌شود تا
    از محدودیت اندازه‌ی تکسچر Kivy عبور نکند و انتهای جواب بریده نشود.
    """
    CHUNK_LINES = 30

    def __init__(self, color=TEXT, font_px=None, **kwargs):
        self._font_px = font_px or sp(15.5)
        self._color = color
        super().__init__(orientation="vertical", size_hint=(None, None), spacing=0, **kwargs)
        self._core = CoreLabel(font_name=FONT, font_size=self._font_px)
        self._chunks = []

    def _w(self, s):
        return self._core.get_extents(s)[0]

    def _wrap(self, raw, max_w):
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
        return lines

    def _new_chunk(self):
        return Label(font_name=FONT, font_size=self._font_px, color=self._color,
                     halign="right", valign="top", size_hint=(None, None), line_height=1.45)

    def set_text(self, raw, max_w):
        lines = self._wrap(raw, max_w)
        n = self.CHUNK_LINES
        groups = [lines[i:i + n] for i in range(0, len(lines), n)] or [[""]]
        if len(groups) != len(self._chunks):
            while len(self._chunks) < len(groups):
                self._chunks.append(self._new_chunk())
            del self._chunks[len(groups):]
            self.clear_widgets()
            for c in reversed(self._chunks):      # BoxLayout عمودی: اولین فرزند پایین‌ترین است
                self.add_widget(c)
        sizes = []
        for c, g in zip(self._chunks, groups):
            c.text_size = (None, None)
            c.text = "\n".join(shape(l) for l in g)
            c.texture_update()
            sizes.append(c.texture_size)
        w = max(s[0] for s in sizes)
        total_h = sum(s[1] for s in sizes)
        for c, (_cw, ch) in zip(self._chunks, sizes):
            c.size = (w + dp(2), ch)
            c.text_size = c.size
        self.size = (w + dp(2), total_h)


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
        if self.status_kind not in ("ready", "busy", "lite"):
            self.warm_up()

    def on_start(self):
        self.warm_up()

    # ---------- ساخت رابط ----------
    def build(self):
        apply_settings()
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
        self._stage_text = "فکر…"
        self._t0 = 0.0
        self._tick_ev = None

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
            "ready": (GREEN, "آماده · PC" if BACKEND["pc"] else ("آماده · ابر" if BACKEND["cloud"] else "آماده")),
            "busy": (ACCENT_2, "در حال پاسخ…"),
            "off": (RED, "سرور خاموش"),
            "lite": (ACCENT_2, "حالت سبک"),
            "nomodel": (RED, "مدل نصب نیست"),
            "badkey": (RED, "توکن نامعتبر"),
        }
        color, text = table[kind]
        self.status.set(color, text)

    def warm_up(self, *_):
        self.set_status("loading")
        threading.Thread(target=self._warm, daemon=True).start()

    def _warm(self):
        def st(kind):
            Clock.schedule_once(lambda dt: self.set_status(kind), 0)

        local = BACKEND["url"].startswith("http://127.0.0.1")
        if BACKEND.get("cloud") == "direct":
            # یک درخواست واقعی و کوچک: هم اتصال و هم صحت Account ID و توکن را می‌سنجد
            for _ in range(3):
                try:
                    r = requests.post(
                        "https://api.cloudflare.com/client/v4/accounts/%s/ai/run/%s"
                        % (BACKEND["cf_account"], CF_MODELS[-1]),
                        json={"messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
                        headers={"Authorization": "Bearer " + BACKEND["cf_token"]}, timeout=15)
                    if r.status_code == 200:
                        st("ready")
                        return
                    if r.status_code in (400, 401, 403):
                        st("badkey")
                        return
                except Exception:
                    pass
                time.sleep(2)
            st("lite")
            return
        if BACKEND.get("cloud"):
            for _ in range(3):
                try:
                    if requests.get(BACKEND["url"] + "/health", timeout=6).status_code == 200:
                        st("ready")
                        return
                except Exception:
                    pass
                time.sleep(2)
            st("lite")
            return
        for _ in range(4 if local else 30):
            try:
                r = requests.get(BACKEND["url"] + "/api/tags", timeout=3)
                if r.status_code == 200:
                    names = [m.get("name", "") for m in r.json().get("models", [])]
                    if BACKEND["model"] not in names and BACKEND["model"] + ":latest" not in names:
                        st("lite" if local else "nomodel")
                        return
                    requests.post(BACKEND["url"] + "/api/generate",
                                  json={"model": BACKEND["model"], "prompt": "", "stream": False,
                                        "keep_alive": KEEP_ALIVE,
                                        "options": {"num_ctx": CONTEXT_SIZE}},
                                  timeout=OLLAMA_TIMEOUT)
                    st("ready")
                    return
            except Exception:
                pass
            time.sleep(3 if local else 4)
        st("lite" if local else "off")

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
        pc_chip = TapCard(bg=BG, border=BORDER, radius=16, size_hint_y=None, height=dp(44), padding=[dp(16), 0])
        pc_chip.add_widget(SLabel("تنظیمات اتصال (ابر / کامپیوتر)", font_size=sp(13), color=MUTED, shorten=True))
        pc_chip.bind(on_release=lambda *_: self.open_settings())
        w.add_widget(Widget(size_hint_y=None, height=dp(6)))
        w.add_widget(pc_chip)
        self.welcome = w
        self.chat.add_widget(w)

    def open_settings(self):
        st = load_settings()

        def field(text, hint):
            return TextInput(
                text=text, hint_text=hint, hint_text_color=MUTED, multiline=False,
                foreground_color=TEXT, cursor_color=ACCENT_2, background_normal="", background_active="",
                background_color=SURFACE, font_name=FONT, font_size=sp(14),
                size_hint_y=None, height=dp(42), padding=[dp(12), dp(10)])

        def lab(t):
            return SLabel(t, font_size=sp(12), color=MUTED, size_hint_y=None, height=dp(22))

        box = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(5))
        box.add_widget(lab("Cloudflare: شناسه‌ی حساب (Account ID)"))
        cf_acc = field(st.get("cf_account", ""), "Account ID")
        box.add_widget(cf_acc)
        box.add_widget(lab("Cloudflare: توکن (API Token)"))
        cf_tok = field(st.get("cf_token", ""), "API Token")
        box.add_widget(cf_tok)
        box.add_widget(lab("یا آدرس Ollama روی کامپیوتر (اختیاری)"))
        url_in = field(st.get("pc_url", ""), "192.168.1.23:11434")
        box.add_widget(url_in)
        box.add_widget(lab("نام مدل روی کامپیوتر"))
        model_in = field(st.get("pc_model", "qwen3:8b"), "qwen3:8b")
        box.add_widget(model_in)

        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
        pop = Popup(title=shape("تنظیمات اتصال"), title_font=FONT, title_color=TEXT,
                    separator_height=0, content=box, size_hint=(0.94, None), height=dp(520),
                    background="", background_color=(0.08, 0.09, 0.15, 1), auto_dismiss=True)

        def save(*_):
            save_settings({"cf_account": cf_acc.text.strip(), "cf_token": cf_tok.text.strip(),
                           "pc_url": url_in.text.strip(), "pc_model": model_in.text.strip() or "qwen3:8b"})
            apply_settings()
            pop.dismiss()
            self.warm_up()

        def clear(*_):
            save_settings({})
            apply_settings()
            pop.dismiss()
            self.warm_up()

        b_save = TapCard(bg=ACCENT, border=ACCENT, radius=14)
        b_save.add_widget(SLabel("ذخیره", halign="center", color=WHITE))
        b_save.bind(on_release=save)
        b_clear = TapCard(bg=SURFACE, border=BORDER, radius=14)
        b_clear.add_widget(SLabel("پاک کردن همه", halign="center"))
        b_clear.bind(on_release=clear)
        row.add_widget(b_save)
        row.add_widget(b_clear)
        box.add_widget(row)
        pop.open()

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
        lbl = ChatText(color=st["color"], font_px=st["px"])
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
        self.set_status("busy")
        self._start_ticker()
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

    def _start_ticker(self):
        self._stop_ticker()
        self._t0 = time.time()
        self._stage_text = "فکر…"
        self._tick_ev = Clock.schedule_interval(self._tick_status, 1)

    def _stop_ticker(self):
        if self._tick_ev is not None:
            self._tick_ev.cancel()
            self._tick_ev = None

    def _tick_status(self, dt):
        if not self.busy:
            return False
        self.status.set(ACCENT_2, "%s %ds" % (self._stage_text, int(time.time() - self._t0)))

    def stop_generation(self):
        self.req_id += 1
        if self.cancel_ev is not None:
            self.cancel_ev.set()
        self._drop_typing()
        self.stream_bub = None
        self.busy = False
        self._stop_ticker()
        self.send_btn.set_stop(False)
        if self.status_kind == "busy":
            self.set_status("ready")

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

        def stage(kind):
            if rid == self.req_id:
                self._stage_text = {"search": "جستجو…", "search_en": "جستجوی EN…", "think": "فکر…"}[kind]

        result = ask(query, push, history, ev, stage)
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
            self.history += [{"role": "user", "content": self._last_query[:200]},
                             {"role": "assistant", "content": res["text"][:600]}]
            self.history = self.history[-HISTORY_MESSAGES:]
            if res.get("title"):
                short = res["title"] if len(res["title"]) <= 30 else res["title"][:29] + "…"
                self._row(self._bubble("منبع: %s · %s" % (SOURCE_NAME, short), "source"), "left")
        self.stream_bub = None
        self.busy = False
        self._stop_ticker()
        self.send_btn.set_stop(False)
        if self.status_kind == "busy":
            self.set_status("ready")
        self._scroll_bottom()


if __name__ == "__main__":
    SearchApp().run()
