# AudioHarbor

AudioHarbor is a local-only FastAPI application that discovers video or playlist URLs, downloads audio with `yt-dlp`, converts it with FFmpeg, verifies the result, and publishes MP3 files below the runtime user's `~/Downloads` directory.

## Quick start

Install FFmpeg/ffprobe and a supported JavaScript runtime, then:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
audioharbor doctor
audioharbor start
```

Open `http://127.0.0.1:8787`. The worker is a separate process. `audioharbor serve` and `audioharbor worker` can also be run independently.

Only download media you are entitled to access. AudioHarbor does not bypass DRM, CAPTCHAs, access controls, or provider restrictions.

Configuration is read from `${XDG_CONFIG_HOME:-~/.config}/audioharbor/config.toml`; see `config.example.toml`.

