import requests

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

HEADERS = {"User-Agent": "Mozilla/5.0 (Android; Mobile) SearchApp/1.0"}


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


class SearchApp(App):
    def build(self):
        root = BoxLayout(orientation="vertical", padding=10, spacing=10)

        self.input_box = TextInput(
            hint_text="موضوع مورد نظر را بنویسید...",
            size_hint_y=None,
            height=50,
            multiline=False
        )
        self.input_box.bind(on_text_validate=self.on_submit)

        submit_btn = Button(text="جستجو", size_hint_y=None, height=50)
        submit_btn.bind(on_press=self.on_submit)

        self.result_label = Label(
            text="جواب اینجا نشان داده می‌شود",
            size_hint_y=None,
            text_size=(self.get_window_width(), None),
            halign="right",
            valign="top"
        )
        self.result_label.bind(texture_size=self.update_label_height)

        scroll = ScrollView()
        scroll.add_widget(self.result_label)

        root.add_widget(self.input_box)
        root.add_widget(submit_btn)
        root.add_widget(scroll)

        return root

    def get_window_width(self):
        from kivy.core.window import Window
        return Window.width - 40

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
