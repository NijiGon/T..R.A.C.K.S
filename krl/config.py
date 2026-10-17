"""Settings, read from environment variables (or a .env file in the project root)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get(name, default):
    value = os.environ.get(name)
    return default if value in (None, "") else value


@dataclass(frozen=True)
class Settings:
    # Database: a SQLite file
    db_path: str

    # Camera and counting
    source: str  # video file path, or an RTSP/HTTP stream URL
    gerbong: int  # carriage this camera covers
    seat_capacity: int
    line_position: float  # counting line, as a fraction of frame width
    line_margin_px: int  # dead zone around the line that a crossing must clear
    seat_freed_direction: str  # "Left" or "Right": the direction of travel that frees a seat

    # Detection
    model_path: str
    conf_threshold: float
    img_size: int
    duplicate_iou: float  # two tracks overlapping this much in one frame are one person


def load_settings():
    return Settings(
        db_path=_get("KRL_DB_PATH", "data/krl.db"),
        source=_get("KRL_SOURCE", "data/test.mp4"),
        gerbong=int(_get("KRL_GERBONG", "1")),
        seat_capacity=int(_get("KRL_SEAT_CAPACITY", "25")),
        line_position=float(_get("KRL_LINE_POSITION", "0.5")),
        line_margin_px=int(_get("KRL_LINE_MARGIN_PX", "20")),
        seat_freed_direction=_get("KRL_SEAT_FREED_DIRECTION", "Left"),
        model_path=_get("KRL_MODEL", "yolo11n.pt"),
        conf_threshold=float(_get("KRL_CONF", "0.2")),
        img_size=int(_get("KRL_IMG_SIZE", "1024")),
        duplicate_iou=float(_get("KRL_DUPLICATE_IOU", "0.5")),
    )
