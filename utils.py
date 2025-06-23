import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from config import API_URL
import yt_dlp
import tempfile
import os
from googletrans import Translator

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

def download_subtitles_with_ytdlp(video_url: str, lang: str = "it") -> bytes | None:
    """
    Use yt-dlp to fetch .srt subtitles for the given video_url.
    Returns raw .srt data as bytes, or None if not available.
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
        # Download the subtitle file
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

def translate_srt(srt_data: bytes, src: str = "it", dest: str = "en") -> bytes:
    """
    Translate an SRT (bytes) from src→dest and return new SRT bytes.
    """
    text = srt_data.decode("utf-8", errors="ignore")
    blocks = text.strip().split("\n\n")
    translator = Translator()
    new_blocks = []

    for block in blocks:
        lines = block.split("\n")
        if len(lines) < 3:
            continue
        idx = lines[0]
        timestamp = lines[1]
        content = "\n".join(lines[2:])
        # translate the caption text
        translated = translator.translate(content, src=src, dest=dest).text
        new_blocks.append(f"{idx}\n{timestamp}\n{translated}")

    return "\n\n".join(new_blocks).encode("utf-8")
