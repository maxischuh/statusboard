#!/usr/bin/env python3
"""
Cycle weather and MVV information on the Waveshare 7.5" e-paper display.

Private details such as timezone, coordinates, and MVV configuration live in
`local_settings.py`, which is intentionally gitignored. Copy the example file
and adjust it for your setup before running this script.
"""

import logging
import os
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Paths and private settings
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
LIB_DIR = BASE_DIR / "lib"
PIC_DIR = BASE_DIR / "pic"

if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

try:
    import local_settings as _local  # type: ignore
except ImportError as exc:
    raise SystemExit(
        "Missing local_settings.py. Copy local_settings.example.py, adjust it, and keep it out of git."
    ) from exc


def _require_setting(name: str):
    if not hasattr(_local, name):
        raise SystemExit(f"local_settings.py must define `{name}`.")
    return getattr(_local, name)


TZ = _require_setting("TZ")
LAT = float(_require_setting("LAT"))
LON = float(_require_setting("LON"))
MVV_HTML = getattr(_local, "MVV_HTML", "").strip()
del _local

from waveshare_epd import epd7in5_V2  # noqa: E402

# Make sure the board uses the configured timezone.
os.environ["TZ"] = TZ
if hasattr(time, "tzset"):
    time.tzset()


# ---------------------------------------------------------------------------
# Display constants
# ---------------------------------------------------------------------------
W, H = 800, 480

SLIDE_INTERVAL = 60
WX_REFRESH = 15 * 60
RAIN_REFRESH = 5 * 60
MVV_REFRESH = 120
FULL_REFRESH = 60 * 60

RAIN_THRESHOLD_MM = 0.1
RAIN_WINDOW_STEPS = 8

PROG_BOX = (0, H - 10, W, H)
PROG_SEG_W = 10
PROG_GAP = 6
PROG_BASE_THICK = 1
PROG_FILL_THICK = 3
TOP_ERASE_H = 2

FONT_PATH = PIC_DIR / "Font.ttc"


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    if not FONT_PATH.exists():
        raise SystemExit(f"Font file missing: {FONT_PATH}")
    return ImageFont.truetype(str(FONT_PATH), size)


FONT_TIME = _load_font(120)
FONT_DATE = _load_font(30)
FONT_BIG = _load_font(40)
FONT_SM = _load_font(26)


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
def de_date_local() -> str:
    s = time.strftime("%a %d %b %Y", time.localtime())
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
    resp = requests.get(url, params=params, timeout=10)
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
    url = "https://api.open-meteo.com/v1/dwd-icon"
    params = {
        "latitude": LAT,
        "longitude": LON,
        "timezone": TZ,
        "minutely_15": ["precipitation"],
        "forecast_minutely_15": RAIN_WINDOW_STEPS,
    }
    resp = requests.get(url, params=params, timeout=10)
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
def init_browser():
    if not MVV_HTML:
        raise RuntimeError("MVV HTML snippet not configured.")

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import TimeoutException

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
    tmp.write(MVV_HTML.encode("utf-8"))
    tmp.flush()
    tmp.close()

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--remote-allow-origins=*")
    opts.add_argument("--window-size=800,480")
    try:
        opts.page_load_strategy = "none"
    except Exception:
        pass

    svc_path = "/usr/bin/chromedriver"
    service = Service(svc_path) if os.path.exists(svc_path) else Service()
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(120)
    try:
        driver.get("file://" + tmp.name)
    except TimeoutException:
        pass

    return driver, tmp.name


def grab_mvv_png(driver, out_png):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".mvv-departure-monitor"))
    )
    driver.find_element(By.CSS_SELECTOR, ".mvv-departure-monitor").screenshot(out_png)


def get_mvv_image_cached(state):
    if not MVV_HTML:
        canvas = Image.new("1", (W, H), 255)
        d = ImageDraw.Draw(canvas)
        d.text(
            (40, H // 2 - 20),
            "MVV Monitor nicht konfiguriert",
            font=FONT_SM,
            fill=0,
        )
        state["err"] = "MVV Monitor nicht konfiguriert"
        return canvas, state["err"]

    now = time.monotonic()
    if "driver" not in state:
        try:
            state["driver"], state["html_path"] = init_browser()
        except Exception as exc:
            state["err"] = f"MVV: {exc}".splitlines()[0]
            return Image.new("1", (W, H), 255), state["err"]
        state["last_reload"] = 0.0

    if (now - state.get("last_shot", 0)) > MVV_REFRESH:
        try:
            if (now - state.get("last_reload", 0)) > 600:
                from selenium.common.exceptions import TimeoutException

                try:
                    state["driver"].get("file://" + state["html_path"])
                except TimeoutException:
                    pass
                state["last_reload"] = now

            png = state.get("png_path") or tempfile.mktemp(suffix=".png")
            grab_mvv_png(state["driver"], png)
            state["png_path"] = png
            state["last_shot"] = now
            state["err"] = None
        except Exception as exc:
            state["err"] = f"MVV: {exc}".splitlines()[0]

    canvas = Image.new("1", (W, H), 255)
    if state.get("png_path") and os.path.exists(state["png_path"]):
        src = Image.open(state["png_path"]).convert("L")
        src.thumbnail((W - 80, H - 120))
        x = (W - src.width) // 2
        y = (H - src.height) // 2
        canvas.paste(src.convert("1"), (x, y))
        d = ImageDraw.Draw(canvas)
        d.rectangle((x - 10, y - 10, x + src.width + 10, y + src.height + 10), outline=0, width=2)
    else:
        d = ImageDraw.Draw(canvas)
        d.text((40, H // 2 - 20), state.get("err") or "MVV Monitor nicht verfügbar", font=FONT_SM, fill=0)
    return canvas, state.get("err")


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------
def draw_progress(img, frac: float):
    frac = max(0.0, min(1.0, frac))
    d = ImageDraw.Draw(img)
    d.rectangle(PROG_BOX, fill=255)

    x1, y1, x2, y2 = PROG_BOX
    cy = (y1 + y2) // 2
    step = PROG_SEG_W + PROG_GAP
    segs = max(1, (x2 - x1) // step)
    filled = int(round(frac * segs))

    for i in range(segs):
        sx = x1 + i * step
        d.rectangle((sx, cy - PROG_BASE_THICK // 2, sx + PROG_SEG_W, cy + PROG_BASE_THICK // 2), fill=0)

    for i in range(filled):
        sx = x1 + i * step
        d.rectangle((sx, cy - PROG_FILL_THICK // 2, sx + PROG_SEG_W, cy + PROG_FILL_THICK // 2), fill=0)


def erase_top_line(img):
    ImageDraw.Draw(img).rectangle((0, 0, W, TOP_ERASE_H), fill=255)


def draw_slide_weather(img, weather, rain_eta, err=None):
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, H), fill=255)

    now = time.strftime("%H:%M", time.localtime())
    tw, th = d.textbbox((0, 0), now, font=FONT_TIME)[2:]
    d.text(((W - tw) // 2, 40 + (120 - th) // 2), now, font=FONT_TIME, fill=0)

    ds = de_date_local()
    dw, dh = d.textbbox((0, 0), ds, font=FONT_DATE)[2:]
    d.text((W - 40 - dw, 160 - dh), ds, font=FONT_DATE, fill=0)

    d.line((40, 180, W - 40, 180), fill=0, width=2)

    y = 200
    if err:
        headline = f"Wetterfehler: {err}"
    else:
        if rain_eta is None:
            headline = "Kein Regen in den nächsten 2 h"
        elif rain_eta <= 0:
            headline = "Regen jetzt"
        else:
            headline = f"Regen in {rain_eta} min"
    d.text((40, y), headline, font=FONT_BIG, fill=0)
    y += d.textbbox((0, 0), headline, font=FONT_BIG)[3] + 10

    if weather:
        code = weather.get("code")
        cond = WMO_DE.get(int(code) if code is not None else 3, f"Code {code}")
        d.text((40, y), cond, font=FONT_BIG, fill=0)
        y += d.textbbox((0, 0), cond, font=FONT_BIG)[3] + 6

        temp = weather.get("temp")
        feels = weather.get("feels")
        if temp is not None:
            text = f"{round(temp)}°C"
            if feels is not None:
                text += f" (gefühlt {round(feels)}°)"
            d.text((40, y), text, font=FONT_BIG, fill=0)
            y += d.textbbox((0, 0), text, font=FONT_BIG)[3] + 6

        extras = []
        if weather.get("wind") is not None:
            extras.append(f"Wind {round(weather['wind'])} km/h")
        if weather.get("precip") is not None:
            extras.append(f"Niederschlag {weather['precip']:.1f} mm")
        if extras:
            d.text((40, y), " · ".join(extras), font=FONT_SM, fill=0)


def draw_slide_mvv(img, mvv_img):
    img.paste(mvv_img, (0, 0))


def push_frame(epd, frame, *, full_refresh: bool):
    buffer = epd.getbuffer(frame)
    if full_refresh:
        epd.init()
        epd.display(buffer)
        epd.init_part()
    else:
        epd.display_Partial(buffer, 0, 0, W, H)


def update_progress(epd, frame, started_at, interval):
    fraction = (time.monotonic() - started_at) / interval
    draw_progress(frame, fraction)
    erase_top_line(frame)
    push_frame(epd, frame, full_refresh=False)


def render_weather(epd, frame, weather, rain_eta, error, progress, *, full):
    draw_slide_weather(frame, weather, rain_eta, error)
    erase_top_line(frame)
    draw_progress(frame, progress)
    push_frame(epd, frame, full_refresh=full)


def render_mvv(epd, frame, mvv_state, progress, *, full):
    mvv_img, mvv_err = get_mvv_image_cached(mvv_state)
    draw_slide_mvv(frame, mvv_img)
    erase_top_line(frame)
    draw_progress(frame, progress)
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
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    epd = epd7in5_V2.EPD()
    frame = Image.new("1", (W, H), 255)

    try:
        epd.init()
        epd.Clear()
        epd.init_part()
    except Exception as exc:
        raise SystemExit(f"Failed to initialise display: {exc}") from exc

    weather_data, weather_err = safe_fetch(fetch_current_weather, "weather")
    rain_eta, rain_err = safe_fetch(fetch_rain_eta, "rain")
    weather_error = weather_err or rain_err

    render_weather(epd, frame, weather_data, rain_eta, weather_error, 0.0, full=True)

    mvv_state = {}
    slide = "weather"
    now = time.monotonic()
    slide_started = now
    last_weather = now
    last_rain = now
    last_mvv = now
    last_full = now

    try:
        while True:
            now = time.monotonic()

            update_progress(epd, frame, slide_started, SLIDE_INTERVAL)

            if now - slide_started >= SLIDE_INTERVAL:
                slide = "mvv" if slide == "weather" else "weather"
                slide_started = now
                if slide == "weather":
                    render_weather(epd, frame, weather_data, rain_eta, weather_error, 0.0, full=True)
                else:
                    render_mvv(epd, frame, mvv_state, 0.0, full=False)

            if slide == "weather" and now - last_weather >= WX_REFRESH:
                weather_data, weather_err = safe_fetch(fetch_current_weather, "weather")
                weather_error = weather_err or rain_err
                progress = (now - slide_started) / SLIDE_INTERVAL
                render_weather(epd, frame, weather_data, rain_eta, weather_error, progress, full=False)
                last_weather = now

            if slide == "weather" and now - last_rain >= RAIN_REFRESH:
                rain_eta, rain_err = safe_fetch(fetch_rain_eta, "rain")
                weather_error = weather_err or rain_err
                progress = (now - slide_started) / SLIDE_INTERVAL
                render_weather(epd, frame, weather_data, rain_eta, weather_error, progress, full=False)
                last_rain = now

            if slide == "mvv" and now - last_mvv >= MVV_REFRESH:
                progress = (now - slide_started) / SLIDE_INTERVAL
                render_mvv(epd, frame, mvv_state, progress, full=False)
                last_mvv = now

            if now - last_full >= FULL_REFRESH:
                if slide == "weather":
                    render_weather(epd, frame, weather_data, rain_eta, weather_error, (now - slide_started) / SLIDE_INTERVAL, full=True)
                else:
                    render_mvv(epd, frame, mvv_state, (now - slide_started) / SLIDE_INTERVAL, full=True)
                last_full = now

            time.sleep(1)

    except KeyboardInterrupt:
        logging.info("Stopping slideshow...")
    except Exception as exc:
        logging.error("Unhandled error: %s", exc)
        traceback.print_exc()
    finally:
        driver = mvv_state.get("driver")
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        try:
            epd.sleep()
        except Exception:
            pass


if __name__ == "__main__":
    main()
