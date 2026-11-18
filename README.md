# gta6-twitch-forecast

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/zakkysp/gta6-twitch-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/zakkysp/gta6-twitch-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecasts how many people watch Grand Theft Auto VI live on Twitch in each hour of its release day, 2026-11-19 (UTC), from everything recorded up to the end of the first hour. One hour into the day, `main.py` reads the case file and writes five quantiles (5%, 25%, 50%, 75%, 95%) of that hour's viewer count for each of hours 2 to 24.

The forecast is built from the past launches in the case itself: each comparable launch's release-day curve is expressed as a ratio to its own hour-1 print, launches whose first hour was nearly empty (peak more than 20x the hour-1 print) and early-access contaminated launches are left out, and each hour's forecast is the median log-ratio across the launches that remain, with a spread taken from how much those launches actually disagreed (interquartile range, normal scale). On the four practice launches that scores a mean pinball loss of 0.258 against the house baseline's 0.387, with a typical miss of 47% and 90% coverage of 0.85.

## Run it

```sh
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Put the case files (`<id>.in`) in `input/`; the forecast for each one lands in `out/<id>.out` as `{"hours": [{"hour": 2, "q": [q05, q25, q50, q75, q95]}, ...]}`. Python 3.13, standard library only, no network, deterministic — the same input always writes the same bytes, in well under a second per case.

---

<sub>Entered on [make.fun](https://make.fun/?ref=5twwhvj5&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
