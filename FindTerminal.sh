#!/bin/sh
#
# This code is released in public domain by Han Boetes <han@mijncomputer.nl>
#
# This script tries to exec a terminal emulator by trying some known terminal
# emulators.
#
# We welcome patches that add distribution-specific mechanisms to find the
# preferred terminal emulator. On Debian, there is the x-terminal-emulator
# symlink for example.
#
# Invariants:
# 1. $TERMINAL must come first
# 2. Distribution-specific mechanisms come next, e.g. x-terminal-emulator
# 3. The terminal emulator with best accessibility comes first.
# 4. No order is guaranteed/desired for the remaining terminal emulators.
echo ''>tmp
for terminal in "$TERMINAL" x-terminal-emulator mate-terminal gnome-terminal terminator xfce4-terminal urxvt rxvt termit Eterm aterm uxterm xterm roxterm termite lxterminal terminology st qterminal lilyterm tilix terminix konsole kitty guake tilda alacritty hyper; do
    if command -v "$terminal" > /dev/null 2>&1; then
        echo "$terminal">>tmp
    fi
done
