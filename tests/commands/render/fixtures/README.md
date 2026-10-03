# FFmpeg statistics fixtures

Captured with FFmpeg 9.0.2 on macOS; temporary input paths are replaced with
filenames. Reproduce with:

```sh
ffmpeg -f lavfi -i 'sine=frequency=1000:duration=2' tone.wav
ffmpeg -f lavfi -i 'anullsrc=r=44100:cl=mono:d=2' silence.wav
ffmpeg -i tone.wav -filter:a 'volumedetect,ebur128=framelog=verbose' \
  -hide_banner -nostats -f null /dev/null 2>tone.txt
```

Use the same analysis command for `silence.wav` to capture `silence.txt`.
