import polib
from deep_translator import GoogleTranslator

# 📁 English base file (IMPORTANT)
BASE_PO_FILE = "base.po"

# 🌍 Languages: Odoo code → Google code
languages = {
    "ar_SY": "ar",  # Arabic
    "es_ES": "es",  # Spanish
    "fr_FR": "fr",  # French
    "de_DE": "de",  # German
    "zh_CN": "zh-CN",  # Chinese
    "nl_NL": "nl",  # Dutch
    "it_IT": "it",  # Italian
    "ro_RO": "ro",  # Romanian
}

for odoo_lang, google_lang in languages.items():
    print(f"🌍 Translating to {odoo_lang}...")

    # 🔁 Always load fresh base file
    po = polib.pofile(BASE_PO_FILE)

    translator = GoogleTranslator(source="en", target=google_lang)

    for entry in po:
        if entry.msgid and entry.msgstr == "":
            try:
                entry.msgstr = translator.translate(entry.msgid)
            except Exception as e:
                print(f"❌ Error: {e}")
                entry.msgstr = entry.msgid

    # 💾 Save file
    output_file = f"{odoo_lang}.po"
    po.save(output_file)

    print(f"✅ Saved: {output_file}")

print("🎉 All translations completed!")
