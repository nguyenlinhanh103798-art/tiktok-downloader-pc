
import re
import yt_dlp


class TikTokAccountManager:
    """Lấy danh sách video từ tài khoản TikTok công khai."""

    def __init__(self):
        self.last_error = ""

    def normalize_username(self, username):
        username = (username or "").strip()

        if not username:
            raise ValueError("Bạn chưa nhập tên tài khoản.")

        username = username.replace("https://www.tiktok.com/", "")
        username = username.replace("http://www.tiktok.com/", "")
        username = username.strip("/")

        if username.startswith("@"):
            username = username[1:]

        if username.startswith("@"):
            username = username[1:]

        username = username.split("/")[0].split("?")[0]

        if not re.fullmatch(r"[A-Za-z0-9._]{1,50}", username):
            raise ValueError("Tên tài khoản TikTok không hợp lệ.")

        return username

    def get_account_url(self, username):
        username = self.normalize_username(username)
        return f"https://www.tiktok.com/@{username}"

    def get_videos(self, username, max_videos=100):
        """
        Lấy link video từ tài khoản công khai.

        max_videos = 0 nghĩa là không giới hạn số video.
        Việc lấy danh sách phụ thuộc khả năng truy cập của TikTok.
        """

        self.last_error = ""

        try:
            account_url = self.get_account_url(username)

            limit = max(0, int(max_videos))

            options = {
                "extract_flat": "in_playlist",
                "skip_download": True,
                "quiet": True,
                "no_warnings": True,
                "ignoreerrors": True,
                "playlistend": limit if limit > 0 else None,
                "socket_timeout": 30,
            }

            videos = []
            seen = set()

            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(
                    account_url,
                    download=False
                )

            if not info:
                raise RuntimeError(
                    "TikTok không trả về danh sách video."
                )

            entries = info.get("entries")

            if entries is None:
                entries = [info]

            for entry in entries:
                if not entry:
                    continue

                video_url = (
                    entry.get("webpage_url")
                    or entry.get("original_url")
                    or entry.get("url")
                )

                video_id = entry.get("id")

                if video_url and video_url.startswith("http"):
                    if "/video/" not in video_url:
                        if video_id and str(video_id).isdigit():
                            video_url = (
                                f"https://www.tiktok.com/@"
                                f"{self.normalize_username(username)}"
                                f"/video/{video_id}"
                            )
                        else:
                            continue

                elif video_id and str(video_id).isdigit():
                    video_url = (
                        f"https://www.tiktok.com/@"
                        f"{self.normalize_username(username)}"
                        f"/video/{video_id}"
                    )

                else:
                    continue

                if video_url not in seen:
                    seen.add(video_url)

                    videos.append({
                        "url": video_url,
                        "id": str(video_id or ""),
                        "title": entry.get("title", ""),
                        "duration": entry.get("duration"),
                    })

                if limit and len(videos) >= limit:
                    break

            if not videos:
                raise RuntimeError(
                    "Không tìm thấy video. Tài khoản có thể riêng tư, "
                    "không có video công khai hoặc TikTok đang chặn truy cập."
                )

            return videos

        except Exception as error:
            self.last_error = str(error)
            raise RuntimeError(self.last_error) from error

    def get_video_urls(self, username, max_videos=100):
        """Trả về danh sách link video dạng văn bản."""

        videos = self.get_videos(username, max_videos)

        return [
            video["url"]
            for video in videos
        ]
