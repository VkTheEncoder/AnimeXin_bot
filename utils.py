# utils.py

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from config import API_URL

def search_series(query: str) -> list[dict]:
    """Returns a list of series for a search query."""
    resp = requests.get(f"{API_URL}/search", params={"query": query})
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, dict):
        return data.get("data") or data.get("results") or []
    if isinstance(data, list):
        return data
    return []

def get_series_info(slug: str) -> dict:
    """Returns series metadata (including episodes)."""
    resp = requests.get(f"{API_URL}/donghua/info", params={"slug": slug})
    resp.raise_for_status()
    return resp.json()

def get_episode_videos(ep_slug: str) -> list[dict]:
    """Fetches `/episode/videos` and normalizes into a list of dicts."""
    resp = requests.get(f"{API_URL}/episode/videos", params={"ep_slug": ep_slug})
    resp.raise_for_status()
    data = resp.json()

    # If it's a dict of simple string→string, treat keys as server names
    if isinstance(data, dict) and all(isinstance(v, str) for v in data.values()):
        return [{"server_name": k, "video_url": v} for k, v in data.items()]

    # If it’s wrapped in another key
    if isinstance(data, dict):
        for possible in ("servers", "data", "videos"):
            if isinstance(data.get(possible), list):
                data = data[possible]
                break

    # Now if it's a list of dict, verify shape
    if isinstance(data, list):
        normalized = []
        for item in data:
            if not isinstance(item, dict):
                continue
            # Try common field names
            url = item.get("video_url") or item.get("url") or item.get("embed")
            name = item.get("server_name") or item.get("server") or item.get("name")
            if url:
                normalized.append({"server_name": name or "server", "video_url": url})
        return normalized

    # Fallback
    return []

def extract_italian_subtitle(embed_url: str) -> str | None:
    """
    Fetches the embed page and pulls out the <track> tag with srclang="it".
    Returns the full URL to the subtitle file, or None if not found.
    """
    resp = requests.get(embed_url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    track = soup.find("track", {"srclang": "it"})
    if not track or not track.get("src"):
        return None

    src = track["src"]
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return urljoin(embed_url, src)
    return src
