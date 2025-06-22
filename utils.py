# utils.py

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from config import API_URL

def search_series(query: str):
    """Returns list of series for a search query."""
    resp = requests.get(f"{API_URL}/search", params={"query": query})
    resp.raise_for_status()
    return resp.json()

def get_series_info(slug: str):
    """Returns series metadata (including episodes)."""
    resp = requests.get(f"{API_URL}/donghua/info", params={"slug": slug})
    resp.raise_for_status()
    return resp.json()

def get_episode_videos(ep_slug: str):
    """Returns list of servers + embed URLs for an episode."""
    resp = requests.get(f"{API_URL}/episode/videos", params={"ep_slug": ep_slug})
    resp.raise_for_status()
    return resp.json()

def extract_italian_subtitle(embed_url: str) -> str | None:
    """
    Fetches the embed page and pulls out the <track> tag with srclang="it".
    Returns the full URL to the .vtt or .srt file, or None if not found.
    """
    resp = requests.get(embed_url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Look for a track element for Italian
    track = soup.find("track", {"srclang": "it"})
    if not track or not track.get("src"):
        return None

    src = track["src"]
    # Fix protocol-relative or relative URLs
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return urljoin(embed_url, src)
    return src
