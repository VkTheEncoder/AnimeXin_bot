import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
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

def extract_italian_subtitle_url(wrapper_url: str) -> str | None:
    """
    1) Scrape the Animexin wrapper for <track srclang="it">.
    2) If none, request the Dailymotion embed with '?captions=it' to expose tracks.
    3) Finally, fall back to the Dailymotion subtitles API.
    """
    # —– 1) Animexin wrapper page —–
    try:
        r = requests.get(wrapper_url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
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

    # —– 2) Dailymotion embed with captions=it —–
    # ensure we have the embed URL
    if "/embed/video/" in wrapper_url:
        embed_url = wrapper_url
    else:
        # convert a normal Dailymotion URL to its embed form
        embed_url = wrapper_url.replace("/video/", "/embed/video/")
    embed_with_cc = embed_url + ("&" if "?" in embed_url else "?") + "captions=it"
    try:
        r2 = requests.get(embed_with_cc)
        r2.raise_for_status()
        soup2 = BeautifulSoup(r2.text, "html.parser")
        track2 = soup2.find("track", {"srclang": "it"})
        if track2 and track2.get("src"):
            return track2["src"]
    except Exception:
        pass

    # —– 3) Dailymotion subtitles API fallback —–
    m = re.search(r"/video/([^/?&]+)", wrapper_url)
    if not m:
        return None
    vid = m.group(1)
    try:
        api_url = f"https://api.dailymotion.com/video/{vid}/subtitles"
        r3 = requests.get(api_url)
        r3.raise_for_status()
        subs = r3.json().get("list") or r3.json().get("subtitles") or []
        for t in subs:
            if t.get("language") == "it" and t.get("url"):
                return t["url"]
    except Exception:
        pass

    return None
