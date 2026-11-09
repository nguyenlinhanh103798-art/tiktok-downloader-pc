
import re
import time
import yt_dlp


class TikTokAccountManager:
    """
    Lấy danh sách video từ tài khoản TikTok công khai.
    Không yêu cầu mật khẩu hoặc cookie tài khoản.
    """

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    def __init__(self):
        self.last_error = ""

    def normalize_username(self, username):
        username = (username or "").strip()

        if not username:
            raise ValueError("Bạn chưa nhập tài khoản TikTok.")

        username = username.replace(
            "https://www.tiktok.com/", ""
        )
        username = username.replace(
            "http://www.tiktok.com/", ""
        )
        username = username.replace(
            "https://tiktok.com/", ""
        )
        username = username.strip("/")

        if username.startswith("@"):
            username = username[1:]

        username = username.split("/")[0].split("?")[0]

        if not re.fullmatch(r"[A-Za-z0-9._]{1,50}", username):
            raise ValueError(
                "Tên tài khoản không hợp lệ. "
                "Hãy nhập @username hoặc link trang cá nhân."
            )

        return username

    def get_account_url(self, username):
        name = self.normalize_username(username)
        return f"https://www.tiktok.com/@{name}"

    def build_options(self, limit):
        return {
            "extract_flat": "in_playlist",
            "skip_download": True,

            # Không âm thầm bỏ qua lỗi
            "ignoreerrors": False,

            "quiet": True,
            "no_warnings": False,
            "verbose": True,

            "playlistend": limit if limit > 0 else None,

            "socket_timeout": 30,
            "retries": 3,
            "extractor_retries": 3,
            "fragment_retries": 3,

            "http_headers": {
                "User-Agent": self.USER_AGENT,
                "Referer": "https://www.tiktok.com/",
                "Accept-Language": "en-US,en;q=0.9",
            },

            "logger": self,
        }

    def debug(self, message):
        pass

    def warning(self, message):
        self.last_error = str(message)

    def error(self, message):
        self.last_error = str(message)

    def get_videos(self, username, max_videos=100):
        self.last_error = ""

        name = self.normalize_username(username)
        account_url = self.get_account_url(name)

        try:
            limit = max(0, int(max_videos))
        except (TypeError, ValueError):
            raise ValueError("Số lượng video không hợp lệ.")

        options = self.build_options(limit)

        last_exception = None

        # Thử tối đa 2 lần nếu lỗi mạng tạm thời
        for attempt in range(2):
            try:
                self.last_error = ""

                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(
                        account_url,
                        download=False
                    )

                if not info:
                    raise RuntimeError(
                        "TikTok không trả về dữ liệu tài khoản."
                    )

                entries = info.get("entries")

                if entries is None:
                    entries = [info]

                videos = []
                seen = set()

                for entry in entries:
                    if not entry:
                        continue

                    video_id = str(entry.get("id") or "")

                    video_url = (
                        entry.get("webpage_url")
                        or entry.get("original_url")
                        or entry.get("url")
                        or ""
                    )

                    # Tạo link từ ID video nếu cần
                    if video_id.isdigit():
                        if "/video/" not in video_url:
                            video_url = (
                                f"https://www.tiktok.com/"
                                f"@{name}/video/{video_id}"
                            )

                    if (
                        not video_url.startswith("http")
                        or "/video/" not in video_url
                    ):
                        continue

                    if video_url in seen:
                        continue

                    seen.add(video_url)

                    videos.append({
                        "url": video_url,
                        "id": video_id,
                        "title": entry.get("title") or "",
                        "duration": entry.get("duration"),
                    })

                    if limit and len(videos) >= limit:
                        break

                if not videos:
                    raise RuntimeError(
                        "TikTok đã trả về dữ liệu nhưng không tìm "
                        "thấy video nào. Tài khoản có thể riêng tư, "
                        "không có video công khai hoặc TikTok "
                        "đang giới hạn truy cập."
                    )

                self.last_error = ""
                return videos

            except Exception as error:
                last_exception = error
                self.last_error = str(error)

                if attempt == 0:
                    time.sleep(2)

        error_text = str(last_exception)

        if "secondary user ID" in error_text.lower():
            message = (
                "TikTok không cho yt-dlp lấy mã định danh tài khoản "
                "để đọc danh sách video. Đây là lỗi trích xuất hồ sơ "
                "từ TikTok, không phải lỗi nhập tên tài khoản. "
                "Hãy thử lại sau hoặc dùng link video trực tiếp."
            )

        elif "private" in error_text.lower():
            message = (
                "Không thể lấy video từ tài khoản riêng tư "
                "hoặc nội dung bị giới hạn."
            )

        elif "429" in error_text or "Too Many Requests" in error_text:
            message = (
                "TikTok đang giới hạn số lần truy cập. "
                "Hãy chờ một lúc rồi thử lại."
            )

        else:
            message = (
                "Không lấy được danh sách video TikTok.\n\n"
                "Chi tiết lỗi:\n" + error_text
            )

        self.last_error = message
        raise RuntimeError(message) from last_exception

    def get_video_urls(self, username, max_videos=100):
        """
        Trả về danh sách link video dạng chuỗi.
        Giữ tương thích với main.py hiện tại.
        """

        videos = self.get_videos(username, max_videos)

        return [
            video["url"]
            for video in videos
        ]
