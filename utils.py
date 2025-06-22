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
    # the API returns {"video_servers":[{server_name,video_url,embed_url},...]}
    return data.get("video_servers", [])

def extract_italian_subtitle_url(wrapper_url: str) -> str | None:
    """
    Scrape the Animexin wrapper page (not the raw Dailymotion iframe)
    to find the <track srclang="it"> URL (usually .vtt or .srt).
    """
    resp = requests.get(wrapper_url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    track = soup.find("track", {"srclang": "it"})
    if not track or not track.get("src"):
        return None
    src = track["src"]
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return urljoin(wrapper_url, src)
    return src
