import requests

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.graphics import Color, RoundedRectangle
from kivy.utils import get_color_from_hex

HEADERS = {"User-Agent": "Mozilla/5.0 (Android; Mobile) SearchApp/1.0"}

BG_COLOR = get_color_from_hex("#0F1220")
CARD_COLOR = get_color_from_hex("#1B1F33")
ACCENT_COLOR = get_color_from_hex("#6C63FF")
TEXT_COLOR = get_color_from_hex("#F2F2F7")
MUTED_COLOR = get_color_from_hex("#9A9AB0")

LabelBase.register(name="Vazir", fn_regular="Vazirmatn-Regular.ttf")

Window.clearcolor = BG_COLOR


def ask(query):
    try:
        url = "https://fa.wikipedia.org/w/api.php"
        params = {
            "action": "opensearch",
            "search": query,
            "limit": 1,
            "namespace": 0,
            "format": "json"
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = r.json()

        titles = data[1] if len(data) > 1 else []
        if not titles:
            return "پاسخی پیدا نشد."

        title = titles[0]

        summary_url = "https://fa.wikipedia.org/api/rest_v1/page/summary/" + title
        r2 = requests.get(summary_url, headers=HEADERS, timeout=15)
        data2 = r2.json()
        return data2.get("extract", "پاسخی پیدا نشد.")

    except Exception as e:
        return f"خطا: {e}"


class RoundedBox(BoxLayout):
    def __init__(self, bg_color, radius=18, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*bg_color)
            self.bg_rect = RoundedRectangle(
                pos=self.pos, size=self.size, radius=[radius]
            )
        self.bind(pos=self.update_rect, size=self.update_rect)

    def update_rect(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size


class SearchApp(App):
    def build(self):
        root = BoxLayout(
            orientation="vertical",
            padding=[20, 30, 20, 20],
            spacing=18
        )

        title = Label(
            text="دستیار جستجو",
            font_name="Vazir",
            font_size="26sp",
            bold=True,
            color=TEXT_COLOR,
            size_hint_y=None,
            height=50
        )

        subtitle = Label(
            text="یک موضوع بنویسید تا برایتان جستجو کنم",
            font_name="Vazir",
            font_size="14sp",
            color=MUTED_COLOR,
            size_hint_y=None,
            height=26
        )

        input_card = RoundedBox(
            bg_color=CARD_COLOR,
            orientation="horizontal",
            size_hint_y=None,
            height=56,
            padding=[14, 6, 14, 6],
            spacing=10
        )

        self.input_box = TextInput(
            hint_text="مثلاً: فرانسه",
            hint_text_color=MUTED_COLOR,
            font_name="Vazir",
            font_size="16sp",
            foreground_color=TEXT_COLOR,
            background_color=(0, 0, 0, 0),
            cursor_color=ACCENT_COLOR,
            multiline=False,
            padding=[10, 14, 10, 14],
            base_direction="rtl"
        )
        self.input_box.bind(on_text_validate=self.on_submit)
        input_card.add_widget(self.input_box)

        submit_btn = Button(
            text="جستجو",
            font_name="Vazir",
            font_size="16sp",
            bold=True,
            size_hint_y=None,
            height=52,
            background_normal="",
            background_color=ACCENT_COLOR,
            color=TEXT_COLOR
        )
        submit_btn.bind(on_press=self.on_submit)

        result_card = RoundedBox(
            bg_color=CARD_COLOR,
            orientation="vertical",
            padding=[18, 18, 18, 18]
        )

        self.result_label = Label(
            text="جواب اینجا نشان داده می‌شود",
            font_name="Vazir",
            font_size="16sp",
            color=TEXT_COLOR,
            size_hint_y=None,
            text_size=(self.get_window_width() - 76, None),
            halign="right",
            valign="top",
            line_height=1.4
        )
        self.result_label.bind(texture_size=self.update_label_height)

        scroll = ScrollView(bar_width=4, bar_color=ACCENT_COLOR)
        scroll.add_widget(self.result_label)
        result_card.add_widget(scroll)

        root.add_widget(title)
        root.add_widget(subtitle)
        root.add_widget(input_card)
        root.add_widget(submit_btn)
        root.add_widget(result_card)

        return root

    def get_window_width(self):
        return Window.width

    def update_label_height(self, instance, size):
        instance.height = size[1]

    def on_submit(self, instance):
        query = self.input_box.text.strip()
        if not query:
            return
        self.result_label.text = "در حال جستجو..."
        answer = ask(query)
        self.result_label.text = answer


if __name__ == "__main__":
    SearchApp().run()
