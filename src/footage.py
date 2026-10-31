"""Footage acquisition and caching using Pixabay API with provider interface."""

import abc
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("timereborn.footage")

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
FOOTAGE_CACHE_FILE = CACHE_DIR / "footage_cache.json"


class FootageProvider(abc.ABC):
    """Abstract interface for stock media providers (Pixabay, Pexels, etc.)."""

    @abc.abstractmethod
    def get_clip(self, keyword: str, orientation: str = "vertical") -> Optional[Dict[str, Any]]:
        """Find a video clip or fallback image for the keyword."""
        pass


class PixabayProvider(FootageProvider):
    """Pixabay stock footage provider with caching and exponential backoff."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("PIXABAY_API_KEY", "")
        self.cache: Dict[str, Any] = self._load_cache()

    def _load_cache(self) -> Dict[str, Any]:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if FOOTAGE_CACHE_FILE.exists():
            try:
                with open(FOOTAGE_CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read footage cache: {e}")
        return {}

    def _save_cache(self) -> None:
        try:
            with open(FOOTAGE_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save footage cache: {e}")

    def _request_with_backoff(self, url: str, params: Dict[str, Any], max_retries: int = 3) -> Optional[Dict[str, Any]]:
        backoff = 1.0
        for attempt in range(max_retries):
            try:
                resp = requests.get(url, params=params, timeout=12)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code in (429, 500, 502, 503):
                    logger.warning(f"Pixabay HTTP {resp.status_code}, retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    logger.warning(f"Pixabay API error {resp.status_code}: {resp.text}")
                    return None
            except requests.RequestException as e:
                logger.warning(f"Request error: {e}, retrying in {backoff}s...")
                time.sleep(backoff)
                backoff *= 2
        return None

    def search_video(self, keyword: str) -> Optional[str]:
        cache_key = f"video_{keyword}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        if not self.api_key:
            return None

        url = "https://pixabay.com/api/videos/"
        params = {
            "key": self.api_key,
            "q": keyword,
            "per_page": 5,
            "safesearch": "true",
            "video_type": "all",
        }
        data = self._request_with_backoff(url, params)
        if data and data.get("hits"):
            hits = data["hits"]
            for hit in hits:
                videos = hit.get("videos", {})
                # Prioritize medium or small for rapid downloading & optimal resolution
                for quality in ["medium", "small", "tiny", "large"]:
                    if quality in videos and videos[quality].get("url"):
                        video_url = videos[quality]["url"]
                        self.cache[cache_key] = video_url
                        self._save_cache()
                        return video_url
        return None

    def search_image(self, keyword: str, orientation: str = "vertical") -> Optional[str]:
        cache_key = f"image_{orientation}_{keyword}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        if not self.api_key:
            return None

        url = "https://pixabay.com/api/"
        pixabay_orientation = "vertical" if orientation == "vertical" else "horizontal"
        params = {
            "key": self.api_key,
            "q": keyword,
            "per_page": 5,
            "safesearch": "true",
            "image_type": "photo",
            "orientation": pixabay_orientation,
        }
        data = self._request_with_backoff(url, params)
        if data and data.get("hits"):
            image_url = data["hits"][0].get("largeImageURL")
            if image_url:
                self.cache[cache_key] = image_url
                self._save_cache()
                return image_url
        return None

    def get_clip(self, keyword: str, orientation: str = "vertical") -> Optional[Dict[str, Any]]:
        # 1. Try video
        vid_url = self.search_video(keyword)
        if vid_url:
            return {"type": "video", "url": vid_url, "keyword": keyword}

        # 2. Fallback to image with Ken Burns pan/zoom
        img_url = self.search_image(keyword, orientation)
        if img_url:
            return {"type": "image", "url": img_url, "keyword": keyword}

        return None


def download_file(url: str, destination: Path) -> Path:
    """Download a remote media file safely."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return destination

    resp = requests.get(url, stream=True, timeout=30)
    resp.raise_for_status()
    with open(destination, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return destination


def prepare_scene_footage(
    keywords: List[str],
    total_duration: float,
    temp_dir: Path,
    orientation: str = "vertical",
) -> List[Dict[str, Any]]:
    """Retrieve and download media for each scene keyword."""
    provider = PixabayProvider()
    clips_dir = temp_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    scenes: List[Dict[str, Any]] = []
    num_scenes = max(1, len(keywords))
    duration_per_scene = total_duration / num_scenes

    logger.info(f"Preparing {num_scenes} footage scenes (approx {duration_per_scene:.1f}s each)...")

    for i, kw in enumerate(keywords):
        clip_meta = provider.get_clip(kw, orientation=orientation)
        if clip_meta:
            url = clip_meta["url"]
            ext = ".mp4" if clip_meta["type"] == "video" else ".jpg"
            h = hashlib.md5(url.encode()).hexdigest()[:8]
            target_path = clips_dir / f"scene_{i}_{h}{ext}"
            try:
                download_file(url, target_path)
                scenes.append({
                    "path": target_path,
                    "type": clip_meta["type"],
                    "duration": duration_per_scene,
                    "keyword": kw,
                })
                continue
            except Exception as e:
                logger.warning(f"Failed to download footage for '{kw}': {e}")

        # Fallback if no media found or no API key provided
        scenes.append({
            "path": None,
            "type": "generated",
            "duration": duration_per_scene,
            "keyword": kw,
        })

    return scenes
