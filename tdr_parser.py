import math
import struct
from collections import Counter


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

def read_utf_strict(r, field_name, max_len=256):
    if r.remaining() < 2:
        raise EOFError(f"EOF reading UTF length for {field_name}")

    raw_len = r.data[r.pos:r.pos+2]
    length = struct.unpack(">H", raw_len)[0]
    print(f"[{field_name}] len_bytes={raw_len.hex()} length={length} pos={r.pos}")
    r.pos += 2

    if length == 0:
        print(f"[{field_name}] length=0 (empty string)")
        return ""

    if length > max_len or length > r.remaining():
        print(f"[{field_name}] CORRUPT: length={length}, remaining={r.remaining()}")
        # don’t try to decode; treat element as corrupt and bail
        raise ValueError(f"CORRUPT UTF length in {field_name}")

    raw = r.data[r.pos:r.pos+length]
    r.pos += length

    try:
        s = raw.decode("utf-8")
    except Exception as e:
        print(f"[{field_name}] CORRUPT UTF: raw={raw.hex()} error={e}")
        raise

    return s

def looks_like_tag_byte(b):
    # ASCII letters only for v5 tags: L, P, A, N, E, etc.
    return 0x41 <= b <= 0x5A  # 'A'..'Z'

def next_tag_pos(r, limit=64):
    """Scan ahead up to `limit` bytes for the next plausible tag."""
    start = r.pos
    for i in range(limit):
        if r.remaining() <= 0:
            break
        b = r.peek_byte(i)
        if looks_like_tag_byte(b):
            return start + i, chr(b)
    return None, None

def dump_context(r, label, window=32):
    start = max(0, r.pos - 16)
    end = min(len(r.data), r.pos + window)
    raw = r.data[start:end]
    print(f"[{label}] pos={r.pos} remaining={r.remaining()} "
          f"window[{start}:{end}]: {raw.hex()}")

def read_type_string_binary(r):
    tag = chr(r.read_byte())          # e.g. 'L'
    hi  = r.read_byte()
    lo  = r.read_byte()
    length = (hi << 8) | lo
    s = r.data[r.pos:r.pos+length]
    r.pos += length
    return tag, s.decode("ascii", errors="ignore")

def skip_binary_geometry(r):
    while r.remaining() > 4:
        b0 = r.peek_byte(0)

        # Must be ASCII letter
        if 0x41 <= b0 <= 0x5A or 0x61 <= b0 <= 0x7A:
            b1 = r.peek_byte(1)
            b2 = r.peek_byte(2)
            b3 = r.peek_byte(3)

            # Type string header pattern: <tag> 00 <len_hi> <len_lo>
            if b1 == 0x00 and (b2 != 0 or b3 != 0):
                return

        r.read_byte()

def parse_elements_v6_binary_only(r):
    # Skip all binary geometry until 'E'
    while r.remaining() > 0:
        b = r.peek_byte()
        if b == ord('E'):
            r.read_byte()
            break
        r.read_byte()

    return 0, 0, 0, 0, Counter()

def parse_elements(r, element_fmt, stats):
    """
    Unified element dispatcher.
    All version-specific parsing is delegated to external functions.
    """
    lines = points = areas = unknown = 0
    tag_counts = Counter()

    # --- v3 UTF --------------------------------------------------------------
    if element_fmt == "v3_utf":
        return parse_elements_v3_utf(r)

    # --- v3 BINARY -----------------------------------------------------------
    if element_fmt == "v3_binary":
        return parse_elements_v3_binary(r)

    # --- v6 BINARY ONLY ------------------------------------------------------
    if element_fmt == "v6_binary_only":
        return parse_elements_v6_binary_only(r)
        
    # --- v6 BINARY -----------------------------------------------------------
    if element_fmt == "v6":
        print(f"[v6 geom preamble] pos={r.pos} next32={r.data[r.pos:r.pos+32].hex()}")
        while r.remaining() > 0:
            try:
                before = r.pos
                print(f"[v6 BEFORE skip] pos={r.pos} next16={r.data[r.pos:r.pos+16].hex()}")
                before = r.pos
                skip_v6_geometry(r)
                print(f"[v6 AFTER skip] {before}->{r.pos} next16={r.data[r.pos:r.pos+16].hex()}")
                print(f"[v6] skipped geometry bytes: {before} -> {r.pos}, remaining={r.remaining()}")
                debug_v6_before_tag(r, "v6 tag scan")

                tag_pos = r.pos
                tag = chr(r.read_byte())
                print(f"[v6 tag] tag={tag!r} tag_pos={tag_pos} remaining={r.remaining()}")

                if tag in ('L','l'):
                    try:
                        parse_line_v6(r)
                        lines += 1
                        stats["lines"] += 1
                    except EOFError as e:
                        print(f"[v6 line ERROR] pos={r.pos} remaining={r.remaining()} error={e}")
                        stats.setdefault("corrupt_lines_v6", 0)
                        stats["corrupt_lines_v6"] += 1
                    continue

                if tag in ('P','p'):
                    parse_point_v6(r)
                    points += 1; stats["points"] += 1; continue
                if tag in ('A','a'):
                    parse_area_v6(r)
                    areas += 1; stats["areas"] += 1; continue

                tag_counts[tag] += 1
                unknown += 1
                stats["unknown"] += 1

            except EOFError as e:
                print(f"[v6 ERROR] EOF at pos={r.pos} remaining={r.remaining()} "
                      f"last_tag={tag!r} error={e}")
                break
        return lines, points, areas, unknown, tag_counts

    # --- v5 UTF --------------------------------------------------------------
    if element_fmt == "v5":
        debug_v5_tags(r, limit=10)

        while r.remaining() > 0:
            tag = chr(r.read_byte())
            print(f"[v5 tag]tag={tag!r} remaining={r.remaining()}")

            if tag in ('E','e'):
                print("[v5] End tag encountered")
                break

            if tag in ('N','n'):
                parse_note_v5(r)
                continue

            if tag in ('L','l'):
                try:
                    parse_line_v5(r)
                    lines += 1
                    stats["lines"] += 1
                except Exception:
                    stats["corrupt_lines_v5"] += 1
                continue

            if tag in ('P','p'):
                try:
                    parse_point_v5(r)
                    points += 1
                    stats["points"] += 1
                except Exception:
                    stats["corrupt_points_v5"] += 1
                continue

            if tag in ('A','a'):
                try:
                    parse_area_v5(r)
                    areas += 1
                    stats["areas"] += 1
                except Exception:
                    stats["corrupt_areas_v5"] += 1
                continue

            tag_counts[tag] += 1
            unknown += 1
            stats["unknown"] += 1

        return lines, points, areas, unknown, tag_counts

    # --- v4 UTF --------------------------------------------------------------
    if element_fmt == "v4":
        while r.remaining() > 0:
            tag = chr(r.read_byte())

            if tag in ('E','e'):
                break

            if tag in ('N','n'):
                parse_note_v4(r)
                continue

            if tag in ('L','l'):
                parse_line_v4(r)
                lines += 1
                stats["lines"] += 1
                continue

            if tag in ('P','p'):
                parse_point_v4(r)
                points += 1
                stats["points"] += 1
                continue

            if tag in ('A','a'):
                parse_area_v4(r)
                areas += 1
                stats["areas"] += 1
                continue

            tag_counts[tag] += 1
            unknown += 1
            stats["unknown"] += 1

        return lines, points, areas, unknown, tag_counts

    # --- v3 LEGACY -----------------------------------------------------------
    if element_fmt == "v3":
        while r.remaining() > 0:
            tag = chr(r.read_byte())

            if tag in ('E','e'):
                break

            if tag in ('N','n'):
                parse_note_v3(r)
                continue

            if tag in ('L','l'):
                parse_line_v3(r)
                lines += 1
                stats["lines"] += 1
                continue

            if tag in ('P','p'):
                parse_point_v3(r)
                points += 1
                stats["points"] += 1
                continue

            if tag in ('A','a'):
                parse_area_v3(r)
                areas += 1
                stats["areas"] += 1
                continue

            tag_counts[tag] += 1
            unknown += 1
            stats["unknown"] += 1

        return lines, points, areas, unknown, tag_counts

    # --- Unknown format ------------------------------------------------------
    raise ValueError(f"Unknown element_fmt {element_fmt}")


def skip_corrupt_element_v5(r, label):
    print(f"[{label}] attempting resync from pos={r.pos}")
    pos, tag = next_tag_pos(r)
    if pos is None:
        print(f"[{label}] no plausible tag found within resync window")
        r.pos = len(r.data)  # force EOF
    else:
        print(f"[{label}] resync to pos={pos} tag={tag!r}")
        r.pos = pos

def probe_geometry_v5(r, npts, label):
    if npts <= 0 or r.remaining() < 8:
        print(f"[{label}] no geometry to probe (npts={npts}, remaining={r.remaining()})")
        return

    raw = r.data[r.pos:r.pos+8]
    try:
        x, y = struct.unpack(">ff", raw)
        print(f"[{label}] first coords x={x} y={y} raw={raw.hex()}")
    except Exception as e:
        print(f"[{label}] INVALID first coords raw={raw.hex()} error={e}")

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
        line_type = read_utf_strict(r, "line_type_v5")
        group     = read_utf_strict(r, "group_v5")
        if line_type is None or group is None:
            print(f"[v5 line] CORRUPT type/group at off={off}, skipping element")
            skip_corrupt_element_v5(r,"[v5 line]")
            stats["corrupt_lines_v5"] += 1
            #return

        scrap_id = read_int_be(r, "v5 scrap_id")
        npts = read_int_be(r, "v5 npts")
        probe_geometry_v5(r, npts, "v5 line probe")

        print(f"[v5 line] off={off} type={line_type!r} group={group!r} "
              f"scrap_id={scrap_id} npts={npts} remaining={r.remaining()}")

        expected_bytes = npts * 8
        if npts < 0 or npts > 10000 or r.remaining() < expected_bytes:
            print(f"[v5 line] CORRUPT: npts={npts}, expected_bytes={expected_bytes}, remaining={r.remaining()}")
            stats["corrupt_lines_v5"] += 1
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
        stats["corrupt_lines_v5"] += 1
        raise

def parse_point_v5(r):
    off = r.pos
    tag_pos = off - 1
    dump_context(r, f"v5 point tag at {tag_pos}")

    point_type = read_utf_strict(r, "point_type_v5")
    group = read_utf_strict(r, "group_v5")
    if point_type is None or group is None:
        print(f"[v5 point] CORRUPT type/group at off={off}, skipping element")
        skip_corrupt_element_v5(r,"[v5 point]")
        stats["corrupt_points_v5"] += 1
        #return

    scrap_id = read_int_be(r, "v5 scrap_id")
    print(f"[v5 point] off={off} type={point_type!r} group={group!r} "
          f"scrap_id={scrap_id} remaining={r.remaining()}")

    if r.remaining() < 8:
        print(f"[v5 point] CORRUPT: not enough bytes for coords, remaining={r.remaining()}")
        stats["corrupt_points_v5"] += 1
        return

    r.read_int()
    r.read_float()
    r.read_float()

def parse_area_v5(r):
    off = r.pos
    tag_pos = off - 1
    dump_context(r, f"v5 area tag at {tag_pos}")

    area_type = read_utf_strict(r, "area_type_v5")
    group = read_utf_strict(r, "group_v5")
    if area_type is None or group is None:
        print(f"[v5 area] CORRUPT type/group at off={off}, skipping element")
        skip_corrupt_element_v5(r,"[v5 area]")
        stats["corrupt_areas_v5"] += 1
        #return

    scrap_id = read_int_be(r, "v5 scrap_id")
    npts = read_int_be(r, "v5 npts")

    print(f"[v5 area] off={off} type={area_type!r} group={group!r} "
          f"scrap_id={scrap_id} npts={npts} remaining={r.remaining()}")

    expected_bytes = npts * 8
    if npts < 0 or npts > 10000 or r.remaining() < expected_bytes:
        print(f"[v5 area] CORRUPT: npts={npts}, expected_bytes={expected_bytes}, remaining={r.remaining()}")
        stats["corrupt_areas_v5"] += 1
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


def parse_line_v3_binary(r):
    # Skip geometry before type string
    skip_binary_geometry(r)

    # Read type string (e.g. 'L', 'wall')
    type_tag, type_name = read_type_string_binary(r)

    # Skip geometry payload after type string
    skip_binary_geometry(r)
    
def parse_point_v3_binary(r):
    skip_binary_geometry(r)
    type_tag, type_name = read_type_string_binary(r)
    skip_binary_geometry(r)

def parse_area_v3_binary(r):
    skip_binary_geometry(r)
    type_tag, type_name = read_type_string_binary(r)
    skip_binary_geometry(r)

def parse_note_v3_binary(r):
    skip_binary_geometry(r)
    type_tag, type_name = read_type_string_binary(r)
    skip_binary_geometry(r)

def parse_elements_v3_binary(r):
    lines = points = areas = unknown = 0
    tag_counts = Counter()

    while r.remaining() > 0:
        skip_binary_geometry(r) 
        tag = chr(r.read_byte())

        if tag in ('E', 'e'):
            break

        if tag in ('N', 'n'):
            parse_note_v3_binary(r)
            continue

        if tag in ('L', 'l'):
            parse_line_v3_binary(r)
            lines += 1
            continue

        if tag in ('P', 'p'):
            parse_point_v3_binary(r)
            points += 1
            continue

        if tag in ('A', 'a'):
            parse_area_v3_binary(r)
            areas += 1
            continue

        # Unknown tag
        tag_counts[tag] += 1
        unknown += 1

    return lines, points, areas, unknown, tag_counts

def parse_elements_v3_utf(r):
    lines = points = areas = unknown = 0
    tag_counts = Counter()

    while r.remaining() > 0:
        tag = chr(r.read_byte())

        if tag in ('E', 'e'):
            break

        if tag in ('N', 'n'):
            parse_note_v3(r)
            continue

        if tag in ('L', 'l'):
            parse_line_v3(r)
            lines += 1
            continue

        if tag in ('P', 'p'):
            parse_point_v3(r)
            points += 1
            continue

        if tag in ('A', 'a'):
            parse_area_v3(r)
            areas += 1
            continue

        # Unknown tag
        tag_counts[tag] += 1
        unknown += 1

    return lines, points, areas, unknown, tag_counts


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

def debug_v6_before_tag(r, label):
    off = r.pos
    # show a small window around current pos
    window = r.data[off:off+32]
    print(f"[{label}] pos={off} remaining={r.remaining()} "
          f"next32={window.hex()}")

def skip_v6_layer_block(r):
    block_len = r.read_int()
    r.pos += block_len

def skip_v6_geometry(r):
    start = r.pos
    while r.remaining() > 0:
        b = r.peek_byte()
        if (65 <= b <= 90) or (97 <= b <= 122):
            break
        r.read_byte()
    if r.pos != start:
        print(f"[v6 skip_geom] {start}->{r.pos} skipped={r.pos-start} "
              f"next4={r.data[r.pos:r.pos+4].hex()}")


def parse_line_v6(r):
    start = r.pos - 1  # L was just read
    type_code = r.read_byte()
    group_code = r.read_byte()

    if r.remaining() < 2:
        raise EOFError("EOF reading npts_v6")

    raw_npts = r.data[r.pos:r.pos+2]
    npts_be = struct.unpack(">H", raw_npts)[0]
    npts_le = struct.unpack("<H", raw_npts)[0]
    print(f"[v6 line] start={start} type_code={type_code} group_code={group_code} "
          f"raw_npts={raw_npts.hex()} npts_be={npts_be} npts_le={npts_le} "
          f"remaining={r.remaining()}")

    npts = npts_be  # or decide based on heuristic later
    r.pos += 2

    print(f"[v6 line] start={start} type_code={type_code} group_code={group_code} "
          f"npts={npts} remaining={r.remaining()} raw_npts={raw_npts.hex()}")

    expected_bytes = npts * 8
    if r.remaining() < expected_bytes:
        print(f"[v6 line] CORRUPT? npts={npts} expected_bytes={expected_bytes} "
              f"remaining={r.remaining()}")

    for i in range(npts):
        if r.remaining() < 8:
            print(f"[v6 line] EOF risk before point {i}, remaining={r.remaining()}")
            break
        x = r.read_float()
        y = r.read_float()

def parse_point_v6(r):
    start = r.pos - 1
    type_code = r.read_byte()
    group_code = r.read_byte()
    print(f"[v6 point] start={start} type_code={type_code} group_code={group_code} "
          f"remaining={r.remaining()}")
    r.read_float()
    r.read_float()

def parse_area_v6(r):
    start = r.pos - 1
    type_code = r.read_byte()
    group_code = r.read_byte()

    if r.remaining() < 2:
        raise EOFError("EOF reading npts_v6")

    raw_npts = r.data[r.pos:r.pos+2]
    npts = struct.unpack(">H", raw_npts)[0]
    r.pos += 2

    print(f"[v6 area] start={start} type_code={type_code} group_code={group_code} "
          f"npts={npts} remaining={r.remaining()} raw_npts={raw_npts.hex()}")

    expected_bytes = npts * 8
    if r.remaining() < expected_bytes:
        print(f"[v6 area] CORRUPT? npts={npts} expected_bytes={expected_bytes} "
              f"remaining={r.remaining()}")

    for i in range(npts):
        if r.remaining() < 8:
            print(f"[v6 area] EOF risk before point {i}, remaining={r.remaining()}")
            break
        x = r.read_float()
        y = r.read_float()

def parse_end_v6(r):
    return

__all__ = [
    "sane_float",
    "looks_like_float",
    "find_bbox_start",
    "skip_v6_layer_block",
    "dump_context",
    "parse_elements",
    "debug_v5_tags",
    "debug_scan_v5",
    "parse_line_v3",
    "parse_point_v3",
    "parse_area_v3",
    "parse_note_v3",
    "parse_line_v3_binary",
    "parse_point_v3_binary",
    "parse_area_v3_binary",
    "parse_note_v3_binary",
    "parse_elements_v3_binary",
    "parse_elements_v3_utf",
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
