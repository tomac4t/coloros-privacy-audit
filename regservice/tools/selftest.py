#!/usr/bin/env python3
"""自测：验证 dm_decode.py 的 AES/GZIP/token 实现与 APK 逻辑一致"""
import base64
import gzip
import hashlib
import sys

sys.path.insert(0, "tools")
import dm_decode  # noqa: E402
from Crypto.Cipher import AES  # noqa: E402


def main():
    key = dm_decode.DEFAULT_KEY
    k = dm_decode._aes_key(key)
    print("key_str     :", key)
    print("AES key     :", k, f"(len={len(k)})")
    assert len(k) == 32

    # 1) 明文往返
    plain = '{"imei1":"860000000000000","name":"中文测试"}'
    ct = dm_decode.aes_encrypt(plain)
    assert dm_decode.aes_decrypt(ct).decode() == plain
    print("1) AES 往返        OK  cipher_len=", len(ct))

    # 2) GZIPJsonRequest 路径：先 gzip 再 AES
    payload = "中文" * 500
    ct2 = base64.b64encode(AES.new(k, AES.MODE_ECB).encrypt(dm_decode.pad_pkcs5(gzip.compress(payload.encode())))).decode()
    assert dm_decode.guess_body_bytes(dm_decode.aes_decrypt(ct2)).decode() == payload
    print("2) GZIP→AES 往返   OK")

    # 3) URL token = MD5(imei + last8(timestr))
    imei, ts = "860123456789012", "1759876543210"
    expect = hashlib.md5((imei + ts[-8:]).encode()).hexdigest()
    assert dm_decode.url_token(imei, ts) == expect
    print("3) URL token       OK ", expect)

    # 4) 一批真实字段的解密演示
    demo = {
        "imei1": "860000000000001", "imei2": "860000000000002",
        "imsi1": "460000000000001", "iccid1": "89860000000000000000",
        "logAppAry": "com.eg.android.AlipayGphone|支付宝|128 bugs|45231s\n",
    }
    import json
    ct3 = dm_decode.aes_encrypt(json.dumps(demo, ensure_ascii=False))
    print("\n4) 示例密文(base64):", ct3)
    print("   解回:", dm_decode.aes_decrypt(ct3).decode())


if __name__ == "__main__":
    main()
