"""Arabic-to-German revision app backed by the supplied vocabulary lists."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd
import streamlit as st


st.set_page_config(page_title="مراجعة الألمانية", page_icon=":material/translate:", layout="wide")

ARABIC = "العربية"
GERMAN = "الألمانية"
LIST_DIRECTORY = Path(__file__).with_name("vocabulary_lists")


def clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value))).strip()


def has_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text))


def has_german(text: str) -> bool:
    return bool(re.search(r"[A-Za-zÄÖÜäöüß]", text))


def add_pair(pairs: list[tuple[str, str]], arabic: object, german: object) -> None:
    arabic_text, german_text = clean(arabic), clean(german)
    if arabic_text and german_text and has_arabic(arabic_text) and has_german(german_text):
        pairs.append((arabic_text, german_text))


def pairs_from_inline(text: object) -> list[tuple[str, str]]:
    """Read cells such as ``Vater = الأب`` or ``sein (يكون)``."""
    value = clean(text)
    pairs: list[tuple[str, str]] = []
    for german, arabic in re.findall(r"([A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß /-]*)\s*(?:=|\()\s*([^)=]+)\)?", value):
        if has_arabic(arabic):
            pairs.append((clean(arabic), clean(german)))
    return pairs


def to_dataframe(pairs: list[tuple[str, str]]) -> pd.DataFrame:
    frame = pd.DataFrame(pairs, columns=[ARABIC, GERMAN]).map(clean)
    frame = frame[(frame[ARABIC] != "") & (frame[GERMAN] != "")]
    return frame.drop_duplicates().reset_index(drop=True)


@st.cache_data(ttl="1h", max_entries=16)
def load_vocabulary(file_path: str) -> pd.DataFrame:
    """Extract usable Arabic-to-German pairs from each supplied CSV layout."""
    raw = pd.read_csv(file_path, header=None).map(clean).fillna("")
    filename = Path(file_path).name
    pairs: list[tuple[str, str]] = []

    if filename == "المفردات الشاملة.csv":
        # German word, Arabic translation, category.
        for _, row in raw.iloc[2:].iterrows():
            add_pair(pairs, row.iloc[1], row.iloc[0])

    elif filename == "أدوات الاستفهام.csv":
        # Question word and German example with their Arabic translations.
        for _, row in raw.iloc[2:].iterrows():
            meaning_match = re.search(r"\(([^()]*[\u0600-\u06FF][^()]*)\)", row.iloc[2])
            if meaning_match:
                add_pair(pairs, meaning_match.group(1), row.iloc[1])
            add_pair(pairs, row.iloc[4], row.iloc[3])

    elif filename == "الرياضات والأدوات.csv":
        for _, row in raw.iloc[2:].iterrows():
            pairs.extend(pairs_from_inline(row.iloc[0]))
            add_pair(pairs, row.iloc[2], row.iloc[1])
            add_pair(pairs, row.iloc[4], f"{row.iloc[5]} {row.iloc[3]}".strip())

    elif filename == "العائلة.csv":
        for value in raw.iloc[3:].to_numpy().ravel():
            pairs.extend(pairs_from_inline(value))

    elif filename == "الممتلكات والانتماء.csv":
        # The first section has German noun, article, and Arabic translation.
        for _, row in raw.iterrows():
            if len(row) >= 3:
                article = row.iloc[1] if has_german(row.iloc[1]) and not has_arabic(row.iloc[1]) else ""
                add_pair(pairs, row.iloc[2], f"{article} {row.iloc[0]}".strip())
            for value in row:
                pairs.extend(pairs_from_inline(value))

    else:
        # Verb, pronoun, and grammar tables encode the meaning in cells such
        # as ``können (يستطيع)`` and ``ich (أنا)``.
        for value in raw.to_numpy().ravel():
            pairs.extend(pairs_from_inline(value))

    return to_dataframe(pairs)


def normalise_answer(text: str) -> str:
    return re.sub(r"[.!?،,;:’'\"-]", "", clean(text).casefold())


GERMAN_SPEECH_PLAYER = st.components.v2.component(
    "german_speech_player",
    html="""
    <div class="speech-player">
      <button id="play" type="button">تشغيل النطق الألماني</button>
      <button id="stop" type="button">إيقاف</button>
      <span id="status" role="status"></span>
    </div>
    """,
    css="""
    .speech-player { display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; }
    button { border: 0; border-radius: .5rem; padding: .55rem .8rem; cursor: pointer;
             background: var(--st-primary-color); color: white; font: inherit; }
    #stop { background: var(--st-secondary-background-color); color: var(--st-text-color); }
    #status { color: var(--st-text-color); font-size: .9rem; }
    """,
    js="""
    export default function (component) {
      const { data, parentElement } = component
      const play = parentElement.querySelector("#play")
      const stop = parentElement.querySelector("#stop")
      const status = parentElement.querySelector("#status")
      if (!play || !stop || !status) return
      if (!("speechSynthesis" in window)) {
        play.disabled = true; stop.disabled = true
        status.textContent = "النطق غير مدعوم في هذا المتصفح."
        return
      }
      play.onclick = () => {
        const text = data?.text ?? ""
        if (!text) return
        window.speechSynthesis.cancel()
        const utterance = new SpeechSynthesisUtterance(text)
        utterance.lang = "de-DE"
        utterance.rate = .85
        utterance.onstart = () => { status.textContent = "جارٍ النطق..." }
        utterance.onend = () => { status.textContent = "انتهى النطق." }
        utterance.onerror = () => { status.textContent = "تعذّر النطق الألماني في المتصفح." }
        window.speechSynthesis.speak(utterance)
      }
      stop.onclick = () => { window.speechSynthesis.cancel(); status.textContent = "تم الإيقاف." }
      return () => { play.onclick = null; stop.onclick = null }
    }
    """,
)


def german_speech_player(text: str, *, key: str) -> None:
    GERMAN_SPEECH_PLAYER(data={"text": text}, key=key)


def clear_results() -> None:
    st.session_state.quiz_results = None


list_files = {path.stem: path for path in sorted(LIST_DIRECTORY.glob("*.csv"))}
st.session_state.setdefault("quiz_results", None)

st.title("مراجعة المفردات الألمانية")
st.caption("اختر قائمة، استمع إلى الألمانية، ثم اكتب الترجمة الألمانية للكلمة العربية.")

if not list_files:
    st.error("لم تُعثر على ملفات القوائم الألمانية.")
    st.stop()

with st.sidebar:
    st.header("الإعدادات")
    selected_list = st.selectbox(
        "اختر قائمة المذاكرة",
        list(list_files),
        key="selected_german_list",
        on_change=clear_results,
    )

vocabulary = load_vocabulary(str(list_files[selected_list]))
if vocabulary.empty:
    st.warning("هذه القائمة تحتوي قواعد أو ملاحظات ولا تتضمن أزواجًا صالحة للاختبار عربي–ألماني.")
    st.stop()

batch_size = 20
batch_count = (len(vocabulary) + batch_size - 1) // batch_size
batch_number = st.selectbox(
    "مجموعة المراجعة والاختبار",
    range(1, batch_count + 1),
    format_func=lambda number: (
        f"المجموعة {number}: الكلمات {(number - 1) * batch_size + 1}–"
        f"{min(number * batch_size, len(vocabulary))}"
    ),
    key=f"batch_{selected_list}",
    on_change=clear_results,
)
batch_start = (batch_number - 1) * batch_size
batch = vocabulary.iloc[batch_start : batch_start + batch_size].copy()

st.caption(f"القائمة: {selected_list} — {len(vocabulary)} مفردة")
tab_words, tab_listen, tab_quiz = st.tabs(["الكلمات", "استمع بالألمانية", "اختبر نفسك"])

with tab_words:
    st.dataframe(batch, hide_index=True, height=480)

with tab_listen:
    st.subheader(f"استمع إلى المجموعة {batch_number}")
    st.caption("يستخدم التطبيق الصوت الألماني المحلي المثبّت في متصفحك ولا يحتاج إلى الإنترنت.")
    german_speech_player(". ".join(batch[GERMAN].tolist()), key=f"speech_{selected_list}_{batch_number}")

with tab_quiz:
    st.subheader(f"تسميع المجموعة {batch_number}")
    with st.form(f"quiz_{selected_list}_{batch_number}", clear_on_submit=False):
        answers = [
            st.text_input(
                f"{row_number}. {word[ARABIC]}",
                placeholder="اكتبها بالألمانية",
                key=f"answer_{selected_list}_{batch_number}_{row_number}",
            )
            for row_number, (_, word) in enumerate(batch.iterrows(), start=batch_start + 1)
        ]
        submitted = st.form_submit_button("صحّح هذه المجموعة", type="primary", icon=":material/fact_check:")

    if submitted:
        results = []
        for (_, word), answer in zip(batch.iterrows(), answers):
            expected = word[GERMAN]
            correct = normalise_answer(answer) == normalise_answer(expected)
            results.append(
                {
                    ARABIC: word[ARABIC],
                    "إجابتك": answer,
                    "الإجابة الصحيحة بالألمانية": expected,
                    "النتيجة": "✓ صحيح" if correct else "✗ خطأ",
                }
            )
        st.session_state.quiz_results = pd.DataFrame(results)

    results = st.session_state.quiz_results
    if results is not None:
        correct_count = int((results["النتيجة"] == "✓ صحيح").sum())
        st.metric("نتيجة المجموعة", f"{correct_count} / {len(batch)}")
        st.dataframe(results, hide_index=True)
