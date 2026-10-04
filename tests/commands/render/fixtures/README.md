# Audio statistics fixtures

`tone.json` and `silence.json` are FFprobe 9.0.2 frame-tag output from the filter
chain in `render/stats.py`. Inputs are two-second, 44.1 kHz mono WAVs made with
FFmpeg's `sine=frequency=1000:duration=2` and `anullsrc=r=44100:cl=mono:d=2` sources.
