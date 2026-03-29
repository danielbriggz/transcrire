# ============================================================
# Transcrire — RSS Service
# ============================================================
# Wraps feedparser for all RSS feed operations.
# Raises typed exceptions — never returns None on failure.
#
# Usage:
#   from transcrire.services.rss import fetch_feed, find_episode
# ============================================================

from __future__ import annotations

import logging
from dataclasses import dataclass

import feedparser

logger = logging.getLogger(__name__)


# ============================================================
# EXCEPTIONS
# ============================================================

class FeedError(Exception):
    """Raised when an RSS feed cannot be loaded or parsed."""


class EpisodeNotFoundError(Exception):
    """Raised when the requested season/episode is not in the feed."""


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class FeedResult:
    """Parsed podcast feed metadata."""
    podcast_name: str
    rss_url:      str


@dataclass
class EpisodeAssets:
    """
    All fetchable assets for a single episode from its RSS entry.
    Fields are None if not present in the feed.
    """
    title:       str
    safe_title:  str
    season:      int
    episode:     int
    audio_url:   str | None
    cover_url:   str | None
    spotify_link: str | None


# ============================================================
# FEED FUNCTIONS
# ============================================================

def fetch_feed(rss_url: str) -> FeedResult:
    """
    Fetches and parses an RSS feed URL.
    Returns a FeedResult with the podcast name.
    Raises FeedError if the feed cannot be loaded.
    """
    try:
        feed = feedparser.parse(rss_url)
    except Exception as e:
        raise FeedError(f"Could not load RSS feed: {e}") from e

    if not feed.entries:
        raise FeedError(
            "RSS feed loaded but contains no episodes. "
            "Check the URL and your internet connection."
        )

    podcast_name = feed.feed.get("title", "Unknown Podcast")
    logger.info("Feed loaded", extra={"podcast": podcast_name, "url": rss_url})
    return FeedResult(podcast_name=podcast_name, rss_url=rss_url)


def find_episode(rss_url: str, season: int, episode: int) -> EpisodeAssets:
    """
    Searches an RSS feed for a specific season/episode.
    Returns an EpisodeAssets object with all available URLs.
    Raises EpisodeNotFoundError if no matching entry is found.
    Raises FeedError if the feed cannot be loaded.
    """
    try:
        feed = feedparser.parse(rss_url)
    except Exception as e:
        raise FeedError(f"Could not load RSS feed: {e}") from e

    for entry in feed.entries:
        try:
            entry_season  = int(entry.get("itunes_season",  0))
            entry_episode = int(entry.get("itunes_episode", 0))
        except (ValueError, TypeError):
            continue

        if entry_season != season or entry_episode != episode:
            continue

        # ---- Matched ----
        title      = entry.get("title", "Unknown Episode")
        safe_title = "".join(c for c in title if c not in r'\/:*?"<>|')

        # Audio URL — first enclosure with audio MIME type
        audio_url = None
        for link in entry.get("links", []):
            if link.get("type", "").startswith("audio"):
                audio_url = link.get("href")
                break

        # Cover art — episode-level preferred over feed-level
        cover_url = (
            entry.get("itunes_image", {}).get("href")
            or entry.get("image", {}).get("href")
            or entry.get("itunes_imageurl")
        )

        # Spotify / episode link
        spotify_link = entry.get("link")

        logger.info(
            "Episode found in feed",
            extra={"title": title, "season": season, "episode": episode},
        )

        return EpisodeAssets(
            title        = title,
            safe_title   = safe_title,
            season       = season,
            episode      = episode,
            audio_url    = audio_url,
            cover_url    = cover_url,
            spotify_link = spotify_link,
        )

    raise EpisodeNotFoundError(
        f"S{season}E{episode} not found in feed. "
        f"Check the season and episode numbers."
    )
