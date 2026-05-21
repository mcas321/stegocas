import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

from stego_core import (
    aes_decrypt, aes_encrypt,
    bits_to_bytes, bytes_to_bits,
    build_bitstream, embed, extract,
    rs_decode, rs_encode,
)
from cryptography.exceptions import InvalidTag
import cv2
import numpy as np

failures = []

def check(label, condition, detail=""):
    if condition:
        print(f"PASS  {label}")
    else:
        print(f"FAIL  {label}{(' -- ' + detail) if detail else ''}")
        failures.append(label)


print("=== 1. bits <-> bytes ===")
original = b"Hello, World! \x00\xFF\xAB"
check("roundtrip", bits_to_bytes(bytes_to_bits(original)) == original)

print("\n=== 2. Reed-Solomon ===")
data = b"Secret payload test data 1234567890 ABCDEFGH"
check("encode/decode", rs_decode(rs_encode(data)) == data)
enc_ba = bytearray(rs_encode(data))
for idx in [3, 7, 15, 25]:
    enc_ba[idx] = (enc_ba[idx] + 99) % 256
check("correccion 4 bytes corruptos", rs_decode(bytes(enc_ba)) == data)

print("\n=== 3. AES-256-GCM ===")
plaintext = "Mensaje secreto: aeiou EUR 日本語"
password  = "ContraseñaSegura!2024"
ct = aes_encrypt(plaintext, password)
check("roundtrip AES", aes_decrypt(ct, password) == plaintext)
raised = False
try:
    aes_decrypt(ct, "wrong")
except InvalidTag:
    raised = True
check("rechaza contrasena incorrecta", raised)

print("\n=== 4. build_bitstream ===")
bits = build_bitstream("Test", "pwd")
check("bits validos", all(b in (0, 1) for b in bits))
check("longitud minima", len(bits) > 64)
print(f"      bits: {len(bits)}")

print("\n=== 5. Embed / Extract end-to-end ===")
rng      = np.random.default_rng(42)
img_arr  = rng.integers(50, 210, (300, 400, 3), dtype=np.uint8)
src_path = os.path.join(tempfile.gettempdir(), "_stego_src.jpg")
dst_path = os.path.join(tempfile.gettempdir(), "_stego_out.jpg")
cv2.imwrite(src_path, img_arr, [cv2.IMWRITE_JPEG_QUALITY, 95])

TEXT = "Hola mundo! Mensaje de prueba con acentos: n, u, e. Caracteres especiales."
PWD  = "ClaveSegura!2024"

res_e = embed(src_path, TEXT, PWD, dst_path)
check("embed exitoso", res_e["success"], res_e.get("message", ""))

if res_e["success"]:
    res_x = extract(dst_path, PWD)
    check("extract exitoso", res_x["success"], res_x.get("message", ""))
    check("texto identico", res_x.get("text") == TEXT, repr(res_x.get("text")))
    res_bad = extract(dst_path, "clave_incorrecta")
    check("rechaza contrasena incorrecta", not res_bad["success"])

print("\n=== 6. Recompresion JPEG q=80 ===")
if res_e["success"]:
    recomp = os.path.join(tempfile.gettempdir(), "_stego_recomp.jpg")
    cv2.imwrite(recomp, cv2.imread(dst_path), [cv2.IMWRITE_JPEG_QUALITY, 80])
    res_rc = extract(recomp, PWD)
    check("sobrevive q=80", res_rc["success"], res_rc.get("message", ""))
    if res_rc["success"]:
        check("texto intacto", res_rc.get("text") == TEXT)

print()
if failures:
    print(f"=== {len(failures)} FALLO(S): {failures} ===")
    sys.exit(1)
else:
    print("=== TODAS LAS PRUEBAS PASARON ===")
