#!/usr/bin/env python3
"""Phase 2: extract ARSC string pool + full asset/binary text, dump into per-apk raw text for rereading."""
import os, json, zipfile, re, sys

APKDIR = "/tmp/app_backup"
OUT = os.path.expanduser("~/.openclaw/workspace/projects/coloros-privacy-audit/out/text")
os.makedirs(OUT, exist_ok=True)

def utf8_strs(data, minlen=6):
    out = []
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00){%d,}|(?:[\x09\x0a\x0d\x20-\x7e]|\xe0[\xa0-\xbf][\x80-\xbf]|[\xe1-\xec\xee\xef][\x80-\xbf]{2}|\xed[\x80-\x9f][\x80-\xbf]|\xf0[\x90-\xbf][\x80-\xbf]{2}|[\xf1-\xf3][\x80-\xbf]{3}|\xf4[\x80-\x8f][\x80-\xbf]{2}){%d,}" % (minlen, minlen), data):
        try:
            s = m.group().replace(b"\x00", b"").decode("utf-8")
            out.append(s)
        except Exception:
            pass
    return out

files = sorted(f for f in os.listdir(APKDIR) if f.endswith(".apk"))
only = sys.argv[1:]
if only:
    files = [f for f in files if any(o in f for o in only)]

for f in files:
    pkg = f[:-4].rsplit("_", 1)[-1]
    dest = os.path.join(OUT, pkg + ".txt")
    if os.path.exists(dest):
        continue
    buf = []
    try:
        z = zipfile.ZipFile(os.path.join(APKDIR, f))
        for n in z.namelist():
            low = n.lower()
            if not (low.endswith((".arsc", ".dex", ".xml")) or "/assets/" in low or low.endswith(".json")):
                continue
            try:
                data = z.read(n)
            except Exception:
                continue
            for s in utf8_strs(data, 6):
                buf.append(s)
    except Exception as e:
        buf.append("ERROR " + str(e))
    open(dest, "w").write("\n".join(buf))
    print(pkg, len(buf), flush=True)
