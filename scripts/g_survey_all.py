#!/usr/bin/env python3
"""批量跑 g_apk_survey.py，输出到单个文件。"""
import subprocess
import sys

APK_DIR = sys.argv[1] if len(sys.argv) > 1 else "/tmp/g-apk"
NAMES = ["athena", "dw", "battery", "exsystem", "powermon", "qtiLoc", "fused", "oplusloc"]
SURVEY = "/home/admin/.openclaw/workspace/projects/coloros-privacy-audit/scripts/g_apk_survey.py"

for n in NAMES:
    print("#" * 70)
    print(f"# {n}")
    print("#" * 70)
    r = subprocess.run(
        [sys.executable, SURVEY, f"{APK_DIR}/{n}.apk", n],
        capture_output=True, text=True,
    )
    print(r.stdout)
    if r.stderr.strip():
        print("[stderr]", r.stderr.strip()[:500])
