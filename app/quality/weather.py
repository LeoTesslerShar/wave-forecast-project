"""Sky condition from Open-Meteo's `weather_code` -- the standard WMO 4677 code table
(verified live against api.open-meteo.com/v1/forecast). This is a TRANSLATION table, not a
judgement call like most heuristics in this project -- the code->condition mapping is a
published standard, not something invented here. `icon_key` is a stable English identifier
for the frontend to pick an icon by (kept English for the same reason every other
identifier in this project is -- something to match on, not to show); `label` is the
Hebrew text actually shown to the user.
"""
from dataclasses import dataclass

# (codes, icon_key, hebrew_label) -- WMO 4677 table, grouped the way Open-Meteo's own docs
# group them.
_WEATHER_TABLE: list[tuple[tuple[int, ...], str, str]] = [
    ((0,), "clear", "בהיר"),
    ((1,), "clear", "בהיר בעיקר"),
    ((2,), "partly_cloudy", "מעונן חלקית"),
    ((3,), "cloudy", "מעונן"),
    ((45, 48), "fog", "ערפל"),
    ((51, 53, 55, 56, 57), "rain", "טפטוף"),
    ((61, 63, 65, 66, 67, 80, 81, 82), "rain", "גשם"),
    ((71, 73, 75, 77, 85, 86), "snow", "שלג"),
    ((95, 96, 99), "storm", "סופת רעמים"),
]
_CODE_TO_ENTRY = {code: (icon_key, label) for codes, icon_key, label in _WEATHER_TABLE for code in codes}


@dataclass
class WeatherCondition:
    icon_key: str  # "clear" | "partly_cloudy" | "cloudy" | "fog" | "rain" | "snow" | "storm" | "unknown"
    label: str  # Hebrew


def classify_weather(weather_code: int | None) -> WeatherCondition:
    if weather_code is None or weather_code not in _CODE_TO_ENTRY:
        return WeatherCondition(icon_key="unknown", label="אין נתונים")
    icon_key, label = _CODE_TO_ENTRY[weather_code]
    return WeatherCondition(icon_key=icon_key, label=label)
