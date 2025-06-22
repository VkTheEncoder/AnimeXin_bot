import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from config import API_URL

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

def extract_italian_subtitle_url(embed_url: str) -> str | None:
    """
    Given a Dailymotion embed URL, pull the video ID and call the Dailymotion API
    to get the 'it' subtitle URL (usually a .vtt file).
    """
    m = re.search(r"/video/([^/?&]+)", embed_url)
    if not m:
        return None
    vid = m.group(1)
    api = f"https://api.dailymotion.com/video/{vid}?fields=subtitles"
    resp = requests.get(api)
    resp.raise_for_status()
    subs = resp.json().get("subtitles", {})
    return subs.get("it")  # this is a .vtt URL (if present)
