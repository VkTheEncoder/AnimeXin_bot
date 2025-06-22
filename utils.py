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
    1) Scrape the Animexin wrapper page for any <track> whose
       srclang or label contains 'ita' (covers 'it', 'italiano').
    2) If none, hit the Dailymotion embed with '?captions=it'.
    3) If still none, call the Dailymotion subtitles API and
       pick the URL ending in '_subtitle_it.srt'.
    """
    # —– 1) Try wrapper page —
    try:
        r = requests.get(wrapper_url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for track in soup.find_all("track"):
            sr = (track.get("srclang") or "").lower()
            lb = (track.get("label") or "").lower()
            if "ita" in sr or "ita" in lb:
                src = track.get("src")
                if not src:
                    continue
                if src.startswith("//"):
                    return "https:" + src
                if src.startswith("/"):
                    return urljoin(wrapper_url, src)
                return src
    except Exception:
        pass

    # —– 2) Force captions=it on the Dailymotion embed —
    try:
        if "/embed/video/" in wrapper_url:
            embed = wrapper_url
        else:
            embed = wrapper_url.replace("/video/", "/embed/video/")
        url_cc = embed + ("&" if "?" in embed else "?") + "captions=it"
        r2 = requests.get(url_cc)
        r2.raise_for_status()
        soup2 = BeautifulSoup(r2.text, "html.parser")
        for track in soup2.find_all("track"):
            sr = (track.get("srclang") or "").lower()
            lb = (track.get("label") or "").lower()
            if "ita" in sr or "ita" in lb:
                return track["src"]
    except Exception:
        pass

    # —– 3) Fallback to Dailymotion API for .srt —
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
            url = t.get("url") or ""
            # pick the static .srt if available
            if t.get("language") in ("it",) or "_subtitle_it.srt" in url:
                return url
    except Exception:
        pass

    return None
