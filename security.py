
import json
import os
from pathlib import Path


def get_config_dir():
    """Thư mục cấu hình riêng trên máy tính."""

    if os.name == "nt":
        base = Path(
            os.getenv("LOCALAPPDATA") or Path.home()
        )
        folder = base / "TikTokDownloaderPro"
    else:
        folder = Path.home() / ".tiktok-downloader-pro"

    folder.mkdir(parents=True, exist_ok=True)
    return folder


class AppSecurity:
    """Quản lý cấu hình và kiểm tra dữ liệu an toàn."""

    def __init__(self):
        self.config_file = get_config_dir() / "settings.json"

    def default_settings(self):
        return {
            "max_workers": 5,
            "output_dir": str(
                Path.home() / "Downloads" / "TikTokVideos"
            ),
            "auto_skip_duplicates": True,
            "export_format": "xlsx"
        }

    def load_settings(self):
        defaults = self.default_settings()

        if not self.config_file.exists():
            return defaults

        try:
            with self.config_file.open(
                "r",
                encoding="utf-8"
            ) as file:
                saved = json.load(file)

            if not isinstance(saved, dict):
                return defaults

            settings = defaults.copy()
            settings.update(saved)

            settings["max_workers"] = max(
                1,
                min(int(settings["max_workers"]), 5)
            )

            return settings

        except (OSError, ValueError, TypeError):
            return defaults

    def save_settings(self, settings):
        if not isinstance(settings, dict):
            raise ValueError("Cấu hình không hợp lệ.")

        defaults = self.default_settings()
        safe_settings = defaults.copy()

        safe_settings["max_workers"] = max(
            1,
            min(int(settings.get("max_workers", 5)), 5)
        )

        safe_settings["output_dir"] = str(
            Path(
                settings.get(
                    "output_dir",
                    defaults["output_dir"]
                )
            ).expanduser()
        )

        safe_settings["auto_skip_duplicates"] = bool(
            settings.get("auto_skip_duplicates", True)
        )

        safe_settings["export_format"] = "xlsx"

        self.config_file.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        temporary_file = self.config_file.with_suffix(".tmp")

        with temporary_file.open(
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                safe_settings,
                file,
                ensure_ascii=False,
                indent=4
            )

        temporary_file.replace(self.config_file)

        return True

    def get_output_dir(self):
        settings = self.load_settings()
        folder = Path(settings["output_dir"]).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    @staticmethod
    def validate_tiktok_url(url):
        url = (url or "").strip()

        if not url:
            return False

        if not url.startswith(("https://", "http://")):
            return False

        try:
            from urllib.parse import urlsplit

            host = (urlsplit(url).hostname or "").lower()

            return (
                host == "tiktok.com"
                or host.endswith(".tiktok.com")
                or host == "vm.tiktok.com"
                or host == "vt.tiktok.com"
            )

        except Exception:
            return False
