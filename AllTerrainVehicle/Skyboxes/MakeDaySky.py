"""
Makes the six images of a simple daytime sky for Quorum's Skybox: a blue
gradient from a pale horizon to a deeper zenith, soft clouds, and a hazy
grey-green below the horizon. Each pixel is worked out from its direction,
so the sides meet without seams.

The sides follow the cube map face table OpenGL and Vulkan share, with
Quorum's left-handed world (+x right, +y up, +z forward) and the files
Skybox:Load expects (Item26.md):
    right +x, left -x, top +y, bottom -y, front +z, back -z.

Usage: python3 MakeDaySky.py <output folder> [size]
Pure Python (no numpy), so a 512 sky takes about a minute.
"""
import math
import os
import struct
import sys
import zlib


def side_direction(side, u, v):
    """The direction through a point on a side. u runs -1 (left) to 1
    (right), v runs -1 (top row) to 1 (bottom row)."""
    if side == "right":
        return (1.0, -v, -u)
    if side == "left":
        return (-1.0, -v, u)
    if side == "top":
        return (u, 1.0, v)
    if side == "bottom":
        return (u, -1.0, -v)
    if side == "front":
        return (u, -v, 1.0)
    return (-u, -v, -1.0)  # back


def hash2(x, y):
    n = (x * 374761393 + y * 668265263) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def value_noise(x, y):
    xi, yi = math.floor(x), math.floor(y)
    xf, yf = x - xi, y - yi
    xs, ys = xf * xf * (3 - 2 * xf), yf * yf * (3 - 2 * yf)
    a = hash2(xi, yi)
    b = hash2(xi + 1, yi)
    c = hash2(xi, yi + 1)
    d = hash2(xi + 1, yi + 1)
    return (a + (b - a) * xs) + ((c + (d - c) * xs) - (a + (b - a) * xs)) * ys


def clouds(x, y):
    total, amplitude, frequency = 0.0, 0.5, 1.0
    for _ in range(4):
        total += value_noise(x * frequency, y * frequency) * amplitude
        amplitude *= 0.5
        frequency *= 2.03
    return total


def smoothstep(edge0, edge1, value):
    t = max(0.0, min(1.0, (value - edge0) / (edge1 - edge0)))
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


HORIZON = (0.78, 0.86, 0.94)
ZENITH = (0.22, 0.45, 0.82)
GROUND = (0.50, 0.55, 0.52)
CLOUD_LIGHT = (0.98, 0.98, 0.99)
CLOUD_SHADE = (0.78, 0.80, 0.85)


def sky_color(direction):
    x, y, z = direction
    length = math.sqrt(x * x + y * y + z * z)
    x, y, z = x / length, y / length, z / length
    if y < 0:
        # Below the horizon: haze fading into a plain ground color.
        return mix(HORIZON, GROUND, smoothstep(0.0, 0.25, -y))
    color = mix(HORIZON, ZENITH, math.sqrt(y))
    if y > 0.01:
        # Clouds on a flat layer overhead, thinning toward the horizon.
        scale = 1.6 / (y + 0.12)
        density = clouds(x * scale + 17.0, z * scale - 9.0)
        cover = smoothstep(0.52, 0.72, density) * smoothstep(0.01, 0.2, y)
        cloud = mix(CLOUD_SHADE, CLOUD_LIGHT, smoothstep(0.5, 0.8, density))
        color = mix(color, cloud, cover * 0.9)
    return color


def write_png(path, size, rows):
    raw = b"".join(b"\x00" + bytes(row) for row in rows)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    folder = sys.argv[1]
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 512
    os.makedirs(folder, exist_ok=True)
    for side in ("right", "left", "top", "bottom", "front", "back"):
        rows = []
        for row in range(size):
            v = (row + 0.5) / size * 2 - 1
            pixels = []
            for column in range(size):
                u = (column + 0.5) / size * 2 - 1
                color = sky_color(side_direction(side, u, v))
                pixels.extend(max(0, min(255, int(round(c * 255)))) for c in color)
            rows.append(pixels)
        write_png(os.path.join(folder, side + ".png"), size, rows)
        print("wrote", side)


if __name__ == "__main__":
    main()
