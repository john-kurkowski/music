#!/usr/bin/env bash

# Encode .wav master to .mp3 and tag with artist, album, and track number.
# Example expected input folders and filenames form: 'My Album Title/01 - Song
# of Myself.wav', 'My Album Title/02 - Lead Single.wav'.

set -e

cd "$(dirname "$0")" || exit 1

# TODO: only re-encode if .wav is newer than .mp3
# parallel lame --preset standard {} {.}.mp3 ::: */*.wav

for track in */*.mp3 ; do
    album=$(dirname "$track")
    artist='Bluu'
    title=$(basename "${track#* - }" ".${track##*.}")
    track_num=$(basename "${track%% - *}")
    eyed3 -a "$artist" -A "${album}" -n "${track_num}" -t "${title}" "$track"
done
