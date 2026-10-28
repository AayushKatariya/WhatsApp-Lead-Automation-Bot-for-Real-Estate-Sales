"""Checks your Gemini API key and the AI fallback on sample projects. Nothing is sent to WhatsApp.

    GEMINI_API_KEY=your-key python tools/try_ai.py                       (a few sample questions)
    GEMINI_API_KEY=your-key python tools/try_ai.py "Is there a pool?"    (your own question)
Optional: GEMINI_MODEL=gemini-3.8-flash to try another model.
Prints the model's raw reply and what the bot would do with it.
"""

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from ai import DEFAULT_MODEL, Gemini, build_facts, sales_topics  # noqa: E402
from demo_conversations import FAQ, SITES  # noqa: E402

SAMPLES = [
    "Is there a swimming pool in Green Valley?",
    "Site office kab khula rehta hai?",
    "Do you allow pets?",
    "How much is a 2 BHK?",
]


def render(text, site):
    values = {"site_name": site["name"] if site else "", "sales_name": site["sales_name"] if site else "our team",
              "availability": site["availability"] if site else "", "company": "Shree Builders", "name": ""}
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


def main():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        sys.exit("Set GEMINI_API_KEY first (see the top of this file).")
    logging.basicConfig(level=logging.INFO, format="  (%(message)s)")
    model = os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_MODEL
    gemini = Gemini(key, model)
    facts = build_facts(SITES, FAQ, render)
    topics = sales_topics(FAQ)
    print(f"Model {model}; {len(facts)} facts from the sample Sheet; sales-team topics: {', '.join(topics)}\n")
    for question in sys.argv[1:] or SAMPLES:
        answer, raw = gemini.ask(question, facts, topics, project="Green Valley Residency", company="Shree Builders")
        print(f"Q: {question}")
        print(f"   Model replied: {raw.strip() or '(nothing: see the error above)'}")
        print(f"   Bot would: {'SEND  ' + answer if answer else 'HAND OFF to sales'}\n")


if __name__ == "__main__":
    main()
