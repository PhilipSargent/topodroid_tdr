import math
import struct

def sane_float(f):
    return math.isfinite(f) and -1e6 < f < 1e6

def looks_like_float(b):
    try:
        f = struct.unpack(">f", b)[0]
        return sane_float(f)
    except Exception:
        return False

def find_bbox_start(r):
    start = r.pos
    data = r.data
    n = len(data)

    for i in range(start, n - 16):
        f1 = struct.unpack(">f", data[i:i+4])[0]
        f2 = struct.unpack(">f", data[i+4:i+8])[0]
        f3 = struct.unpack(">f", data[i+8:i+12])[0]
        f4 = struct.unpack(">f", data[i+12:i+16])[0]

        if all(sane_float(f) for f in (f1, f2, f3, f4)):
            return i

    raise ValueError("BBox not found")

def read_int_be(r, label):
    if r.remaining() < 4:
        raise EOFError(f"EOF reading {label}")
    raw = r.data[r.pos:r.pos+4]
    v = struct.unpack(">i", raw)[0]
    print(f"[{label}] raw={raw.hex()} value={v}")
    r.pos += 4
    return v

def safe_read_utf(r, field_name, max_len=256):
    if r.remaining() < 2:
        raise EOFError(f"EOF reading UTF length for {field_name}")

    raw_len = r.data[r.pos:r.pos+2]
    length = struct.unpack(">H", raw_len)[0]
    print(f"[{field_name}] len_bytes={raw_len.hex()} length={length} pos={r.pos}")

    if length == 0 or length > max_len or length > r.remaining() - 2:
        print(f"[{field_name}] CORRUPT: length={length}, remaining={r.remaining()}")
        return None

    r.pos += 2

    if r.remaining() < length:
        raise EOFError(f"EOF reading UTF bytes for {field_name}")

    raw = r.data[r.pos:r.pos+length]
    r.pos += length

    try:
        s = raw.decode("utf-8")
    except Exception as e:
        print(f"[{field_name}] CORRUPT UTF: raw={raw.hex()} error={e}")
        return None

    for c in s:
        if ord(c) < 32 and c not in ("\n", "\r", "\t"):
            print(f"[{field_name}] CORRUPT: control char in {s!r}")
            return None

    print(f"[{field_name}] value={s!r}")
    return s

def dump_context(r, label, window=32):
    start = max(0, r.pos - 16)
    end = min(len(r.data), r.pos + window)
    raw = r.data[start:end]
    print(f"[{label}] pos={r.pos} remaining={r.remaining()} "
          f"window[{start}:{end}]: {raw.hex()}")


def debug_v5_tags(r, limit=20):
    print("\n--- DEBUG V5 TAGS ---")
    start_pos = r.pos
    count = 0

    while r.remaining() > 0 and count < limit:
        off = r.pos
        b = r.read_byte()
        ch = chr(b) if 32 <= b <= 126 else '.'
        print(f"offset {off:06d}: tag byte=0x{b:02x} '{ch}'")
        raw = r.data[r.pos:r.pos+16]
        print(f"    next 16 bytes: {raw.hex()}")
        count += 1

    print(f"--- END DEBUG V5 TAGS (scanned {count} tags) ---")
    r.pos = start_pos

def debug_scan_v5(r, limit=200):
    print("\n--- DEBUG SCAN V5 GEOMETRY ---")
    count = 0

    while r.remaining() > 0 and count < limit:
        off = r.pos
        b = r.read_byte()
        print(f"offset {off:06d}: byte=0x{b:02x}", end='')
        if 32 <= b <= 126:
            print(f" '{chr(b)}'", end='')
        print()

        if r.remaining() >= 4:
            raw = r.data[r.pos:r.pos+4]
            try:
                f = struct.unpack("<f", raw)[0]
                print(f"    next float32 (LE) = {f}")
            except Exception as e:
                print(f"    next float32 (LE) = INVALID ({e})")
        else:
            print("    next float32 (LE) = <EOF>")

        count += 1

    print(f"--- END DEBUG SCAN (scanned {count} bytes) ---\n")

def parse_geometry_v5(r):
    coords = 0
    while r.remaining() >= 8:
        x = r.read_float()
        y = r.read_float()
        coords += 1
    return coords

def parse_line_v5(r):
    off = r.pos
    tag_pos = off - 1
    dump_context(r, f"v5 line tag at {tag_pos}")
    try:
        line_type = safe_read_utf(r, "line_type_v5")
        group = safe_read_utf(r, "group_v5")
        if line_type is None or group is None:
            print(f"[v5 line] CORRUPT type/group at off={off}, skipping element")
            return

        scrap_id = read_int_be(r, "v5 scrap_id")
        npts = read_int_be(r, "v5 npts")

        print(f"[v5 line] off={off} type={line_type!r} group={group!r} "
              f"scrap_id={scrap_id} npts={npts} remaining={r.remaining()}")

        expected_bytes = npts * 8
        if npts < 0 or npts > 10000 or r.remaining() < expected_bytes:
            print(f"[v5 line] CORRUPT: npts={npts}, expected_bytes={expected_bytes}, remaining={r.remaining()}")
            return

        for i in range(npts):
            if r.remaining() < 8:
                print(f"[v5 line] EOF risk before point {i}, remaining={r.remaining()}")
                break
            x = r.read_float()
            y = r.read_float()
    except Exception as e:
        print(f"[v5 line ERROR] off={off} pos={r.pos} remaining={r.remaining()} "
              f"error={e}")
        dump_context(r, "v5 line ERROR")
        raise

def parse_point_v5(r):
    off = r.pos
    tag_pos = off - 1
    dump_context(r, f"v5 point tag at {tag_pos}")

    point_type = safe_read_utf(r, "point_type_v5")
    group = safe_read_utf(r, "group_v5")
    if point_type is None or group is None:
        print(f"[v5 point] CORRUPT type/group at off={off}, skipping element")
        return

    scrap_id = read_int_be(r, "v5 scrap_id")
    print(f"[v5 point] off={off} type={point_type!r} group={group!r} "
          f"scrap_id={scrap_id} remaining={r.remaining()}")

    if r.remaining() < 8:
        print(f"[v5 point] CORRUPT: not enough bytes for coords, remaining={r.remaining()}")
        return

    r.read_int()
    r.read_float()
    r.read_float()

def parse_area_v5(r):
    off = r.pos
    tag_pos = off - 1
    dump_context(r, f"v5 area tag at {tag_pos}")

    area_type = safe_read_utf(r, "area_type_v5")
    group = safe_read_utf(r, "group_v5")
    if area_type is None or group is None:
        print(f"[v5 area] CORRUPT type/group at off={off}, skipping element")
        return

    scrap_id = read_int_be(r, "v5 scrap_id")
    npts = read_int_be(r, "v5 npts")

    print(f"[v5 area] off={off} type={area_type!r} group={group!r} "
          f"scrap_id={scrap_id} npts={npts} remaining={r.remaining()}")

    expected_bytes = npts * 8
    if npts < 0 or npts > 10000 or r.remaining() < expected_bytes:
        print(f"[v5 area] CORRUPT: npts={npts}, expected_bytes={expected_bytes}, remaining={r.remaining()}")
        return

    for i in range(npts):
        if r.remaining() < 8:
            print(f"[v5 area] EOF risk before point {i}, remaining={r.remaining()}")
            break
        x = r.read_float()
        y = r.read_float()

def parse_note_v5(r):
    r.read_byte()
    r.read_byte()
    r.read_byte()


def parse_line_v3(r):
    line_type = r.read_utf("line_type_v3")
    group = r.read_utf("group_v3")
    npts = r.read_int()
    for _ in range(npts):
        r.read_float()
        r.read_float()

def parse_point_v3(r):
    point_type = r.read_utf("point_type_v3")
    group = r.read_utf("group_v3")
    r.read_float()
    r.read_float()

def parse_area_v3(r):
    area_type = r.read_utf("area_type_v3")
    group = r.read_utf("group_v3")
    npts = r.read_int()
    for _ in range(npts):
        r.read_float()
        r.read_float()

def parse_note_v3(r):
    r.read_byte()
    r.read_byte()
    r.read_byte()


def parse_line_v4(r):
    line_type = r.read_utf("line_type_v4")
    group = r.read_utf("group_v4")
    npts = r.read_int()
    for _ in range(npts):
        r.read_float()
        r.read_float()

def parse_point_v4(r):
    point_type = r.read_utf("point_type_v4")
    group = r.read_utf("group_v4")
    r.read_float()
    r.read_float()

def parse_area_v4(r):
    area_type = r.read_utf("area_type_v4")
    group = r.read_utf("group_v4")
    npts = r.read_int()
    for _ in range(npts):
        r.read_float()
        r.read_float()

def parse_note_v4(r):
    # placeholder for v4 note handling
    pass


def skip_v6_layer_block(r):
    block_len = r.read_int()
    r.pos += block_len

def skip_v6_geometry(r):
    while r.remaining() > 0:
        b = r.peek_byte()
        if (65 <= b <= 90) or (97 <= b <= 122):
            return
        r.read_byte()

def parse_line_v6(r):
    type_code = r.read_byte()
    group_code = r.read_byte()
    if r.remaining() < 2:
        raise EOFError("EOF reading npts_v6")
    npts = struct.unpack(">H", r.data[r.pos:r.pos+2])[0]
    r.pos += 2
    for _ in range(npts):
        r.read_float()
        r.read_float()

def parse_point_v6(r):
    type_code = r.read_byte()
    group_code = r.read_byte()
    r.read_float()
    r.read_float()

def parse_area_v6(r):
    type_code = r.read_byte()
    group_code = r.read_byte()
    if r.remaining() < 2:
        raise EOFError("EOF reading npts_v6")
    npts = struct.unpack(">H", r.data[r.pos:r.pos+2])[0]
    r.pos += 2
    for _ in range(npts):
        r.read_float()
        r.read_float()

def parse_end_v6(r):
    return
__all__ = [
    "sane_float",
    "looks_like_float",
    "find_bbox_start",
    "td_version_major",
    "skip_v6_layer_block",
    "dump_context",
    "debug_v5_tags",
    "debug_scan_v5",
    "parse_line_v3",
    "parse_point_v3",
    "parse_area_v3",
    "parse_note_v3",
    "parse_line_v4",
    "parse_point_v4",
    "parse_area_v4",
    "parse_note_v4",
    "parse_geometry_v5",
    "parse_note_v5",
    "read_int_be",
    "safe_read_utf",
    "parse_line_v5",
    "parse_point_v5",
    "parse_area_v5",
    "skip_v6_geometry",
    "parse_line_v6",
    "parse_point_v6",
    "parse_end_v6",
    "parse_area_v6",
]
