# Stegocas

JPEG-resistant steganography tool. Hides AES-256-GCM encrypted text inside JPEG images by modifying DCT coefficients in the luminance channel. Survives JPEG recompression at quality >= 65 (WhatsApp, Telegram).

## How it works

### Embedding pipeline

    plaintext + password
        -> AES-256-GCM encryption  (PBKDF2 key derivation, 200k iterations)
        -> Reed-Solomon encoding   (RS(240,200), corrects up to 20 bytes/chunk)
        -> bitstream               (4B length header + RS payload + 4B EOF marker)
        -> DCT coefficient modification in Y channel
        -> JPEG output at quality 95

### Bit encoding in DCT blocks

Each 8x8 block holds one bit. Two mid-frequency coefficients are used:

    C1 at position (2,3),  C2 at position (3,2)
    mid = (C1 + C2) / 2

    bit=1  ->  C1 = mid + P,  C2 = mid - P   (C1 - C2 = +2P)
    bit=0  ->  C1 = mid - P,  C2 = mid + P   (C1 - C2 = -2P)

Using `mid` preserves the sum of the two coefficients, minimizing spatial distortion. With P=40, the imposed difference is ±80. The JPEG luminance quantization step at these positions is ~10 at q=80, giving an 8x margin. The embedding survives quantization as long as the difference remains larger than the step.

### Why the Y (luminance) channel

JPEG applies 4:2:0 chroma subsampling to Cb and Cr: each 2x2 pixel block is averaged to one chroma sample before quantization. This destroys embedded differences before any further recompression. The Y channel is never subsampled, so 8x8 DCT blocks in Y map 1:1 to the blocks the JPEG encoder processes.

### Block selection

Three mechanisms work together to distribute modifications invisibly:

1. **Variance filter** — blocks with pixel variance < 100 are skipped. Flat areas (sky, solid backgrounds) would show visible banding from even small DCT modifications. Unmodified blocks stay flat, so the extractor reconstructs the identical usable set without any metadata.

2. **Password-seeded permutation** — SHA-256(password) seeds a numpy RNG permutation of all block indices. Without the password, the block order is unknown.

3. **Spatial interleaving** — the permuted usable blocks are round-robin sorted by image row. This guarantees that the first k blocks written are drawn from all textured rows in equal proportion, preventing any horizontal band from concentrating artifacts.

### Extraction

The extractor rebuilds the same usable block list (same password -> same permutation, same image -> same variance values) and reads bits back by comparing C1 vs C2 in each block's DCT. Reed-Solomon corrects any bit errors introduced by recompression, then AES-GCM decrypts and authenticates the payload.

## Limitations

- Images larger than ~2000px may not extract correctly. The image used to embed and the image used to extract must have identical dimensions; if WhatsApp or another platform resizes the image, the block grid shifts and all data is lost.
- Recommended maximum: 1200px on the longest side.
- Minimum JPEG quality for reliable extraction: 65.

## Stack

- Python 3.12
- opencv-python — image I/O, YCrCb conversion
- scipy.fftpack — 2D DCT via separable 1D transforms
- cryptography — AES-256-GCM, PBKDF2-HMAC-SHA256
- reedsolo — Reed-Solomon codec
- tkinter — GUI

## Build

    # install dependencies
    pip install opencv-python numpy scipy cryptography reedsolo pyinstaller

    # compile to single exe
    pyinstaller --onefile --windowed --name StegoCAS \
        --hidden-import=scipy.fftpack \
        --hidden-import=reedsolo \
        main_gui.py

## Run tests

    python test_stego.py
