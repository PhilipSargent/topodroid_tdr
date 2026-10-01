#!/usr/bin/env python3
import struct
import sys
import os
import collections
from pathlib import Path
from collections import defaultdict, Counter

FILENUMBER = 0
versions_dict = defaultdict(int)

import math

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


def td_version_major(version_int):
    # 501040 -> 5, 301040 -> 3, 602012 -> 6
    return version_int // 100000


def skip_v6_layer_block(r):
    block_len = r.read_int()      # length of binary layer block
    r.pos += block_len            # skip it



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
                f = struct.unpack("<f", raw)[0]  # LITTLE-ENDIAN
                print(f"    next float32 (LE) = {f}")
            except Exception as e:
                print(f"    next float32 (LE) = INVALID ({e})")
        else:
            print("    next float32 (LE) = <EOF>")

        count += 1

    print(f"--- END DEBUG SCAN (scanned {count} bytes) ---\n")



def parse_line_v3(r):
    # l <type UTF> <group UTF> <npts int> <pts>
    line_type = r.read_utf("line_type_v3")
    group = r.read_utf("group_v3")
    npts = r.read_int()
    for _ in range(npts):
        r.read_float()
        r.read_float()

def parse_point_v3(r):
    # p <type UTF> <group UTF> <x float> <y float>
    point_type = r.read_utf("point_type_v3")
    group = r.read_utf("group_v3")
    r.read_float()
    r.read_float()

def parse_area_v3(r):
    # a <type UTF> <group UTF> <npts int> <pts>
    area_type = r.read_utf("area_type_v3")
    group = r.read_utf("group_v3")
    npts = r.read_int()
    for _ in range(npts):
        r.read_float()
        r.read_float()
        
def parse_note_v3(r):
    # N <3-byte payload> then next tag
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

def parse_geometry_v5(r):
    # v5 geometry = pure float32 coordinate pairs
    coords = 0
    while r.remaining() >= 8:
        x = r.read_float()
        y = r.read_float()
        coords += 1
    return coords

def parse_note_v5(r):
    # N <3-byte payload> then next tag
    r.read_byte()
    r.read_byte()
    r.read_byte()

def parse_line_v5(r):
    # L <UTF line_type> <UTF group_type> <int scrap_id?> <int npts> <points>
    line_type = r.read_utf("line_type_v5")
    group = r.read_utf("group_v5")
    scrap_id = r.read_int()
    npts = r.read_int()
    for _ in range(npts):
        r.read_float()
        r.read_float()

def parse_point_v5(r):
    # P <UTF point_type> <UTF group_type> <int scrap_id?> <float x> <float y>
    point_type = r.read_utf("point_type_v5")
    group = r.read_utf("group_v5")
    scrap_id = r.read_int()
    r.read_float()
    r.read_float()

def parse_area_v5(r):
    # A <UTF area_type> <UTF group_type> <int scrap_id?> <int npts> <points>
    area_type = r.read_utf("area_type_v5")
    group = r.read_utf("group_v5")
    scrap_id = r.read_int()
    npts = r.read_int()
    for _ in range(npts):
        r.read_float()
        r.read_float()
        
def skip_v6_geometry(r):
    """
    Skip the v6 geometry block.

    v6 geometry is binary (float32, int32, packed bits).
    It contains NO ASCII tag bytes.

    The first ASCII letter marks the start of the tag stream.
    """
    while r.remaining() > 0:
        b = r.peek_byte()

        # ASCII letters: A–Z or a–z
        if (65 <= b <= 90) or (97 <= b <= 122):
            # Found the first real tag
            return

        # Otherwise skip this byte
        r.read_byte()


def parse_line_v6(r):
    # L <byte type_code> <byte group_code> <uint16 npts> <points>

    type_code = r.read_byte()       # NOT UTF
    group_code = r.read_byte()      # NOT UTF

    # npts is uint16
    if r.remaining() < 2:
        raise EOFError("EOF reading npts_v6")
    npts = struct.unpack(">H", r.data[r.pos:r.pos+2])[0]
    r.pos += 2

    # points are float32 pairs
    for _ in range(npts):
        r.read_float()
        r.read_float()

def parse_point_v6(r):
    # P <byte type_code> <byte group_code> <float x> <float y>

    type_code = r.read_byte()
    group_code = r.read_byte()
    r.read_float()
    r.read_float()
    
def parse_end_v6(r):
    # E (no payload)
    return
    
def parse_area_v6(r):
    # A <byte type_code> <byte group_code> <uint16 npts> <points>

    type_code = r.read_byte()
    group_code = r.read_byte()

    if r.remaining() < 2:
        raise EOFError("EOF reading npts_v6")
    npts = struct.unpack(">H", r.data[r.pos:r.pos+2])[0]
    r.pos += 2

    for _ in range(npts):
        r.read_float()
        r.read_float()

# ------------------------------------------------------------
# Directory scanner (pathlib version)
# ------------------------------------------------------------

def scan_directory(root: Path):
    print(f"Scanning directory: {root}")

    for path in root.rglob("*.tdr"):
        print("\n----------------------------------------")
        check_tdr(path)
        print("----------------------------------------")

                
# ------------------------------------------------------------
# Safe binary reader
# ------------------------------------------------------------

class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0
        
    def read_int_le(self):
        if self.remaining() < 4:
            raise EOFError("EOF reading int_le")
        v = struct.unpack("<i", self.data[self.pos:self.pos+4])[0]
        self.pos += 4
        return v
        
    def read_cstring(self, field_name):
        # print(f"\n[{field_name}] ENTER read_cstring: pos={self.pos}")
        # print(f"[{field_name}] id(self.data)={id(self.data)} id(self)={id(self)}")


        start = self.pos

        # Walk until null
        while self.remaining() > 0 and self.data[self.pos] != 0x00:
            self.pos += 1

        # print(f"[{field_name}] after scan: start={start}, end={self.pos}, "
              # f"byte_at_end=0x{self.data[self.pos]:02x} "
              # f"(remaining={self.remaining()})")

        if self.remaining() == 0:
            raise EOFError(f"EOF reading cstring for {field_name}")

        raw = self.data[start:self.pos]
        # print(f"[{field_name}] raw bytes: {raw.hex()}")

        # Skip exactly one null terminator
        # print(f"[{field_name}] skipping null at pos={self.pos}")
        self.pos += 1
        # print(f"[{field_name}] EXIT read_cstring: new pos={self.pos}")

        try:
            s = raw.decode("utf-8")
            # print(f"[{field_name}] decoded: {s!r}")
            return s
        except Exception:
            raise ValueError(f"CORRUPT HEADER: invalid C-string in {field_name}")



    def remaining(self):
        return len(self.data) - self.pos

    def read_byte(self):
        if self.remaining() < 1:
            raise EOFError("EOF reading byte")
        b = self.data[self.pos]
        self.pos += 1
        return b

    def read_int(self):
        if self.remaining() < 4:
            raise EOFError("EOF reading int")
        v = struct.unpack(">i", self.data[self.pos:self.pos+4])[0]
        self.pos += 4
        return v
        
    def read_float(self):
        if self.remaining() < 4:
            raise EOFError("EOF reading float")
        val = struct.unpack(">f", self.data[self.pos:self.pos+4])[0]
        self.pos += 4
        return val

    def peek_byte(self, offset=0):
        """Return the byte at current position + offset without advancing."""
        idx = self.pos + offset
        if idx < 0 or idx >= len(self.data):
            raise EOFError("EOF in peek_byte")
        return self.data[idx]

    def read_utf(self, field_name):
        if self.remaining() < 2:
            raise EOFError(f"EOF reading UTF length for {field_name}")

        length = struct.unpack(">H", self.data[self.pos:self.pos+2])[0]
        self.pos += 2

        if self.remaining() < length:
            raise EOFError(f"EOF reading UTF bytes for {field_name}")

        raw = self.data[self.pos:self.pos+length]
        self.pos += length

        try:
            s = raw.decode("utf-8")
        except Exception:
            raise ValueError(f"CORRUPT HEADER: invalid UTF in {field_name}")

        # Reject control chars
        for c in s:
            if ord(c) < 32 and c not in ("\n", "\r", "\t"):
                raise ValueError(f"CORRUPT HEADER: control chars in {field_name}")

        return s
        
def dispatch_by_version(version):
    if version == 602012:
        return ("v5_cstring_header", "v6")

    if version == 602011:
        return ("v5_length_header", "v6")

    if version == 501040:
        return ("v5_length_header2", "v5")
        
    if version == 401092 or version == 400020 :
        return ("v4_header", "v4")
 
    if version == 301040:
        return ("v3_header", "v3_binary")

    if version == 301004:
        return ("v3_header", "v3_utf")


    if version == 301040:
        return ("v3_header", "v3")

    raise ValueError(f"Unsupported TD version {version}")


def detect_format_v5_or_v6(r: Reader) -> str:
    """
    Detect whether a 'v6' file is actually v5-format or v6-format.

    After the header, v5 files always start with ASCII tag letters:
        N, L, P, A, E, ...

    v6 files always start with binary geometry (float32), which
    begins with non-ASCII bytes (0x00, 0x42, 0x9C, etc).
    """

    start_pos = r.pos

    # Skip padding zeros
    while r.remaining() > 0 and r.peek_byte() == 0x00:
        r.read_byte()

    if r.remaining() == 0:
        r.pos = start_pos
        return "unknown"

    b = r.peek_byte()

    # ASCII letters = v5 format
    if 65 <= b <= 90 or 97 <= b <= 122:
        r.pos = start_pos
        return "v5"

    # Otherwise v6 (binary geometry)
    r.pos = start_pos
    return "v6"

# ------------------------------------------------------------
# Manifest loader
# ------------------------------------------------------------
def td_version_to_int(ver: str) -> int:
    # "5.1.40" -> 5, 1, 40 -> "5" + "01" + "040" -> 501040
    parts = ver.split(".")
    if len(parts) != 3:
        raise ValueError(f"Unexpected TopoDroid version format: {ver}")

    major = int(parts[0])
    minor = int(parts[1])
    patch = int(parts[2])

    return int(f"{major}{minor:02d}{patch:03d}")
    
    # Expected format:
    # 5.1.40 501040
    # 43
    # gruffalo_ninky_knonk
    # 2025.09.01
    
    # or
    # 3.1.4
    # 27
    # 101_real
    # 2016.06.26
    
    # or
    # 3.1.4a
    # 27
    # 101_real
    # 2016.06.26

def load_manifest(path: Path):
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]

    first = lines[0].split()

    if len(first) == 2:
        # New format (TopoDroid 5.x)
        td_version = first[0]
        tdr_version = int(first[1])
        schema_version = int(lines[1])
        survey_name = lines[2]
        date = lines[3]
        
        if tdr_version != td_version_to_int(td_version):
            raise ValueError("Manifest version numbers inconsistent")

    elif len(first) == 1:
        # Old format (TopoDroid 3.x)
        td_version = first[0]
        if td_version[-1] in ["a", "b", "c"]:
            # strip
            tdr_version = td_version_to_int(td_version[:-1])
        else:
            tdr_version = td_version_to_int(td_version)
        schema_version = int(lines[1])
        survey_name = lines[2]
        date = lines[3]

    else:
        raise ValueError("Unrecognised manifest format")

    return {
        "td_version": td_version,
        "tdr_version": tdr_version,
        "schema_version": schema_version,
        "survey_name": survey_name,
        "date": date,
    }


# ------------------------------------------------------------
# Main checker
# ------------------------------------------------------------
        
def read_len_string(r):
    length = r.read_byte()
    s = r.data[r.pos:r.pos+length]
    r.pos += length
    return s.decode("ascii", errors="ignore")

def parse_header_v5_length(r):
    layer = read_len_string(r)
    wall  = read_len_string(r)
    water = read_len_string(r)
    material = read_len_string(r)
    
    #print("pos after material:", r.pos)
    #print("Next 32 bytes:", r.data[r.pos:r.pos+32].hex())
    # Now capture the raw ASCII block starting at the NUL
    start = r.pos
    r.read_byte()  # skip the leading 0x00
    # read until BBox start
    bbox_pos = find_bbox_start(r)
    material2 = r.data[start+1:bbox_pos].decode("ascii", errors="ignore")
    print(f"{material2=}")
    
    # BBox
    r.pos = bbox_pos
    
    raw = r.data[r.pos:r.pos+16]
    x1 = struct.unpack(">f", raw[0:4])[0]
    y1 = struct.unpack(">f", raw[4:8])[0]
    x2 = struct.unpack(">f", raw[8:12])[0]
    y2 = struct.unpack(">f", raw[12:16])[0]
    r.pos += 16

    return {
        "layer": layer,
        "wall": wall,
        "water": water,
        "material": material,
        "material2": material2,
        "bbox": (x1, y1, x2, y2),
    }

def parse_header_v5_cstring(r):
    layer = r.read_cstring("layer")
    wall  = r.read_cstring("wall")
    water = r.read_cstring("water")

    # material: ASCII until BBox start
    bbox_pos = find_bbox_start(r)
    material = r.data[r.pos:bbox_pos].decode("ascii", errors="ignore")
    r.pos = bbox_pos

    # BBox
    raw = r.data[r.pos:r.pos+16]
    x1 = struct.unpack(">f", raw[0:4])[0]
    y1 = struct.unpack(">f", raw[4:8])[0]
    x2 = struct.unpack(">f", raw[8:12])[0]
    y2 = struct.unpack(">f", raw[12:16])[0]
    r.pos += 16

    return {
        "layer": layer,
        "wall": wall,
        "water": water,
        "material": material,
        "bbox": (x1, y1, x2, y2),
    }

def read_v5_field(r):
    r.read_byte()  # swallow leading 0x00 (empty C-string)
    length = r.read_byte()
    s = r.data[r.pos:r.pos+length]
    r.pos += length
    return s.decode("ascii", errors="ignore")

def parse_header_v5_len(r):
    """This format has no materials field and no Bounding Box either
    """
    layer = read_v5_field(r)
    wall  = read_v5_field(r)
    water = read_v5_field(r)
    #material = read_v5_field(r)

    # # BBox
    # raw = r.data[r.pos:r.pos+16]
    # x1 = struct.unpack(">f", raw[0:4])[0]
    # y1 = struct.unpack(">f", raw[4:8])[0]
    # x2 = struct.unpack(">f", raw[8:12])[0]
    # y2 = struct.unpack(">f", raw[12:16])[0]
    # r.pos += 16

    return {
        "layer": layer,
        "wall": wall,
        "water": water,
    }

def read_v4_field(r):
    r.read_byte()          # leading 0x00
    length = r.read_byte() # length
    s = r.data[r.pos:r.pos+length]
    r.pos += length
    return s.decode("ascii", errors="ignore")

def parse_header_v4(r):
    layer = read_v4_field(r)
    wall  = read_v4_field(r)
    water = read_v4_field(r)

    return {
        "layer": layer,
        "wall": wall,
        "water": water,
    }
    # element stream starts here: r.pos is at first v4 tag

def read_v3_field(r):
    r.read_byte()          # leading 0x00
    length = r.read_byte() # length
    s = r.data[r.pos:r.pos+length]
    r.pos += length
    return s.decode("ascii", errors="ignore")

def parse_header_v3(r):
    layer = read_v3_field(r)
    wall  = read_v3_field(r)
    water = read_v3_field(r)

    return {
        "layer": layer,
        "wall": wall,
        "water": water,
    }
    # v3 elements start at r.pos

 
def parse_header(r, header_fmt):
    """
    Parse the header according to v3/v4/v5 rules.
    TD6/v5 hybrid uses v5 header.
    """
        # Detect format BEFORE reading layer/wall/water/BBox
    print("Detector peek byte:", hex(r.peek_byte()))
    print("Detector peek char:", repr(chr(r.peek_byte())))
    print("Detector pos:", r.pos)

    if header_fmt == "v5_cstring_header":
        return parse_header_v5_cstring(r)

    if header_fmt == "v5_length_header":
        return parse_header_v5_length(r)

    if header_fmt == "v5_length_header2":
        return parse_header_v5_len(r)

    if header_fmt == "v4_header":
        return parse_header_v4(r)

    if header_fmt == "v3_header":
        return parse_header_v3(r)

    raise ValueError(f"Unknown header_fmt {header_fmt}")


def parse_header_old(r, header_fmt):
        
  
    ###########################################################
    # Header strings differ by major
    if major == 5:
        # true v5: UTF-length-prefixed
        layer = r.read_utf("layer")
        wall  = r.read_utf("wall")
        water = r.read_utf("water")
        material = ""
        print("After water, next 16 bytes:", r.data[r.pos:r.pos+16].hex())

        print("UTF-length-prefixed:")
    else:
        # TD6 (602011/602012): zero-terminated ASCII C-strings
        # print(f"pos before layer: {r.pos}")
        # print("Outside id(r.data)=", id(r.data), "id(r)=", id(r))
        layer = r.read_cstring("layer")
        # print(f"pos before wall: {r.pos}")
        wall  = r.read_cstring("wall")
        # print(f"pos before water: {r.pos}")
        water = r.read_cstring("water")
        print("Byte before water:", hex(r.data[r.pos-1]))
        print("Byte at water start:", hex(r.data[r.pos]))

        print("After water, next 16 bytes:", r.data[r.pos:r.pos+16].hex())
        
        bbox_pos = find_bbox_start(r)
        material = r.data[r.pos:bbox_pos].decode("ascii", errors="ignore")
        r.pos = bbox_pos
        print("material:", repr(material))
        print("zero-terminated ASCII C-strings:")
        
        
    ###########################################################
    # Show where we think the BBox starts
    print(f"BBox starts at offset {r.pos}")

    # Grab raw 16 bytes
    raw_bbox = r.data[r.pos:r.pos+16]
    print("Raw BBox bytes:", raw_bbox.hex())

    if len(raw_bbox) < 16:
        raise EOFError("EOF reading raw BBox bytes")

    # Read raw 16 bytes of BBox without committing to an interpretation yet
    raw_bbox = r.data[r.pos:r.pos+16]
    if len(raw_bbox) < 16:
        raise EOFError("EOF reading raw BBox bytes")

    # Big-endian interpretation
    x1_be = struct.unpack(">f", raw_bbox[0:4])[0]
    y1_be = struct.unpack(">f", raw_bbox[4:8])[0]
    x2_be = struct.unpack(">f", raw_bbox[8:12])[0]
    y2_be = struct.unpack(">f", raw_bbox[12:16])[0]

    # Little-endian interpretation
    x1_le = struct.unpack("<f", raw_bbox[0:4])[0]
    y1_le = struct.unpack("<f", raw_bbox[4:8])[0]
    x2_le = struct.unpack("<f", raw_bbox[8:12])[0]
    y2_le = struct.unpack("<f", raw_bbox[12:16])[0]

    print("BBox BE:", (x1_be, y1_be, x2_be, y2_be))
    print("BBox LE:", (x1_le, y1_le, x2_le, y2_le))

    # Advance reader position by 16 bytes
    r.pos += 16    
    
    ###########################################################
    
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


def parse_elements(r, element_fmt):
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

    # --- v6 BINARY -----------------------------------------------------------
    if element_fmt == "v6":
        while r.remaining() > 0:
            skip_v6_geometry(r)
            tag = chr(r.read_byte())

            if tag in ('L','l'):
                parse_line_v6(r); lines += 1; continue
            if tag in ('P','p'):
                parse_point_v6(r); points += 1; continue
            if tag in ('A','a'):
                parse_area_v6(r); areas += 1; continue

            tag_counts[tag] += 1
            unknown += 1

        return lines, points, areas, unknown, tag_counts

    # --- v5 UTF --------------------------------------------------------------
    if element_fmt == "v5":
        while r.remaining() > 0:
            tag = chr(r.read_byte())

            if tag in ('E','e'):
                break
            if tag in ('N','n'):
                parse_note_v5(r); continue
            if tag in ('L','l'):
                parse_line_v5(r); lines += 1; continue
            if tag in ('P','p'):
                parse_point_v5(r); points += 1; continue
            if tag in ('A','a'):
                parse_area_v5(r); areas += 1; continue

            tag_counts[tag] += 1
            unknown += 1

        return lines, points, areas, unknown, tag_counts

    # --- v4 UTF --------------------------------------------------------------
    if element_fmt == "v4":
        while r.remaining() > 0:
            tag = chr(r.read_byte())

            if tag in ('E','e'):
                break
            if tag in ('N','n'):
                parse_note_v4(r); continue
            if tag in ('L','l'):
                parse_line_v4(r); lines += 1; continue
            if tag in ('P','p'):
                parse_point_v4(r); points += 1; continue
            if tag in ('A','a'):
                parse_area_v4(r); areas += 1; continue

            tag_counts[tag] += 1
            unknown += 1

        return lines, points, areas, unknown, tag_counts

    # --- v3 LEGACY (if ever needed) -----------------------------------------
    if element_fmt == "v3":
        while r.remaining() > 0:
            tag = chr(r.read_byte())

            if tag in ('E','e'):
                break
            if tag in ('N','n'):
                parse_note_v3(r); continue
            if tag in ('L','l'):
                parse_line_v3(r); lines += 1; continue
            if tag in ('P','p'):
                parse_point_v3(r); points += 1; continue
            if tag in ('A','a'):
                parse_area_v3(r); areas += 1; continue

            tag_counts[tag] += 1
            unknown += 1

        return lines, points, areas, unknown, tag_counts

    # --- Unknown format ------------------------------------------------------
    raise ValueError(f"Unknown element_fmt {element_fmt}")


def parse_tdr_file(r):
    version = read_version(r) # not written yet

    header_fmt, element_fmt = dispatch_by_version(version)

    header = parse_header(r, header_fmt)

    lines, points, areas, unknown, tag_counts = parse_elements(r, element_fmt)

    return header, lines, points, areas, unknown, tag_counts

def check_tdr(path):
    global FILENUMBER, versions_dict
    path = Path(path)  # ensure it's a Path object
    FILENUMBER += 1
    print(f"File: {path.parent.parent.stem}/{path.parent.stem}/{path.name}")

    data = path.read_bytes()
    
    print(f"Size: {len(data)} bytes")
    

    # Load manifest
    dirpath = path.parent
    manifest_path = dirpath / "manifest"

    manifest = None
    if os.path.exists(manifest_path):
        try:
            manifest = load_manifest(manifest_path)
            # print("Manifest:")
            # print(f"  TD version:  {manifest['td_version']}")
            # print(f"  TDR version: {manifest['tdr_version']}")
            # print(f"  Survey name: {manifest['survey_name']}")
            # print(f"  Schema:      {manifest['schema_version']}")
            # print(f"  Date:        {manifest['date']}")
        except Exception as e:
            print(f"Manifest: ERROR reading manifest ({e})")
    else:
        print(f"Manifest: NOT FOUND ({manifest_path})")

    r = Reader(data)

    try:
        # Header
        magic = r.read_byte()
        if magic != ord('V'):
            print("ERROR: Not a TDR file (magic byte mismatch)")
            return

        version = r.read_int()
        print(f"Version: {version}")    
        versions_dict[version] += 1
        header_fmt, element_fmt  = dispatch_by_version(version)
        print(f"{header_fmt=}{element_fmt=}")

        # Compare with manifest
        if str(version)[:-2] != str(manifest["tdr_version"])[:-2]:
            print(f"ERROR: TDR version mismatch with manifest {version} != {manifest["tdr_version"]}")
        elif version != manifest["tdr_version"]:
            print(f"Warning: TDR patch version mismatch with manifest {version} != {manifest["tdr_version"]}")
        
        # Safe UTF reads
        scrap_indicator_code = r.read_byte()
        if scrap_indicator_code != 0x53:
            # the letter "S"
            print(f"Bad scrap indicator byte: 0x{scrap_indicator_code:02x}")
            
        scrap_fullname = r.read_utf("scrap_fullname")
 
        if manifest:
            # can also check that filename matches scrap name
            survey_name = manifest["survey_name"]
            path_name = path.stem
            if not scrap_fullname == path_name:
                print(f"Scrap fullname and filename mismatch {scrap_fullname=} {path_name=}")
            if scrap_fullname.startswith(survey_name):
                scrap_shortname = scrap_fullname.replace(survey_name,"")
                print(f"Scrap shortname: '{scrap_shortname}'")
            else:
                print("Warning: Scrap fullname mismatch with Survey Name in manifest")
                print(f"Scrap full name: {scrap_fullname}")
                scrap_shortname = "Z"
       
        # 602012/602011 use little-endian schema_flags
        # Read schema_flags in both byte orders
        raw_flags = r.data[r.pos:r.pos+4]
        schema_flags_be = struct.unpack(">I", raw_flags)[0]
        schema_flags_le = struct.unpack("<I", raw_flags)[0]
        r.pos += 4
        print(f"Schema/flags BE: {schema_flags_be}")
        print(f"Schema/flags LE: {schema_flags_le}")
        
        # After reading schema_flags, dump the next 64 bytes
        print("Header bytes after schema_flags:",
            r.data[r.pos:r.pos+64].hex())

        major = td_version_major(version)

     
        head = parse_header(r, header_fmt)                     
        print(f"{head["layer"]=}\n{head["wall"]=}\n{head["water"]=}")
        if "material" in head:
            print(f"{head["material"]=}")
        if "bbox" in head:
            print(f"{head["bbox"]=}")
        
        #print(f"{head["extra1"]=}\n{head["extra2"]=}\n{head["pad"]=}")
       

        

        lines, points, areas, unknown, tag_counts = parse_elements(r, element_fmt)
        print("Summary:")
        print(f"  Lines:   {lines}")
        print(f"  Points:  {points}")
        print(f"  Areas:   {areas}")
        print(f"  Unknown: {unknown}")
        
        print("Tag histogram:", tag_counts)
    except Exception as e:
        print(f"ERROR: {version} {e}")
        # raise


# ------------------------------------------------------------
# Entry point
# ------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: tdr_checker.py <file.tdr | directory>")
        sys.exit(1)

    target = Path(sys.argv[1])

    if target.is_dir():
        scan_directory(target)
    else:
        check_tdr(target)

print(f"{FILENUMBER} tdr files", file=sys.stderr)
for v in versions_dict:
    print(v, versions_dict[v], file=sys.stderr)
