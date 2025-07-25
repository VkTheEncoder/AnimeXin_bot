# utils.py
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from config import API_URL
import yt_dlp
import tempfile
import os

def search_series(query: str) -> list[dict]:
    resp = requests.get(f"{API_URL}/search", params={"query": query})
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        return data.get("data") or data.get("results") or []
    if isinstance(data, list):
        return data
    return []

def get_series_info(slug: str) -> dict:
    resp = requests.get(f"{API_URL}/donghua/info", params={"slug": slug})
    resp.raise_for_status()
    return resp.json()

def get_episode_videos(ep_slug: str) -> list[dict]:
    resp = requests.get(f"{API_URL}/episode/videos", params={"ep_slug": ep_slug})
    resp.raise_for_status()
    data = resp.json()
    return data.get("video_servers", [])

def extract_italian_subtitle_url(wrapper_url: str) -> str | None:
    """
    (Legacy) Scrape wrapper or Dailymotion API for subtitle URL.
    """
    # same as before
    try:
        r = requests.get(wrapper_url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for track in soup.find_all("track"):
            sr = (track.get("srclang") or "").lower()
            lb = (track.get("label") or "").lower()
            if "ita" in sr or "ita" in lb:
                src = track.get("src")
                if src:
                    if src.startswith("//"): return "https:" + src
                    if src.startswith("/"): return urljoin(wrapper_url, src)
                    return src
    except:
        pass
    m = re.search(r"/video/([^/?&]+)", wrapper_url)
    if not m: return None
    vid = m.group(1)
    try:
        api_url = f"https://api.dailymotion.com/video/{vid}/subtitles"
        r3 = requests.get(api_url)
        r3.raise_for_status()
        subs = r3.json().get("list") or r3.json().get("subtitles") or []
        for t in subs:
            url = t.get("url") or ""
            if t.get("language") == "it" or url.endswith("_subtitle_it.srt"):
                return url
    except:
        pass
    return None

def download_subtitles_with_ytdlp(video_url: str, lang: str = "it") -> bytes | None:
    """
    Use yt-dlp to fetch .srt subtitles for the given video_url.
    """
    ydl_opts = {
        "skip_download": True,
        "writesubtitles": True,
        "subtitlesformat": "srt",
        "subtitleslangs": [lang],
        "outtmpl": os.path.join(tempfile.gettempdir(), "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        subs = info.get("requested_subtitles") or info.get("subtitles") or {}
        if lang not in subs:
            return None
        ydl.download([video_url])
        vid = info.get("id")
        srt_path = os.path.join(tempfile.gettempdir(), f"{vid}.{lang}.srt")
        if not os.path.exists(srt_path):
            srt_path = os.path.join(tempfile.gettempdir(), f"{vid}.srt")
        if not os.path.exists(srt_path):
            return None
        with open(srt_path, "rb") as f:
            data = f.read()
        os.unlink(srt_path)
        return data
