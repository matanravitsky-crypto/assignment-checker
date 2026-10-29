#!/usr/bin/env bash
python3 -m pip install -q pymupdf pillow mammoth || python3 -m pip install -q --break-system-packages pymupdf pillow mammoth
echo "python deps ok"
