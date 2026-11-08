#!/bin/bash
# usage: experiments/run.sh <script.py> <logname>   (stops any running experiment first)
cd "$(dirname "$0")/.."
if [ -f logs/.exp.pid ]; then kill "$(cat logs/.exp.pid)" 2>/dev/null; sleep 1.5; fi
timeout 400 .venv/bin/python -I "experiments/$1" > "logs/$2" 2>&1 &
echo $! > logs/.exp.pid
