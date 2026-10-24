#!/usr/bin/env python3
"""Automatic translation for PhantomCloak broadcasted data and UI strings."""

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

CONFIG_FILE = Path.home() / ".phantomcloak" / "translation.json"

SUPPORTED_LANGUAGES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "pt": "Portuguese", "ja": "Japanese", "ko": "Korean", "zh": "Chinese",
    "ar": "Arabic", "hi": "Hindi", "ru": "Russian", "it": "Italian",
    "nl": "Dutch", "tr": "Turkish", "vi": "Vietnamese",
}

# Locale codes for browser profile alignment
LANG_TO_LOCALE = {
    "en": "en-US", "es": "es-ES", "fr": "fr-FR", "de": "de-DE",
    "pt": "pt-BR", "ja": "ja-JP", "ko": "ko-KR", "zh": "zh-CN",
    "ar": "ar-AE", "hi": "hi-IN", "ru": "ru-RU", "it": "it-IT",
    "nl": "nl-NL", "tr": "tr-TR", "vi": "vi-VN",
}


class TranslationEngine:
    def __init__(self):
        self.target_lang = "en"
        self.auto_translate = True
        self._cache: Dict[str, str] = {}
        self._load()

    def _load(self):
        if CONFIG_FILE.exists():
            try:
                cfg = json.loads(CONFIG_FILE.read_text())
                self.target_lang = cfg.get("target_lang", "en")
                self.auto_translate = cfg.get("auto_translate", True)
            except Exception:
                pass

    def _save(self):
        CONFIG_FILE.write_text(json.dumps({
            "target_lang": self.target_lang,
            "auto_translate": self.auto_translate,
            "locale": LANG_TO_LOCALE.get(self.target_lang, "en-US"),
        }, indent=2))

    def set_language(self, lang_code: str, auto: bool = True) -> Dict:
        if lang_code not in SUPPORTED_LANGUAGES:
            return {"status": "error", "message": f"Unsupported language: {lang_code}"}
        self.target_lang = lang_code
        self.auto_translate = auto
        self._cache.clear()
        self._save()
        return {
            "status": "ok",
            "language": lang_code,
            "language_name": SUPPORTED_LANGUAGES[lang_code],
            "locale": LANG_TO_LOCALE.get(lang_code, "en-US"),
            "auto_translate": auto,
        }

    def get_config(self) -> Dict:
        return {
            "target_lang": self.target_lang,
            "language_name": SUPPORTED_LANGUAGES.get(self.target_lang, "English"),
            "locale": LANG_TO_LOCALE.get(self.target_lang, "en-US"),
            "auto_translate": self.auto_translate,
            "supported": SUPPORTED_LANGUAGES,
        }

    def _translate_libre(self, text: str, target: str) -> str:
        if not text or target == "en":
            return text
        cache_key = f"{target}:{text}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        try:
            payload = urllib.parse.urlencode({
                "q": text, "source": "en", "target": target, "format": "text",
            }).encode()
            req = urllib.request.Request(
                "https://libretranslate.com/translate",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode())
                result = data.get("translatedText", text)
                self._cache[cache_key] = result
                return result
        except Exception:
            return text

    def translate(self, text: str) -> str:
        if not self.auto_translate or self.target_lang == "en":
            return text
        return self._translate_libre(text, self.target_lang)

    def translate_service(self, service: Dict) -> Dict:
        if not self.auto_translate or self.target_lang == "en":
            return service
        out = dict(service)
        out["name"] = self.translate(service.get("name", ""))
        if "desc" in service:
            out["desc"] = [self.translate(d) for d in service["desc"]]
        return out

    def translate_services(self, services: List[Dict]) -> List[Dict]:
        return [self.translate_service(s) for s in services]

    def apply_browser_locale(self, location_key: str) -> None:
        """Patch browser profile prefs for broadcast language alignment."""
        if self.target_lang == "en":
            return
        locale = LANG_TO_LOCALE.get(self.target_lang, "en-US")
        prefs_path = (
            Path(__file__).parent.parent / "profiles" / "browser" / location_key / "user.js"
        )
        if not prefs_path.parent.exists():
            return
        line = f'\nuser_pref("intl.accept_languages", "{locale}, {self.target_lang}");\n'
        line += f'user_pref("general.useragent.locale", "{locale}");\n'
        existing = prefs_path.read_text() if prefs_path.exists() else ""
        if "intl.accept_languages" not in existing:
            prefs_path.write_text(existing + line)