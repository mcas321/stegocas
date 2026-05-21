# stegocas
Stegocas is a steganography tool that hides encrypted text inside JPEG images that survive modern social network compression by modifying mid frequency DCT coefficients in the Y (luma) channel. Uses Reed-Solomon error correction to survive JPEG recompression, and password seeded block permutation + variance filtering to minimize visible artifacts.
