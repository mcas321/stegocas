import hashlib
import os

import cv2
import numpy as np
from scipy.fftpack import dct, idct

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.exceptions import InvalidTag

import reedsolo


BLOCK_SIZE = 8

# DCT coefficient positions in the 8x8 luminance block.
# Mid-frequency zone: quantization step ~10 at JPEG q=80.
# P=40 -> difference ±80 -> ~8x margin over the quantization step.
C1_POS = (2, 3)
C2_POS = (3, 2)
P: float = 40.0

# Y channel (luminance). JPEG never subsamples Y, unlike Cb/Cr (4:2:0).
CHANNEL_IDX = 0

SALT_SIZE      = 16
NONCE_SIZE     = 12
KDF_ITERATIONS = 200_000

RS_NSYM  = 40   # corrects up to 20 corrupted bytes per chunk
RS_CHUNK = 200

EOF_MARKER = b"\xDE\xAD\xBE\xEF"

MAX_DIMENSION = 1200

# Blocks with pixel variance below this threshold are flat (sky, backgrounds).
# They are skipped in both embed and extract to avoid visible artifacts.
# The usable block list is deterministic: unmodified flat blocks stay flat.
VARIANCE_THRESHOLD: float = 100.0

# Thresholds tried in order (highest first) when the message doesn't fit.
# Embed picks the highest that gives enough blocks.
# Extract tries each until AES-GCM authentication succeeds.
VARIANCE_THRESHOLDS = [100, 75, 50, 25, 10, 1, 0]


def _block_order(total_blocks: int, password: str) -> list:
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    seed   = int.from_bytes(digest[:8], "big")
    rng    = np.random.default_rng(seed)
    return rng.permutation(total_blocks).tolist()


def _spatially_interleave(usable_order: list, w_blocks: int) -> list:
    # Round-robin by image row: the first k blocks used come from all
    # textured rows in equal proportion, preventing visible horizontal bands.
    rows: dict = {}
    for idx in usable_order:
        bi = idx // w_blocks
        rows.setdefault(bi, []).append(idx)

    sorted_keys = sorted(rows.keys())
    if not sorted_keys:
        return usable_order

    result  = []
    max_len = max(len(rows[r]) for r in sorted_keys)
    for i in range(max_len):
        for r in sorted_keys:
            if i < len(rows[r]):
                result.append(rows[r][i])
    return result


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
        backend=default_backend(),
    )
    return kdf.derive(password.encode("utf-8"))


def aes_encrypt(plaintext: str, password: str) -> bytes:
    salt  = os.urandom(SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)
    key   = _derive_key(password, salt)
    ct    = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return salt + nonce + ct


def aes_decrypt(data: bytes, password: str) -> str:
    min_len = SALT_SIZE + NONCE_SIZE + 16
    if len(data) < min_len:
        raise ValueError(f"Payload too short ({len(data)} B).")
    salt  = data[:SALT_SIZE]
    nonce = data[SALT_SIZE : SALT_SIZE + NONCE_SIZE]
    ct    = data[SALT_SIZE + NONCE_SIZE :]
    key   = _derive_key(password, salt)
    return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")


def rs_encode(data: bytes) -> bytes:
    rsc    = reedsolo.RSCodec(RS_NSYM)
    chunks = [data[i : i + RS_CHUNK] for i in range(0, max(1, len(data)), RS_CHUNK)]
    if len(chunks) > 255:
        raise ValueError(f"Payload too large: {len(chunks)} chunks (max 255).")
    result = len(chunks).to_bytes(1, "big")
    for chunk in chunks:
        enc = bytes(rsc.encode(chunk))
        result += len(enc).to_bytes(2, "big") + enc
    return result


def rs_decode(data: bytes) -> bytes:
    rsc    = reedsolo.RSCodec(RS_NSYM)
    offset = 0
    if not data:
        raise ValueError("Empty RS data.")
    num_chunks = data[offset]; offset += 1
    result = b""
    for i in range(num_chunks):
        if offset + 2 > len(data):
            raise ValueError(f"Premature end at chunk {i}.")
        chunk_len = int.from_bytes(data[offset : offset + 2], "big"); offset += 2
        if offset + chunk_len > len(data):
            raise ValueError(f"Premature end reading chunk {i}.")
        result += bytes(rsc.decode(data[offset : offset + chunk_len])[0])
        offset += chunk_len
    return result


def bytes_to_bits(data: bytes) -> list:
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def bits_to_bytes(bits: list) -> bytes:
    result = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for j in range(8):
            byte <<= 1
            if i + j < len(bits):
                byte |= bits[i + j]
        result.append(byte)
    return bytes(result)


def build_bitstream(text: str, password: str) -> list:
    encrypted  = aes_encrypt(text, password)
    rs_payload = rs_encode(encrypted)
    full_blob  = len(rs_payload).to_bytes(4, "big") + rs_payload + EOF_MARKER
    return bytes_to_bits(full_blob)


def _dct2(block: np.ndarray) -> np.ndarray:
    return dct(dct(block.T, norm="ortho").T, norm="ortho")


def _idct2(block: np.ndarray) -> np.ndarray:
    return idct(idct(block.T, norm="ortho").T, norm="ortho")


def _embed_bit_in_block(block_dct: np.ndarray, bit: int) -> np.ndarray:
    # Encode bit via coefficient difference: bit=1 -> C1>C2, bit=0 -> C1<C2.
    # Using mid=(C1+C2)/2 preserves the sum, minimizing spatial distortion.
    r1, c1 = C1_POS
    r2, c2 = C2_POS
    block  = block_dct.copy()
    mid    = (block[r1, c1] + block[r2, c2]) / 2.0
    if bit == 1:
        block[r1, c1] = mid + P
        block[r2, c2] = mid - P
    else:
        block[r1, c1] = mid - P
        block[r2, c2] = mid + P
    return block


def _extract_bit_from_block(block_dct: np.ndarray) -> int:
    r1, c1 = C1_POS
    r2, c2 = C2_POS
    return 1 if block_dct[r1, c1] > block_dct[r2, c2] else 0


def _build_usable_order(work_f: np.ndarray, h_blocks: int, w_blocks: int,
                        password: str, threshold: float = VARIANCE_THRESHOLD) -> list:
    total_blocks = h_blocks * w_blocks
    order        = _block_order(total_blocks, password)
    usable       = []
    for idx in order:
        bi = idx // w_blocks
        bj = idx  % w_blocks
        r  = bi * BLOCK_SIZE
        c  = bj * BLOCK_SIZE
        if np.var(work_f[r : r + BLOCK_SIZE, c : c + BLOCK_SIZE]) >= threshold:
            usable.append(idx)
    return _spatially_interleave(usable, w_blocks)


def embed(image_path: str, text: str, password: str, output_path: str) -> dict:
    result: dict = {"success": False, "message": "", "warning": ""}

    img = cv2.imread(image_path)
    if img is None:
        result["message"] = f"Could not load image: '{image_path}'"
        return result

    h, w = img.shape[:2]
    if len(img.shape) == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    if max(h, w) > MAX_DIMENSION:
        result["warning"] = (
            f"La imagen mide {w}x{h} px.\n"
            f"WhatsApp reescala imagenes a <= {MAX_DIMENSION} px al enviarlas,\n"
            f"lo cual destruiria los datos ocultos."
        )

    try:
        bits = build_bitstream(text, password)
    except Exception as exc:
        result["message"] = f"Error building bitstream: {exc}"
        return result

    h_blocks = h // BLOCK_SIZE
    w_blocks = w // BLOCK_SIZE

    ycrcb    = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
    channels = list(cv2.split(ycrcb))
    work_f   = channels[CHANNEL_IDX].astype(np.float64)

    usable_order     = None
    chosen_threshold = VARIANCE_THRESHOLDS[0]
    for thresh in VARIANCE_THRESHOLDS:
        candidate = _build_usable_order(work_f, h_blocks, w_blocks, password, thresh)
        if len(candidate) >= len(bits):
            usable_order     = candidate
            chosen_threshold = thresh
            break

    if usable_order is None:
        overhead = (SALT_SIZE + NONCE_SIZE + 16 + RS_NSYM + 10) * 8
        all_blocks = _build_usable_order(work_f, h_blocks, w_blocks, password, 0)
        cap        = max(0, (len(all_blocks) - overhead) // 8)
        result["message"] = (
            f"Mensaje demasiado largo para esta imagen.\n"
            f"  Bits necesarios: {len(bits)}\n"
            f"  Bloques disponibles (todos): {len(all_blocks)} de {h_blocks * w_blocks}\n"
            f"  Capacidad aproximada: ~{cap} caracteres."
        )
        return result

    for bit_idx, linear_idx in enumerate(usable_order):
        if bit_idx >= len(bits):
            break
        bi  = linear_idx // w_blocks
        bj  = linear_idx  % w_blocks
        r   = bi * BLOCK_SIZE
        c   = bj * BLOCK_SIZE
        blk = work_f[r : r + BLOCK_SIZE, c : c + BLOCK_SIZE]
        work_f[r : r + BLOCK_SIZE, c : c + BLOCK_SIZE] = _idct2(
            _embed_bit_in_block(_dct2(blk), bits[bit_idx])
        )

    channels[CHANNEL_IDX] = np.clip(work_f, 0, 255).astype(np.uint8)
    img_out = cv2.cvtColor(cv2.merge(channels), cv2.COLOR_YCrCb2BGR)

    if not cv2.imwrite(output_path, img_out, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        result["message"] = f"Could not save image to: '{output_path}'"
        return result

    result["success"] = True
    thresh_note      = f", umbral varianza: {chosen_threshold}" if chosen_threshold < VARIANCE_THRESHOLDS[0] else ""
    result["message"] = (
        f"Mensaje ocultado con exito{thresh_note}.\n"
        f"  Bloques usados: {len(bits)} de {len(usable_order)} disponibles "
        f"({len(bits) / len(usable_order) * 100:.1f}%)\n"
        f"  Guardado en: '{output_path}'"
    )
    return result


def extract(image_path: str, password: str) -> dict:
    result: dict = {"success": False, "message": "", "text": ""}

    img = cv2.imread(image_path)
    if img is None:
        result["message"] = f"Could not load image: '{image_path}'"
        return result

    h, w = img.shape[:2]
    if len(img.shape) == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    ycrcb    = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
    channels = cv2.split(ycrcb)
    work_f   = channels[CHANNEL_IDX].astype(np.float64)

    h_blocks = h // BLOCK_SIZE
    w_blocks = w // BLOCK_SIZE

    if h_blocks < 4 or w_blocks < 4:
        result["message"] = "La imagen es demasiado pequeña."
        return result

    HEADER_BITS  = 32
    total_blocks = h_blocks * w_blocks

    if total_blocks < HEADER_BITS:
        result["message"] = "Imagen demasiado pequeña para contener datos."
        return result

    MAX_PAYLOAD = 50_000
    eof_bits    = len(EOF_MARKER) * 8

    for thresh in VARIANCE_THRESHOLDS:
        usable_order = _build_usable_order(work_f, h_blocks, w_blocks, password, thresh)
        if len(usable_order) < HEADER_BITS:
            continue

        def _read_bit(pos, _uo=usable_order):
            idx = _uo[pos]
            bi  = idx // w_blocks
            bj  = idx  % w_blocks
            r   = bi * BLOCK_SIZE
            c   = bj * BLOCK_SIZE
            return _extract_bit_from_block(_dct2(work_f[r : r + BLOCK_SIZE, c : c + BLOCK_SIZE]))

        header_bits    = [_read_bit(i) for i in range(HEADER_BITS)]
        payload_length = int.from_bytes(bits_to_bytes(header_bits), "big")

        if payload_length == 0 or payload_length > MAX_PAYLOAD:
            continue
        if HEADER_BITS + payload_length * 8 + eof_bits > len(usable_order):
            continue

        payload_bits  = [_read_bit(i) for i in range(HEADER_BITS, HEADER_BITS + payload_length * 8)]
        payload_bytes = bits_to_bytes(payload_bits)

        try:
            decoded_bytes = rs_decode(payload_bytes)
        except (reedsolo.ReedSolomonError, IndexError, ValueError):
            continue

        try:
            plaintext = aes_decrypt(decoded_bytes, password)
        except Exception:
            continue

        eof_start = HEADER_BITS + payload_length * 8
        eof_found = bits_to_bytes([_read_bit(i) for i in range(eof_start, eof_start + eof_bits)]) == EOF_MARKER

        result["success"] = True
        result["text"]    = plaintext
        result["message"] = (
            f"Mensaje extraido y descifrado con exito.\n"
            f"  Payload RS: {payload_length} bytes\n"
            f"  Marcador EOF: {'encontrado' if eof_found else 'no encontrado (OK)'}"
        )
        return result

    result["message"] = (
        "No se encontro un mensaje valido en la imagen.\n"
        "Causas posibles: imagen sin datos, reescalada, o recomprimida con calidad JPEG < 65."
    )
    return result
