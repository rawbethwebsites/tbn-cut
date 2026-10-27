#!/bin/bash
# Double-click to open the TBN Cut dashboard (starts it if it isn't running).
cd "$(dirname "$0")"
[ -f ~/.tbn-cut.env ] && . ~/.tbn-cut.env
mkdir -p output
if ! curl -s -o /dev/null http://127.0.0.1:4321/; then
  PYTHONPATH= OPENCV_LOG_LEVEL=ERROR nohup ~/.ai-video-editor/venv/bin/python -m tbncut.dashboard > output/_dashboard.log 2>&1 &
  for i in $(seq 1 20); do curl -s -o /dev/null http://127.0.0.1:4321/ && break; sleep 0.5; done
fi
open http://127.0.0.1:4321/
