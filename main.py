import threading
import requests

from kivy.app import App
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.utils import get_color_from_hex

# ---------- Font ----------
LabelBase.register(name='Vazir', fn_regular='Vazirmatn-Regular.ttf')

# ---------- Theme ----------
BG_COLOR = get_color_from_hex('#0F1220')
CARD_COLOR = get_color_from_hex('#1B1F33')
ACCENT_COLOR = get_color_from_hex('#6C63FF')
TEXT_COLOR = get_color_from_hex('#F2F2F7')
MUTED_COLOR = get_color_from_hex('#9A9AB0')

HEADERS = {'User-Agent': 'SearchAppPersian/1.0 (Android search assistant app; contact: myap-project)'}

WIKI_SEARCH_URL = 'https://fa.wikipedia.org/w/api.php'
WIKI_SUMMARY_URL = 'https://fa.wikipedia.org/api/rest_v1/page/summary/'

NO_RESULT_MSG = 'پاسخی پیدا نشد.'
NO_CONNECTION_MSG = 'اتصال به اینترنت برقرار نشد. وای\u200cفای یا دیتای موبایل را بررسی کنید.'
TIMEOUT_MSG = 'درخواست بیش از حد طول کشید. دوباره تلاش کنید.'
EMPTY_RESPONSE_MSG = 'پاسخ خالی از سرور دریافت شد. اتصال اینترنت را بررسی کنید.'


class RoundedBox(BoxLayout):
    def __init__(self, bg_color=CARD_COLOR, **kwargs):
        super().__init__(**kwargs)
        self.bg_color = bg_color
        with self.canvas.before:
            Color(*self.bg_color)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[16])
        self.bind(pos=self.update_rect, size=self.update_rect)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


def ask(query):
    """Search Persian Wikipedia for `query` and return a short summary, or a Persian error message."""
    try:
        search_params = {
            'action': 'opensearch',
            'search': query,
            'limit': 1,
            'namespace': 0,
            'format': 'json',
        }
        r = requests.get(WIKI_SEARCH_URL, params=search_params, headers=HEADERS, timeout=15)

        if r.status_code != 200:
            return f'خطای سرور ({r.status_code}). اتصال اینترنت را بررسی کنید.'
        if not r.text.strip():
            return EMPTY_RESPONSE_MSG

        data = r.json()
        titles = data[1] if len(data) > 1 else []
        if not titles:
            return NO_RESULT_MSG

        title = titles[0]

        r2 = requests.get(WIKI_SUMMARY_URL + title, headers=HEADERS, timeout=15)

        if r2.status_code != 200:
            return f'خطای سرور در دریافت خلاصه ({r2.status_code}).'
        if not r2.text.strip():
            return EMPTY_RESPONSE_MSG

        data2 = r2.json()
        return data2.get('extract', NO_RESULT_MSG) or NO_RESULT_MSG

    except requests.exceptions.ConnectionError:
        return NO_CONNECTION_MSG
    except requests.exceptions.Timeout:
        return TIMEOUT_MSG
    except ValueError:
        return EMPTY_RESPONSE_MSG
    except Exception as e:
        return f'خطا: {e}'


class SearchApp(App):
    def build(self):
        Window.clearcolor = BG_COLOR

        root = BoxLayout(orientation='vertical', padding=[20, 30, 20, 20], spacing=18)

        title = Label(
            text='دستیار جستجو', font_name='Vazir', font_size='26sp',
            bold=True, color=TEXT_COLOR, size_hint_y=None, height=50,
        )

        subtitle = Label(
            text='یک موضوع بنویسید تا برایتان جستجو کنم', font_name='Vazir',
            font_size='14sp', color=MUTED_COLOR, size_hint_y=None, height=26,
        )

        input_card = RoundedBox(
            bg_color=CARD_COLOR, orientation='horizontal', size_hint_y=None,
            height=56, padding=[14, 6, 14, 6], spacing=10,
        )

        self.input_box = TextInput(
            hint_text='مثلاً: فرانسه', hint_text_color=MUTED_COLOR,
            font_name='Vazir', font_size='16sp', foreground_color=TEXT_COLOR,
            background_color=(0, 0, 0, 0), cursor_color=ACCENT_COLOR,
            multiline=False, padding=[10, 14, 10, 14], base_direction='rtl',
        )
        self.input_box.bind(on_text_validate=self.on_submit)
        input_card.add_widget(self.input_box)

        submit_btn = Button(
            text='جستجو', font_name='Vazir', font_size='16sp', bold=True,
            size_hint_y=None, height=52, background_normal='',
            background_color=ACCENT_COLOR, color=TEXT_COLOR,
        )
        submit_btn.bind(on_release=self.on_submit)

        result_card = RoundedBox(bg_color=CARD_COLOR, orientation='vertical', padding=[18, 18, 18, 18])

        self.result_label = Label(
            text='جواب اینجا نشان داده می\u200cشود', font_name='Vazir', font_size='16sp',
            color=TEXT_COLOR, size_hint_y=None,
            text_size=(Window.width - 76, None), halign='right', valign='top', line_height=1.4,
        )
        self.result_label.bind(texture_size=self.update_label_height)
        Window.bind(width=self.get_window_width)

        result_card.add_widget(self.result_label)

        scroll = ScrollView(bar_width=4, bar_color=ACCENT_COLOR)
        scroll.add_widget(result_card)

        root.add_widget(title)
        root.add_widget(subtitle)
        root.add_widget(input_card)
        root.add_widget(submit_btn)
        root.add_widget(scroll)

        return root

    def get_window_width(self, *args):
        self.result_label.text_size = (Window.width - 76, None)

    def update_label_height(self, *args):
        self.result_label.height = self.result_label.texture_size[1]

    def on_submit(self, *args):
        query = self.input_box.text.strip()
        if not query:
            return
        self.result_label.text = 'در حال جستجو...'
        threading.Thread(target=self._run_query, args=(query,), daemon=True).start()

    def _run_query(self, query):
        answer = ask(query)
        Clock.schedule_once(lambda dt: setattr(self.result_label, 'text', answer))


if __name__ == '__main__':
    SearchApp().run()
