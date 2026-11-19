#!/bin/sh
# Regenerates the bundled sounds (synthesised sine tones, public domain). Needs ffmpeg.
set -e
out="$(dirname "$0")/../src/waterreminder/data/sounds"
gen() { # name, expr, dur
  ffmpeg -loglevel error -y -f lavfi -i "aevalsrc='$2':d=$3:s=44100" -af "afade=t=in:d=0.01,afade=t=out:st=$(awk "BEGIN{print $3-0.4}"):d=0.4" -c:a libvorbis -q:a 3 "$out/$1.ogg"
}
# drop: falling-pitch "bloop" twice
gen drop "0.5*sin(2*PI*(900-700*mod(t,0.5))*t)*exp(-5*mod(t,0.5))" 1.0
# chime: two soft notes
gen chime "0.4*(sin(2*PI*880*t)*exp(-3*t)+sin(2*PI*1320*(t-0.25))*exp(-3*(t-0.25))*gte(t,0.25))" 1.4
# bell: inharmonic partials, long decay
gen bell "0.3*(sin(2*PI*660*t)+0.6*sin(2*PI*1584*t)+0.4*sin(2*PI*2640*t))*exp(-2.5*t)" 1.8
