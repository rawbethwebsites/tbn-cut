#!/bin/bash
# One-time setup of TBN Cut on a new Mac (Apple silicon). Safe to run again.
#   git clone https://github.com/rawbethwebsites/tbn-cut.git && cd tbn-cut && ./install.sh
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
HOME_DIR="$HOME/.ai-video-editor"
VENV="$HOME_DIR/venv"
ENV_FILE="$HOME/.tbn-cut.env"
# Open models from the Ollama library (Rob's own machine uses his local fine-tunes instead).
VISION_MODEL="${TBN_CUT_VISION_MODEL:-qwen3.5:9b}"
EDITOR_MODEL="${TBN_CUT_EDITOR_MODEL:-$VISION_MODEL}"

say() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }

say "1/6 Tools (Homebrew: python, ffmpeg, node, ollama)"
if ! command -v brew >/dev/null; then
  echo "Homebrew is missing. Install it from https://brew.sh, then run ./install.sh again."; exit 1
fi
for f in python@3.12 ffmpeg node; do brew list "$f" >/dev/null 2>&1 || brew install "$f"; done
command -v ollama >/dev/null || brew install --cask ollama
PY="$(brew --prefix python@3.12)/bin/python3.12"

say "2/6 Python environment ($VENV)"
mkdir -p "$HOME_DIR/models"
[ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV"
PYTHONPATH= "$VENV/bin/pip" install -q --upgrade pip
PYTHONPATH= "$VENV/bin/pip" install -q -r requirements.txt

say "3/6 Face finder + speech model"
[ -f "$HOME_DIR/models/yunet.onnx" ] || curl -fL -o "$HOME_DIR/models/yunet.onnx" \
  https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
# Whisper "small" downloads itself on the first edit if this folder is missing; fetch it now instead.
if [ ! -d "$HOME_DIR/models/faster-whisper-small" ]; then
  PYTHONPATH= "$VENV/bin/python" -c "from faster_whisper import download_model; download_model('small', output_dir='$HOME_DIR/models/faster-whisper-small')"
fi

say "4/6 Motion graphics (Remotion)"
(cd motion && npm ci --no-audit --no-fund && npx remotion browser ensure)

say "5/6 Local AI models (Ollama: $VISION_MODEL)"
if ! curl -s -o /dev/null http://127.0.0.1:11434/; then
  open -a Ollama || (ollama serve >/dev/null 2>&1 &)
  for i in $(seq 1 30); do curl -s -o /dev/null http://127.0.0.1:11434/ && break; sleep 1; done
fi
ollama pull "$VISION_MODEL"
[ "$EDITOR_MODEL" = "$VISION_MODEL" ] || ollama pull "$EDITOR_MODEL"
cat > "$ENV_FILE" <<EOF
export TBN_CUT_VISION_MODEL="$VISION_MODEL"
export TBN_CUT_EDITOR_MODEL="$EDITOR_MODEL"
EOF

say "6/6 Claude Code skill"
mkdir -p "$HOME/.claude/skills"
rm -rf "$HOME/.claude/skills/tbn-cut"
ln -s "$ROOT/skill/tbn-cut" "$HOME/.claude/skills/tbn-cut"
mkdir -p output

PYTHONPATH= "$VENV/bin/python" -c "import tbncut.run, tbncut.dashboard" && say "Done. Double-click 'Open TBN Cut.command', or ask Claude: \"edit my video with TBN Cut\"."
