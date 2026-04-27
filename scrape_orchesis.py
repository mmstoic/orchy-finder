#!/usr/bin/env python3
"""
Scrapes CU Orchesis YouTube channel, extracts song info from video descriptions,
and organizes by semester (Spring: Apr-Oct, Fall: Nov-Mar) into a CSV file.
"""

import ssl
import certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

import yt_dlp
import csv
import re
import sys
from datetime import datetime
from collections import defaultdict

CHANNEL_URL = "https://www.youtube.com/@CUorchesis/videos"
OUTPUT_FILE = "orchesis_songs.csv"

# Ordered from most to least specific to avoid false matches
MUSIC_PATTERNS = [
    r'[Mm]usic\s*:\s*(.+?)(?:\n|$)',
    r'[Ss]ong\s*:\s*(.+?)(?:\n|$)',
    r'[Ss]ong\s+[Bb]y\s*:\s*(.+?)(?:\n|$)',
    r'[Pp]erformed\s+[Tt]o\s*:\s*(.+?)(?:\n|$)',
    r'[Tt]rack\s*:\s*(.+?)(?:\n|$)',
    r'[Aa]udio\s*:\s*(.+?)(?:\n|$)',
]


def get_semester(upload_date_str):
    """Return (season, year) from an upload date string formatted YYYYMMDD.

    Spring covers April–October, Fall covers November–March.
    A January–March date belongs to the Fall of the *prior* calendar year.
    """
    try:
        date = datetime.strptime(upload_date_str, "%Y%m%d")
    except (ValueError, TypeError):
        return None

    month, year = date.month, date.year
    if 4 <= month <= 10:
        return ("Spring", year)
    elif month >= 11:
        return ("Fall", year)
    else:  # January–March → tail end of previous year's Fall
        return ("Fall", year - 1)


def semester_sort_key(key):
    """Chronological sort for (season, year) tuples.

    Fall YYYY (starts Nov YYYY) < Spring YYYY+1 (starts Apr YYYY+1).
    Maps to (year, 0) for Fall and (year, 1) for Spring so that
    Fall 2022 < Spring 2023 < Fall 2023 < Spring 2024.
    """
    if key is None:
        return (9999, 9)
    season, year = key
    return (year, 1 if season == "Spring" else 0)


def extract_songs(description):
    """Return a list of song strings found in the description."""
    if not description:
        return []

    seen = set()
    songs = []
    for pattern in MUSIC_PATTERNS:
        for match in re.finditer(pattern, description, re.MULTILINE):
            raw = match.group(1).strip()
            # Drop anything after common separators used as decoration
            raw = re.sub(r'\s*[|•·–—]\s*.*$', '', raw).strip()
            # Drop URLs that occasionally appear on the same line
            raw = re.sub(r'https?://\S+', '', raw).strip()
            if raw and raw.lower() not in seen:
                seen.add(raw.lower())
                songs.append(raw)

    return songs


class _SilentLogger:
    """Suppresses yt-dlp's error/warning output for unavailable videos."""
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def fetch_videos():
    """Fetch full metadata (including descriptions) for every channel video."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,   # full info so we get descriptions
        "ignoreerrors": True,
        "logger": _SilentLogger(),
    }

    print(f"Fetching videos from {CHANNEL_URL} …")
    print("(This may take a few minutes for large channels.)")

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(CHANNEL_URL, download=False)

    if not info or "entries" not in info:
        print("ERROR: Could not retrieve channel data.", file=sys.stderr)
        sys.exit(1)

    # entries can contain None for videos that failed to extract
    return [v for v in info["entries"] if v]


def main():
    videos = fetch_videos()
    total_videos = len(videos)
    print(f"Total videos found on channel: {total_videos}\n")

    semester_data = defaultdict(list)   # (season, year) → [row dicts]
    no_song_count = 0
    no_song_videos = []

    for video in videos:
        vid_id       = video.get("id", "")
        title        = video.get("title", "Unknown")
        description  = video.get("description") or ""
        upload_str   = video.get("upload_date", "")
        url          = (
            f"https://www.youtube.com/watch?v={vid_id}"
            if vid_id
            else video.get("webpage_url", "")
        )

        semester_key = get_semester(upload_str)
        if semester_key:
            semester_label = f"{semester_key[0]} {semester_key[1]}"
        else:
            semester_label = "Unknown"
            semester_key   = None

        songs = extract_songs(description)

        if not songs:
            no_song_count += 1
            no_song_videos.append((title, url))

        semester_data[semester_key].append({
            "semester":    semester_label,
            "title":       title,
            "songs":       " | ".join(songs) if songs else "N/A",
            "upload_date": upload_str,
            "url":         url,
        })

    # ── Write CSV ────────────────────────────────────────────────────────────
    sorted_keys = sorted(semester_data.keys(), key=semester_sort_key)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Semester", "Video Title", "Songs", "Upload Date", "URL"])

        for key in sorted_keys:
            entries = sorted(semester_data[key], key=lambda x: x["upload_date"])
            for row in entries:
                writer.writerow([
                    row["semester"],
                    row["title"],
                    row["songs"],
                    row["upload_date"],
                    row["url"],
                ])

    # ── Summary to stdout ────────────────────────────────────────────────────
    print("=" * 60)
    print(f"Total videos on channel : {total_videos}")
    print(f"Videos with no song info: {no_song_count}")

    if no_song_videos:
        print("\nVideos missing song info:")
        for title, url in no_song_videos:
            print(f"  • {title}")
            print(f"    {url}")

    print(f"\nSemester breakdown:")
    for key in sorted_keys:
        label = f"{key[0]} {key[1]}" if key else "Unknown"
        count = len(semester_data[key])
        with_songs = sum(1 for r in semester_data[key] if r["songs"] != "N/A")
        print(f"  {label:<20} {count:>3} video(s), {with_songs} with song info")

    print(f"\nOutput saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
