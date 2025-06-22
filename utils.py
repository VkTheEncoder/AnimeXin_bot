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
    # your API returns {"video_servers":[{server_name,video_url,embed_url},...]}
    return data.get("video_servers", [])

def extract_italian_subtitle_url(wrapper_url: str) -> str | None:
    """
    1) Scrape the Animexin wrapper page for a <track srclang="it"> URL.
    2) If none found, fall back to the Dailymotion
       /video/{id}/subtitles endpoint to get the static .srt link.
    """
    # --- 1) Try the wrapper page ---
    try:
        resp = requests.get(wrapper_url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        track = soup.find("track", {"srclang": "it"})
        if track and track.get("src"):
            src = track["src"]
            if src.startswith("//"):
                return "https:" + src
            if src.startswith("/"):
                return urljoin(wrapper_url, src)
            return src
    except Exception:
        pass

    # --- 2) Fallback to Dailymotion API ---
    m = re.search(r"/video/([^/?&]+)", wrapper_url)
    if not m:
        return None
    vid = m.group(1)

    try:
        # This endpoint returns a list of subtitle tracks, including .srt
        api_url = f"https://api.dailymotion.com/video/{vid}/subtitles"
        r2 = requests.get(api_url)
        r2.raise_for_status()
        data = r2.json()
        # Dailymotion may return { "list": […], "subtitles": […] } or just […]
        tracks = data.get("list") or data.get("subtitles") or data or []
        for t in tracks:
            if t.get("language") == "it" and t.get("url"):
                return t["url"]
    except Exception:
        pass

    return None
