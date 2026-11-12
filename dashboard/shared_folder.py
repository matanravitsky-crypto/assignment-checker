"""עבר ל-moodle/shared_folder.py (2026-11-12), לליבה המשותפת שכל חלק משתמש בה (ראו docs/Modularity.md).

הקובץ הזה נשאר רק כדי שייבוא בשם הישן ימשיך לעבוד: זה אותו מודול בדיוק (גם monkeypatch בבדיקות פוגע בו).
קוד חדש מייבא מ-moodle.shared_folder.
"""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("moodle.shared_folder")
