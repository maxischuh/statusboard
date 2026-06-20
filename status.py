#!/usr/bin/env python3
"""
Render weather and MVV information on the Waveshare 7.5" e-paper display.

Private details such as timezone, coordinates, and MVV configuration live in
`local_settings.py`, which is intentionally gitignored. Copy the example file
and adjust it for your setup before running this script.
"""

import argparse
import base64
import json
import logging
import os
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

# ---------------------------------------------------------------------------
# Paths and private settings
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
LIB_DIR = BASE_DIR / "lib"
PIC_DIR = BASE_DIR / "pic"

if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

try:
    import local_settings as _local_settings  # type: ignore
except ImportError:
    _local_settings = None


def _require_setting(name: str):
    if _local_settings is None:
        raise SystemExit(
            "Missing local_settings.py. Copy local_settings.example.py, adjust it, and keep it out of git."
        )
    if not hasattr(_local_settings, name):
        raise SystemExit(f"local_settings.py must define `{name}`.")
    return getattr(_local_settings, name)


def _optional_setting(name: str, default):
    if _local_settings is None:
        return default
    return getattr(_local_settings, name, default)


def require_runtime_settings():
    _require_setting("TZ")
    _require_setting("LAT")
    _require_setting("LON")


TZ = str(_optional_setting("TZ", "Europe/Berlin"))
LAT = float(_optional_setting("LAT", 0.0))
LON = float(_optional_setting("LON", 0.0))
MVV_HTML = str(_optional_setting("MVV_HTML", "")).strip()

# Make sure the board uses the configured timezone.
os.environ["TZ"] = TZ
if hasattr(time, "tzset"):
    time.tzset()


# ---------------------------------------------------------------------------
# Display constants
# ---------------------------------------------------------------------------
W, H = 800, 480

CLOCK_REFRESH = 60
WX_REFRESH = 15 * 60
RAIN_REFRESH = 5 * 60
MVV_REFRESH = 120
FULL_REFRESH = 15 * 60

RAIN_THRESHOLD_MM = 0.1
RAIN_WINDOW_STEPS = 8

MVV_EFA_URL = "https://efa.mvv-muenchen.de/ng/XML_DM_REQUEST"
MVV_FETCH_LIMIT_MARGIN = 3
MVV_RETRY_BASE = 5 * 60
MVV_RETRY_MAX = 30 * 60
MVV_SUCCESS_LOG_INTERVAL = 30 * 60
STATUS_LOG_INTERVAL = 60 * 60

REQUEST_TIMEOUT = 10
DISPLAY_MAX_RETRIES = 2
DISPLAY_RECOVERY_SLEEP = 5
LOG_LEVEL = str(_optional_setting("LOG_LEVEL", "INFO")).upper()

OUTER_PAD = 16
PANEL_TOP = 14
CARD_BOTTOM = H - 18
PANEL_GAP = 14
LEFT_CARD_W = 310
CARD_TITLE_H = 44
CARD_PAD = 12
PANEL_PAD = 16

LEFT_CARD = (OUTER_PAD, PANEL_TOP, OUTER_PAD + LEFT_CARD_W, CARD_BOTTOM)
RIGHT_CARD = (LEFT_CARD[2] + PANEL_GAP, PANEL_TOP, W - OUTER_PAD, CARD_BOTTOM)
LEFT_CONTENT = (
    LEFT_CARD[0] + PANEL_PAD,
    LEFT_CARD[1] + PANEL_PAD,
    LEFT_CARD[2] - PANEL_PAD,
    LEFT_CARD[3] - PANEL_PAD,
)
RIGHT_CONTENT = (
    RIGHT_CARD[0] + CARD_PAD,
    RIGHT_CARD[1] + CARD_TITLE_H + CARD_PAD,
    RIGHT_CARD[2] - CARD_PAD,
    RIGHT_CARD[3] - CARD_PAD,
)

FONT_PATH = PIC_DIR / "Font.ttc"

try:
    RESAMPLE_LANCZOS = Image.Resampling.LANCZOS
    RESAMPLE_NEAREST = Image.Resampling.NEAREST
except AttributeError:
    RESAMPLE_LANCZOS = Image.LANCZOS
    RESAMPLE_NEAREST = Image.NEAREST


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    if not FONT_PATH.exists():
        raise SystemExit(f"Font file missing: {FONT_PATH}")
    return ImageFont.truetype(str(FONT_PATH), size)


FONT_TIME = _load_font(120)
FONT_DATE = _load_font(30)
FONT_BIG = _load_font(40)
FONT_SM = _load_font(26)
FONT_PANEL_TIME = _load_font(104)
FONT_PANEL_DATE = _load_font(24)
FONT_CARD_TITLE = _load_font(28)
FONT_TEMP = _load_font(78)
FONT_BODY = _load_font(24)
FONT_CAPTION = _load_font(20)
FONT_METRIC_LABEL = _load_font(18)
FONT_METRIC_VALUE = _load_font(22)


WMO_DE = {
    0: "Klar",
    1: "Überwiegend klar",
    2: "Teilweise bewölkt",
    3: "Bedeckt",
    45: "Nebel",
    48: "Nebel mit Reif",
    51: "Leichter Nieselregen",
    53: "Nieselregen",
    55: "Starker Nieselregen",
    56: "Gefr. Nieselregen",
    57: "Gefr. Nieselregen",
    61: "Leichter Regen",
    63: "Mäßiger Regen",
    65: "Starker Regen",
    66: "Gefrierender Regen",
    67: "Starker gefr. Regen",
    71: "Leichter Schneefall",
    73: "Mäßiger Schneefall",
    75: "Starker Schneefall",
    77: "Schneekörner",
    80: "Leichte Schauer",
    81: "Schauer",
    82: "Starke Schauer",
    85: "Leichte Schneeschauer",
    86: "Starke Schneeschauer",
    95: "Gewitter",
    96: "Gewitter m. kleinem Hagel",
    99: "Gewitter m. Hagel",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def de_date_local(now_ts=None) -> str:
    ts = time.time() if now_ts is None else now_ts
    s = time.strftime("%a %d %b %Y", time.localtime(ts))
    repl = {
        "Mon": "Mo",
        "Tue": "Di",
        "Wed": "Mi",
        "Thu": "Do",
        "Fri": "Fr",
        "Sat": "Sa",
        "Sun": "So",
        "Jan": "Jan",
        "Feb": "Feb",
        "Mar": "Mär",
        "Apr": "Apr",
        "May": "Mai",
        "Jun": "Jun",
        "Jul": "Jul",
        "Aug": "Aug",
        "Sep": "Sep",
        "Oct": "Okt",
        "Nov": "Nov",
        "Dec": "Dez",
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    return s


def fetch_current_weather():
    import requests

    url = "https://api.open-meteo.com/v1/dwd-icon"
    params = {
        "latitude": LAT,
        "longitude": LON,
        "timezone": TZ,
        "current": [
            "temperature_2m",
            "apparent_temperature",
            "precipitation",
            "weather_code",
            "wind_speed_10m",
        ],
    }
    resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    current = resp.json().get("current") or {}
    return {
        "time": current.get("time"),
        "temp": current.get("temperature_2m"),
        "feels": current.get("apparent_temperature"),
        "precip": current.get("precipitation"),
        "code": current.get("weather_code"),
        "wind": current.get("wind_speed_10m"),
    }


def fetch_rain_eta(threshold: float = RAIN_THRESHOLD_MM):
    import requests

    url = "https://api.open-meteo.com/v1/dwd-icon"
    params = {
        "latitude": LAT,
        "longitude": LON,
        "timezone": TZ,
        "minutely_15": ["precipitation"],
        "forecast_minutely_15": RAIN_WINDOW_STEPS,
    }
    resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json().get("minutely_15") or {}
    times = data.get("time") or []
    prec = data.get("precipitation") or []

    now = datetime.fromtimestamp(time.time())
    for stamp, amount in zip(times, prec):
        if amount is None:
            continue
        if amount >= threshold:
            eta = datetime.fromisoformat(stamp)
            minutes = int(round((eta - now).total_seconds() / 60))
            return max(minutes, 0)
    return None


# ---------------------------------------------------------------------------
# MVV widget helpers
# ---------------------------------------------------------------------------
def decode_mvv_monitor_config(html_text):
    if not html_text:
        return None

    candidates = []
    for pattern in (
        r'monitor-configuration=["\']([^"\']+)["\']',
        r'MONITOR_CONFIGURATION\s*=\s*["\']([^"\']+)["\']',
    ):
        candidates.extend(re.findall(pattern, html_text))
    candidates.extend(re.findall(r"[A-Za-z0-9+/=]{80,}", html_text))

    for raw in candidates:
        value = raw.strip()
        padding = "=" * (-len(value) % 4)
        for encoding in ("utf-8", "latin-1"):
            try:
                decoded = base64.b64decode(value + padding).decode(encoding)
                data = json.loads(decoded)
            except Exception:
                continue
            if isinstance(data, dict) and data.get("stations"):
                return data
    return None


def load_mvv_config(state):
    config = state.get("config")
    if config is not None:
        return config
    config = decode_mvv_monitor_config(MVV_HTML)
    if not config:
        raise RuntimeError("MVV Monitor-Konfiguration nicht lesbar")
    state["config"] = config
    logging.info(
        "MVV config loaded: stations=%s max_results=%s",
        len(config.get("stations") or []),
        config.get("maxResults", 5),
    )
    return config


def selected_line_keys(station_config):
    lines = station_config.get("lines") or station_config.get("allLines") or []
    keys = set()
    for line in lines:
        stateless = line.get("stateless")
        number = line.get("number")
        direction = line.get("direction")
        if stateless:
            keys.add(("stateless", stateless))
        if number:
            keys.add(("number", number))
        if number and direction:
            keys.add(("number_direction", number, direction))
    return keys


def line_is_selected(serving_line, keys):
    if not keys:
        return True
    number = serving_line.get("number") or serving_line.get("lineDisplay")
    direction = serving_line.get("direction")
    stateless = serving_line.get("stateless")
    return (
        ("stateless", stateless) in keys
        or ("number", number) in keys
        or ("number_direction", number, direction) in keys
    )


def fetch_mvv_station_departures(station_config, max_results):
    import urllib.parse
    import urllib.request

    station = station_config.get("station") or {}
    station_id = station.get("id") or station.get("stateless") or (station.get("ref") or {}).get("id")
    if not station_id:
        return []

    params = {
        "outputFormat": "JSON",
        "language": "de",
        "mode": "direct",
        "type_dm": "stop",
        "name_dm": station_id,
        "useRealtime": "1",
        "limit": str(max_results + MVV_FETCH_LIMIT_MARGIN),
    }
    url = MVV_EFA_URL + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    lead_time = int(station_config.get("leadTimeMinutes") or 0)
    line_keys = selected_line_keys(station_config)
    rows = []
    for departure in data.get("departureList") or []:
        serving_line = departure.get("servingLine") or {}
        if not line_is_selected(serving_line, line_keys):
            continue

        countdown = departure.get("countdown")
        try:
            minutes = int(countdown)
        except (TypeError, ValueError):
            continue
        if minutes < lead_time:
            continue

        line = serving_line.get("number") or serving_line.get("lineDisplay") or serving_line.get("name")
        destination = serving_line.get("direction") or departure.get("nameWO")
        if not line or not destination:
            continue
        rows.append(
            {
                "line": str(line),
                "destination": str(destination),
                "minutes": minutes,
                "platform": departure.get("platform") or departure.get("platformName"),
            }
        )
    return rows


def fetch_mvv_departures(config):
    max_results = int(config.get("maxResults") or 5)
    rows = []
    for station_config in config.get("stations") or []:
        rows.extend(fetch_mvv_station_departures(station_config, max_results))
    rows.sort(key=lambda row: row["minutes"])
    return rows[:max_results]


def reset_mvv_state(state, *, discard_cache=False):
    if discard_cache:
        for key in ("departures", "last_update_wall", "last_update", "config"):
            state.pop(key, None)


def mark_mvv_failure(state, now, message):
    failures = state.get("failures", 0) + 1
    state["failures"] = failures
    state["err"] = message
    state["next_attempt"] = now + min(MVV_RETRY_MAX, MVV_RETRY_BASE * failures)
    reset_mvv_state(state)


def maybe_log_mvv_success(state, rows):
    now = time.monotonic()
    if now - state.get("last_success_log", 0) >= MVV_SUCCESS_LOG_INTERVAL:
        logging.info("MVV update ok: rows=%s", len(rows))
        state["last_success_log"] = now


def get_mvv_departures_cached(state):
    if not MVV_HTML:
        state["err"] = "MVV Monitor nicht konfiguriert"
        return None, state["err"]

    now = time.monotonic()
    if now < state.get("next_attempt", 0):
        return state.get("departures"), state.get("err")

    if (now - state.get("last_update", 0)) > MVV_REFRESH:
        try:
            config = load_mvv_config(state)
            rows = fetch_mvv_departures(config)
            state["departures"] = rows
            state["last_update"] = now
            state["last_update_wall"] = time.time()
            state["failures"] = 0
            state["next_attempt"] = 0
            state["err"] = None
            maybe_log_mvv_success(state, rows)
        except Exception as exc:
            logging.warning("MVV data update failed: %s", exc)
            mark_mvv_failure(state, now, f"MVV: {exc}".splitlines()[0])

    return state.get("departures"), state.get("err")


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------
def text_width(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def text_height(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[3] - box[1]


def ellipsize(draw, text, font, max_width):
    if text_width(draw, text, font) <= max_width:
        return text
    suffix = "..."
    if text_width(draw, suffix, font) > max_width:
        return ""
    for idx in range(len(text), -1, -1):
        candidate = text[:idx].rstrip() + suffix
        if text_width(draw, candidate, font) <= max_width:
            return candidate
    return suffix


def wrap_lines(draw, text, font, max_width, max_lines):
    words = text.split()
    if not words:
        return []
    lines = []
    idx = 0
    while idx < len(words) and len(lines) < max_lines:
        line = words[idx]
        idx += 1
        while idx < len(words):
            candidate = f"{line} {words[idx]}"
            if text_width(draw, candidate, font) <= max_width:
                line = candidate
                idx += 1
            else:
                break
        if idx < len(words) and len(lines) == (max_lines - 1):
            remainder = " ".join([line] + words[idx:])
            line = ellipsize(draw, remainder, font, max_width)
            idx = len(words)
        lines.append(line)
    return lines


def rain_label(rain_eta):
    if rain_eta is None:
        return "Kein Regen in 2h"
    if rain_eta <= 0:
        return "Regen jetzt"
    return f"Regen in {rain_eta} min"


def draw_card_frame(draw, box, title, subtitle):
    x1, y1, x2, y2 = box
    draw.rectangle(box, outline=0, width=2)
    draw.line((x1, y1 + CARD_TITLE_H, x2, y1 + CARD_TITLE_H), fill=0, width=2)
    subtitle_w = 0
    if subtitle:
        subtitle = ellipsize(draw, subtitle, FONT_CAPTION, max(80, (x2 - x1) // 2))
        subtitle_w = text_width(draw, subtitle, FONT_CAPTION)
        draw.text((x2 - CARD_PAD - subtitle_w, y1 + 11), subtitle, font=FONT_CAPTION, fill=0)
    max_title = (x2 - x1) - (CARD_PAD * 2) - subtitle_w - 12
    draw.text((x1 + CARD_PAD, y1 + 6), ellipsize(draw, title, FONT_CARD_TITLE, max_title), font=FONT_CARD_TITLE, fill=0)


def draw_metric_row(draw, y, label, value, x1, x2):
    draw.text((x1, y + 2), label, font=FONT_METRIC_LABEL, fill=0)
    value = ellipsize(draw, value, FONT_METRIC_VALUE, max(70, x2 - x1 - 110))
    vw = text_width(draw, value, FONT_METRIC_VALUE)
    draw.text((x2 - vw, y), value, font=FONT_METRIC_VALUE, fill=0)


def draw_time_weather_panel(draw, weather, rain_eta, err, now_ts=None):
    draw.rectangle(LEFT_CARD, outline=0, width=2)
    x1, y1, x2, y2 = LEFT_CONTENT
    max_w = x2 - x1

    ts = time.time() if now_ts is None else now_ts
    now_text = time.strftime("%H:%M", time.localtime(ts))
    draw.text((x1, y1 - 4), now_text, font=FONT_PANEL_TIME, fill=0)

    date_text = de_date_local(now_ts)
    draw.text((x1 + 3, y1 + 92), ellipsize(draw, date_text, FONT_PANEL_DATE, max_w), font=FONT_PANEL_DATE, fill=0)
    draw.line((x1, y1 + 138, x2, y1 + 138), fill=0, width=2)

    y = y1 + 158
    if err and not weather:
        lines = wrap_lines(draw, f"Fehler: {err}", FONT_BODY, max_w, 6)
        for line in lines:
            draw.text((x1, y), line, font=FONT_BODY, fill=0)
            y += text_height(draw, line, FONT_BODY) + 4
        return

    temp = weather.get("temp") if weather else None
    temp_text = "--°C" if temp is None else f"{round(temp)}°C"
    draw.text((x1, y), temp_text, font=FONT_TEMP, fill=0)
    y += text_height(draw, temp_text, FONT_TEMP) + 14

    code = weather.get("code") if weather else None
    cond = WMO_DE.get(int(code) if code is not None else 3, "Keine Wetterdaten")
    for line in wrap_lines(draw, cond, FONT_BODY, max_w, 2):
        draw.text((x1, y), line, font=FONT_BODY, fill=0)
        y += text_height(draw, line, FONT_BODY) + 3

    badge = rain_label(rain_eta)
    bw = text_width(draw, badge, FONT_BODY) + 14
    bh = text_height(draw, badge, FONT_BODY) + 8
    if y + bh <= y2 - 96:
        draw.rectangle((x1, y + 2, x1 + bw, y + 2 + bh), fill=0)
        draw.text((x1 + 7, y + 6), badge, font=FONT_BODY, fill=255)
        y += bh + 10

    metric_rows = []
    if err:
        metric_rows.append(("Status", "Updatefehler"))
    feels = weather.get("feels") if weather else None
    if feels is not None:
        metric_rows.append(("Gefühlt", f"{round(feels)}°C"))
    wind = weather.get("wind") if weather else None
    if wind is not None:
        metric_rows.append(("Wind", f"{round(wind)} km/h"))
    precip = weather.get("precip") if weather else None
    if precip is not None:
        metric_rows.append(("Regen", f"{precip:.1f} mm"))

    if metric_rows:
        metric_y = max(y + 8, y2 - 95)
        draw.line((x1, metric_y - 10, x2, metric_y - 10), fill=0, width=1)
        for label, value in metric_rows[:3]:
            draw_metric_row(draw, metric_y, label, value, x1, x2)
            metric_y += 30


def normalize_departure_row(row):
    if isinstance(row, dict):
        return {
            "line": str(row.get("line") or ""),
            "destination": str(row.get("destination") or ""),
            "minutes": row.get("minutes"),
        }
    line, destination, minutes = row
    return {"line": str(line), "destination": str(destination), "minutes": minutes}


def draw_departures_table(draw, rows, box):
    x1, y1, x2, y2 = box
    width = x2 - x1
    draw.text((x1, y1), "Linie", font=FONT_CAPTION, fill=0)
    draw.text((x1 + 76, y1), "Ziel", font=FONT_CAPTION, fill=0)
    min_text = "Min"
    draw.text((x2 - text_width(draw, min_text, FONT_CAPTION), y1), min_text, font=FONT_CAPTION, fill=0)
    draw.line((x1, y1 + 28, x2, y1 + 28), fill=0, width=1)

    y = y1 + 40
    row_h = 44
    for raw_row in rows:
        if y + row_h > y2:
            break
        row = normalize_departure_row(raw_row)
        if not row["line"] or not row["destination"]:
            continue

        draw.rectangle((x1, y, x1 + 60, y + 28), fill=0)
        line_w = text_width(draw, row["line"], FONT_BODY)
        draw.text((x1 + max(4, (60 - line_w) // 2), y + 3), row["line"], font=FONT_BODY, fill=255)

        dest = ellipsize(draw, row["destination"], FONT_BODY, width - 150)
        draw.text((x1 + 76, y + 2), dest, font=FONT_BODY, fill=0)

        minutes = str(row["minutes"])
        minutes_w = text_width(draw, minutes, FONT_BODY)
        draw.text((x2 - minutes_w, y + 2), minutes, font=FONT_BODY, fill=0)

        draw.line((x1, y + row_h - 5, x2, y + row_h - 5), fill=0, width=1)
        y += row_h


def draw_mvv_card(draw, departures, mvv_err, mvv_state, title="MVG Abfahrten"):
    updated = mvv_state.get("last_update_wall")
    subtitle = f"Update {time.strftime('%H:%M', time.localtime(updated))}" if updated else "Lade..."
    draw_card_frame(draw, RIGHT_CARD, title, subtitle)
    x1, y1, x2, y2 = RIGHT_CONTENT
    if departures:
        draw_departures_table(draw, departures, (x1, y1, x2, y2))
        return

    if mvv_err:
        message = mvv_err
    elif updated:
        message = "Keine passenden Abfahrten."
    else:
        message = "MVG Daten werden geladen."
    lines = wrap_lines(draw, message, FONT_BODY, x2 - x1, 5)
    total_h = sum(text_height(draw, line, FONT_BODY) + 4 for line in lines)
    y = y1 + max(0, ((y2 - y1) - total_h) // 2)
    for line in lines:
        draw.text((x1, y), line, font=FONT_BODY, fill=0)
        y += text_height(draw, line, FONT_BODY) + 4


def draw_dashboard(
    img,
    weather,
    rain_eta,
    weather_err,
    departures,
    mvv_err,
    mvv_state,
    now_ts=None,
    departure_title="MVG Abfahrten",
):
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, H), fill=255)
    draw_time_weather_panel(d, weather, rain_eta, weather_err, now_ts)
    draw_mvv_card(d, departures, mvv_err, mvv_state, title=departure_title)


def create_dashboard_frame(
    weather,
    rain_eta,
    weather_err=None,
    departures=None,
    mvv_err=None,
    mvv_state=None,
    now_ts=None,
    departure_title="MVG Abfahrten",
):
    frame = Image.new("1", (W, H), 255)
    draw_dashboard(
        frame,
        weather,
        rain_eta,
        weather_err,
        departures,
        mvv_err,
        mvv_state or {},
        now_ts,
        departure_title=departure_title,
    )
    return frame


def simulate_screen(panel_img, scale=2):
    scale = max(1, int(scale))
    panel = panel_img.convert("L").resize((W * scale, H * scale), resample=RESAMPLE_NEAREST)
    screen = ImageOps.colorize(panel, black=(24, 24, 22), white=(240, 238, 225))

    bezel = 44 * scale
    shadow = 10 * scale
    canvas = Image.new("RGB", (screen.width + bezel * 2 + shadow, screen.height + bezel * 2 + shadow), (226, 224, 215))
    draw = ImageDraw.Draw(canvas)

    device_box = (shadow, shadow, canvas.width - shadow, canvas.height - shadow)
    draw.rounded_rectangle(device_box, radius=18 * scale, fill=(52, 54, 54), outline=(24, 24, 24), width=2 * scale)

    screen_box = (bezel, bezel, bezel + screen.width, bezel + screen.height)
    draw.rectangle(screen_box, fill=(240, 238, 225), outline=(18, 18, 18), width=2 * scale)
    canvas.paste(screen, (screen_box[0], screen_box[1]))
    return canvas


DEFAULT_PREVIEW_CITY = "munich"
PREVIEW_CITIES = {
    "munich": {
        "label": "Munich",
        "departure_title": "MVG Abfahrten",
        "scenarios": [
            {
                "name": "clear",
                "weather": {"temp": 21.6, "feels": 22.0, "precip": 0.0, "code": 2, "wind": 9.4},
                "rain_eta": None,
                "mvv_rows": [
                    ("U2", "Messestadt Ost", 3),
                    ("U2", "Feldmoching", 8),
                    ("19", "Pasing Bf.", 12),
                    ("54", "Münchner Freiheit", 18),
                    ("S8", "Flughafen München", 24),
                    ("X30", "Harras", 29),
                ],
            },
            {
                "name": "rain-soon",
                "weather": {"temp": 12.4, "feels": 10.8, "precip": 0.3, "code": 61, "wind": 27.2},
                "rain_eta": 18,
                "mvv_rows": [
                    ("16", "Romanplatz", 2),
                    ("17", "Amalienburgstraße", 6),
                    ("N17", "Effnerplatz", 11),
                    ("U1", "Olympia-Einkaufszentrum", 14),
                    ("Bus", "Ostbahnhof", 20),
                ],
            },
            {
                "name": "weather-error",
                "weather": None,
                "weather_err": "Open-Meteo timeout",
                "rain_eta": None,
                "mvv_rows": [
                    ("U6", "Klinikum Großhadern", 4),
                    ("U6", "Garching-Forschungszentrum", 7),
                    ("Bus", "Hauptbahnhof Nord", 15),
                    ("20", "Moosach Bf.", 21),
                ],
            },
        ],
    },
    "frankfurt-am-main": {
        "label": "Frankfurt am Main",
        "departure_title": "RMV Abfahrten",
        "scenarios": [
            {
                "name": "clear",
                "weather": {"temp": 19.8, "feels": 20.1, "precip": 0.0, "code": 2, "wind": 11.6},
                "rain_eta": None,
                "mvv_rows": [
                    ("U4", "Bockenheimer Warte", 4),
                    ("U5", "Preungesheim", 7),
                    ("S8", "Wiesbaden Hbf", 11),
                    ("S9", "Hanau Hbf", 15),
                    ("11", "Schießhüttenstraße", 19),
                    ("M32", "Ostbahnhof", 24),
                ],
            },
            {
                "name": "rain-soon",
                "weather": {"temp": 13.1, "feels": 11.9, "precip": 0.4, "code": 61, "wind": 23.7},
                "rain_eta": 16,
                "mvv_rows": [
                    ("U1", "Ginnheim", 3),
                    ("U2", "Bad Homburg Gonzenheim", 8),
                    ("16", "Offenbach Stadtgrenze", 12),
                    ("S3", "Darmstadt Hbf", 18),
                    ("M36", "Westbahnhof", 23),
                ],
            },
            {
                "name": "weather-error",
                "weather": None,
                "weather_err": "Open-Meteo timeout",
                "rain_eta": None,
                "mvv_rows": [
                    ("U4", "Enkheim", 5),
                    ("S1", "Rödermark-Ober Roden", 9),
                    ("12", "Schwanheim Rheinlandstraße", 14),
                    ("M34", "Bornheim Mitte", 21),
                ],
            },
        ],
    },
}


def preview_city_choices_help():
    return ", ".join(f"{city['label']} ({slug})" for slug, city in PREVIEW_CITIES.items())


def normalize_preview_city(value):
    normalized = value.strip().lower().replace("_", "-")
    aliases = {
        slug: slug
        for slug in PREVIEW_CITIES
    }
    aliases.update(
        {
            city["label"].strip().lower(): slug
            for slug, city in PREVIEW_CITIES.items()
        }
    )
    aliases["frankfurt"] = "frankfurt-am-main"
    return aliases.get(normalized)


def generate_previews(output_dir, scale=2, city_slug=DEFAULT_PREVIEW_CITY):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    now_ts = datetime(2026, 2, 18, 7, 42).timestamp()
    city = PREVIEW_CITIES[city_slug]

    written = []
    for spec in city["scenarios"]:
        mvv_state = {"last_update_wall": now_ts - 90}
        frame = create_dashboard_frame(
            spec.get("weather"),
            spec.get("rain_eta"),
            weather_err=spec.get("weather_err"),
            departures=spec["mvv_rows"],
            mvv_state=mvv_state,
            now_ts=now_ts,
            departure_title=city["departure_title"],
        )

        panel_path = output_dir / f"{spec['name']}-panel.png"
        screen_path = output_dir / f"{spec['name']}-screen.png"
        frame.save(panel_path)
        simulate_screen(frame, scale=scale).save(screen_path)
        written.extend([panel_path, screen_path])

    return written


def initialise_display(epd):
    epd.init()
    epd.Clear()
    epd.init_part()


def recover_display(epd):
    try:
        epd.sleep()
    except Exception:
        pass
    time.sleep(DISPLAY_RECOVERY_SLEEP)
    initialise_display(epd)


def push_frame_once(epd, frame, *, full_refresh: bool):
    buffer = epd.getbuffer(frame)
    if full_refresh:
        epd.init()
        epd.display(buffer)
        epd.init_part()
    else:
        epd.display_Partial(buffer, 0, 0, W, H)


def push_frame(epd, frame, *, full_refresh: bool):
    for attempt in range(DISPLAY_MAX_RETRIES + 1):
        try:
            if attempt:
                recover_display(epd)
            push_frame_once(epd, frame, full_refresh=full_refresh or bool(attempt))
            return True
        except Exception as exc:
            logging.warning(
                "Display refresh failed (%s/%s): %s",
                attempt + 1,
                DISPLAY_MAX_RETRIES + 1,
                exc,
            )
            if attempt < DISPLAY_MAX_RETRIES:
                time.sleep(DISPLAY_RECOVERY_SLEEP)
    logging.error("Display refresh failed after recovery attempts; keeping process alive")
    return False


def render_dashboard(epd, frame, weather, rain_eta, weather_err, mvv_state, *, full):
    departures, mvv_err = get_mvv_departures_cached(mvv_state)
    draw_dashboard(frame, weather, rain_eta, weather_err, departures, mvv_err, mvv_state)
    push_frame(epd, frame, full_refresh=full)
    return mvv_err


def safe_fetch(fetcher, label):
    try:
        return fetcher(), None
    except Exception as exc:
        logging.warning("%s fetch failed: %s", label, exc)
        return None, str(exc).splitlines()[0]


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    require_runtime_settings()
    from waveshare_epd import epd7in5_V2

    logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
    logging.info("Statusboard starting")

    epd = epd7in5_V2.EPD()
    frame = Image.new("1", (W, H), 255)

    for attempt in range(DISPLAY_MAX_RETRIES + 1):
        try:
            initialise_display(epd)
            break
        except Exception as exc:
            logging.warning(
                "Display initialisation failed (%s/%s): %s",
                attempt + 1,
                DISPLAY_MAX_RETRIES + 1,
                exc,
            )
            if attempt < DISPLAY_MAX_RETRIES:
                time.sleep(DISPLAY_RECOVERY_SLEEP)
    else:
        raise SystemExit("Failed to initialise display after recovery attempts.")

    weather_data, weather_err = safe_fetch(fetch_current_weather, "weather")
    rain_eta, rain_err = safe_fetch(fetch_rain_eta, "rain")
    weather_error = weather_err or rain_err

    mvv_state = {}
    now = time.monotonic()
    last_clock = now
    last_weather = now
    last_rain = now
    last_mvv = now
    last_full = now
    last_status_log = now

    render_dashboard(epd, frame, weather_data, rain_eta, weather_error, mvv_state, full=True)

    try:
        while True:
            try:
                now = time.monotonic()
                render_due = False
                full_render = False

                if now - last_clock >= CLOCK_REFRESH:
                    render_due = True

                if now - last_weather >= WX_REFRESH:
                    new_weather, weather_err = safe_fetch(fetch_current_weather, "weather")
                    if weather_err is None:
                        weather_data = new_weather
                    weather_error = weather_err or rain_err
                    last_weather = now
                    render_due = True

                if now - last_rain >= RAIN_REFRESH:
                    new_rain_eta, rain_err = safe_fetch(fetch_rain_eta, "rain")
                    if rain_err is None:
                        rain_eta = new_rain_eta
                    weather_error = weather_err or rain_err
                    last_rain = now
                    render_due = True

                if now - last_mvv >= MVV_REFRESH:
                    last_mvv = now
                    render_due = True

                if now - last_full >= FULL_REFRESH:
                    last_full = now
                    full_render = True
                    render_due = True

                if render_due:
                    render_dashboard(epd, frame, weather_data, rain_eta, weather_error, mvv_state, full=full_render)
                    last_clock = now

                if now - last_status_log >= STATUS_LOG_INTERVAL:
                    logging.info(
                        "Status heartbeat: weather_ok=%s rain_ok=%s mvv_rows=%s mvv_ok=%s",
                        weather_err is None,
                        rain_err is None,
                        len(mvv_state.get("departures") or []),
                        mvv_state.get("err") is None,
                    )
                    last_status_log = now
            except Exception as exc:
                logging.error("Loop iteration failed: %s", exc)
                traceback.print_exc()
                reset_mvv_state(mvv_state)
                time.sleep(DISPLAY_RECOVERY_SLEEP)

            time.sleep(1)

    except KeyboardInterrupt:
        logging.info("Stopping slideshow...")
    except Exception as exc:
        logging.error("Unhandled error: %s", exc)
        traceback.print_exc()
    finally:
        reset_mvv_state(mvv_state, discard_cache=True)
        try:
            epd.sleep()
        except Exception:
            pass


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Render the e-paper statusboard.")
    parser.add_argument(
        "--preview",
        nargs="?",
        const=str(BASE_DIR / "previews"),
        default=None,
        metavar="DIR",
        help="Generate simulated screen PNGs in DIR and exit.",
    )
    parser.add_argument(
        "--preview-scale",
        type=int,
        default=2,
        help="Scale factor for simulated screen images.",
    )
    parser.add_argument(
        "--preview-city",
        default=DEFAULT_PREVIEW_CITY,
        metavar="CITY",
        help=f"Preview city. Available: {preview_city_choices_help()}. Default: Munich.",
    )
    args = parser.parse_args(argv)
    city_slug = normalize_preview_city(args.preview_city)
    if city_slug is None:
        parser.error(f"unknown preview city {args.preview_city!r}; choose one of: {preview_city_choices_help()}")
    args.preview_city = city_slug
    return args


def cli(argv=None):
    args = parse_args(argv)
    if args.preview is not None:
        written = generate_previews(args.preview, scale=args.preview_scale, city_slug=args.preview_city)
        for path in written:
            print(path)
        return
    main()


if __name__ == "__main__":
    cli()
