## 1. Output Contract Tests

- [x] 1.1 Update the nearest render CLI snapshot to show the progress row as the only visible elapsed duration and `Rendered at N.Nx realtime` as the statistics caption.
- [x] 1.2 Preserve targeted render-performance coverage proving that the ratio uses audio duration divided by REAPER-only render duration.
- [x] 1.3 Add a narrow absence assertion only if the snapshot does not clearly prevent a second `Rendered in` duration from returning.

## 2. Render Timing Output

- [x] 2.1 Change the statistics caption in `src/music/commands/render/process.py` to omit `render_delta` and display `render_speedup` as `Rendered at N.Nx realtime`.
- [x] 2.2 Keep the timer around `project.render`, `RenderResult.render_delta`, `render_speedup`, `TimeElapsedColumn`, and the progress task lifetime semantically unchanged.
- [x] 2.3 Clarify nearby timing names or documentation only where they could otherwise confuse REAPER-only render time with end-to-end task time.

## 3. Verification

- [x] 3.1 Run `uv run check --fix` repo-wide.
- [x] 3.2 Run the focused render tests, then the full test suite.
- [x] 3.3 Perform a short real render and confirm that only the progress row displays elapsed time while the summary reports realtime performance.
