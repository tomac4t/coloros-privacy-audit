#!/usr/bin/env python3
"""A 组剩余 4 包体检：权限 + 域名 + URL。"""
import subprocess
import sys

APK_DIR = sys.argv[1] if len(sys.argv) > 1 else "/tmp/a-apk"
NAMES = ["logkit", "crashbox", "postman", "nhs"]
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
        print("[stderr]", r.stderr.strip()[:300])
