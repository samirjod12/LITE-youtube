"""Generate assets/icon.ico (original blue play icon) with the standard library only.
To use your own icon, replace assets/icon.ico with a real .ico file and rebuild."""
import struct
import sys
import zlib
from pathlib import Path

SIZE, SS = 256, 3
BLUE, WHITE = (0x28, 0x78, 0xE5), (255, 255, 255)


def inside_round_rect(x, y, n, r):
    cx = min(max(x, r), n - r)
    cy = min(max(y, r), n - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def in_triangle(px, py, a, b, c):
    def s(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
    d1, d2, d3 = s((px, py), a, b), s((px, py), b, c), s((px, py), c, a)
    return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))


def render():
    n, r = SIZE, SIZE * 0.22
    a, b, c = (n * .38, n * .28), (n * .38, n * .72), (n * .74, n * .50)
    rows = []
    for y in range(n):
        row = bytearray([0])
        for x in range(n):
            cov = wh = 0
            for sy in range(SS):
                for sx in range(SS):
                    fx, fy = x + (sx + .5) / SS, y + (sy + .5) / SS
                    if inside_round_rect(fx, fy, n, r):
                        cov += 1
                        if in_triangle(fx, fy, a, b, c):
                            wh += 1
            tot = SS * SS
            if cov == 0:
                row += bytes((0, 0, 0, 0))
            else:
                t = wh / cov
                col = tuple(round(BLUE[i] * (1 - t) + WHITE[i] * t) for i in range(3))
                row += bytes((*col, round(255 * cov / tot)))
        rows.append(bytes(row))
    return b"".join(rows)


def png(raw):
    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "assets/icon.ico")
    out.parent.mkdir(parents=True, exist_ok=True)
    data = png(render())
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(data), 22)   # 0 = 256 px
    out.write_bytes(header + entry + data)
    print("wrote", out, len(data) + 22, "bytes")


if __name__ == "__main__":
    main()
