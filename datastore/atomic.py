"""עבר ל-moodle/atomic.py (2026-11-12), לליבה המשותפת שכל חלק משתמש בה (ראו docs/Modularity.md).

הקובץ הזה נשאר רק כדי שייבוא בשם הישן ימשיך לעבוד: זה אותו מודול בדיוק (גם monkeypatch בבדיקות פוגע בו).
קוד חדש מייבא מ-moodle.atomic.
"""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("moodle.atomic")
