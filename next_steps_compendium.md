### Scrap_Geometry_Packets.md

```md
# Scrap Geometry Packets (SGP) in TopoDroid TDR Files

This document describes the role and structure of Scrap Geometry Packets (SGP)
in TopoDroid `.tdr` files, and how they fit into the parsing and export
pipeline.

---

## 1. Purpose of SGP

Scrap Geometry Packets are TopoDroid’s way of storing **all rendered geometry**
for a single scrap in a compact, binary format. An SGP typically contains:

- walls and passage outlines
- areas (floor, water, mud, etc.)
- symbols (pits, arrows, flow, etc.)
- text labels (station numbers, notes)
- station markers
- cached render buffers

Older TDR versions (e.g. `400020`, `401092`) use SGPs instead of v5/v6 tagged
element streams.

---

## 2. SGP Placement in TDR Files

For versions like `400020` and `401092`:

1. A v4-style header is present:
   - schema flags
   - layer/wall/water tag lists
   - bounding box
2. After the header, the file consists of **one or more SGP blocks**:
   - each block corresponds to a scrap
   - each block has its own internal header and payload

The manifest and `survey.sql` provide the mapping from scrap shortnames (e.g.
`-1p`, `-1s`) to TDR files.

---

## 3. SGP Block Structure (High-Level)

Each SGP block has:

1. **Block header**
   - type (e.g. line, area, symbol)
   - group index (e.g. `wall`, `water`, `layer`)
   - packet version
   - record count or payload length (version-dependent)

2. **Payload**
   - one or more geometry records
   - each record encodes a polyline, Bézier spline, text label, symbol, etc.

Example (simplified):

```text
4C          # 'L' → line geometry packet
00          # type index
04          # group index
77 61 6c 6c # "wall"
00 00 00 00 # reserved
00 01       # packet version
00 00 00 02 # record count (example)

... payload of 2 geometry records ...
```

---

## 4. Geometry Record Types Inside SGP

Within the payload, records are encoded as binary sequences. Common types:

- **Polyline**
  - count + sequence of `(x, y)` float pairs
- **Cubic Bézier segment**
  - 4 control points (`p0`, `p1`, `p2`, `p3`)
- **Bézier spline**
  - multiple cubic segments chained together
- **Text label**
  - tag `'T'` (`0x54`)
  - `float32 x`, `float32 y`
  - `uint8 length`
  - UTF‑8 text
- **Symbol**
  - tag `'S'` (`0x53`)
  - position, rotation, symbol kind

Exact layouts vary by version and packet type, but the parser’s job is to
normalise them into a version‑neutral geometry model.

---

## 5. Parsing Strategy

The SGP parser should:

1. Read the v4 header to obtain:
   - tag lists (`layer`, `wall`, `water`)
   - schema flags
   - bounding box
2. Iterate over SGP blocks:
   - read block header
   - decode payload records according to packet type and version
3. Emit version‑neutral geometry elements:
   - `Polyline`
   - `CubicBezier`
   - `BezierSpline`
   - `TextLabel`
   - `Symbol`

These elements are then used by:

- `tdr_checker.py` for diagnostics
- `tdr_exporter.py` for SVG generation

---

## 6. Relationship to Other Versions

- v3: uses UTF/binary tagged elements, no SGP.
- v4: can use tagged elements or SGP, depending on version.
- v5/v6: use more modern tagged element streams, but the geometry concepts
  (polylines, Béziers, text, symbols) remain the same.

SGP is essentially a **binary cache of scrap geometry**, and the version‑neutral
API should treat it as just another source of geometry elements.

```

---

### Version_Map.md

```md
# Version Map for TopoDroid TDR Files

This document defines the mapping from TDR version numbers to header and
element formats, and explains how the parser should dispatch between them.

---

## 1. Goals

- Make version handling **explicit and declarative**.
- Avoid long `if/elif` ladders.
- Provide a single source of truth for:
  - header format
  - element format
  - special handling (e.g. SGP)

---

## 2. Version Map Table

```python
VERSION_MAP = {
    # TD6 hybrid: v6 header, v5+ elements
    602012: ("v6_cstring_header", "v5+"),
    602011: ("v6_length_header", "v5+"),

    # TD5 hybrid: v5 header, v6 binary-only elements
    501040: ("v5_length_header2", "v6_binary_only"),

    # TD4 with SGP: v4 header, scrap geometry packets
    401092: ("v4_header", "sgp"),
    400020: ("v4_header", "sgp"),

    # TD4 classic: v4 header, v4 tagged elements
    400001: ("v4_header", "v4"),

    # TD3: v3 header, binary elements
    301040: ("v3_header", "v3_binary"),

    # TD3: v3 header, UTF elements
    301004: ("v3_header", "v3_utf"),
}
```

The dispatcher becomes:

```python
def dispatch_by_version(version: int) -> tuple[str, str]:
    try:
        return VERSION_MAP[version]
    except KeyError:
        raise ValueError(f"Unsupported TD version {version}")
```

---

## 3. Header Formats

- **`v3_header`**
  - early TD3 format
  - basic tag lists, minimal metadata

- **`v4_header`**
  - schema flags
  - `layer`, `wall`, `water` tag lists
  - bounding box

- **`v5_length_header2`**
  - v5 header with length-based fields
  - used by hybrid v5/v6

- **`v6_cstring_header` / `v6_length_header`**
  - TD6 headers with either C‑string or length-prefixed fields
  - more metadata, extended schemas

All header parsers should return a unified `TdrHeader` object.

---

## 4. Element Formats

- **`v3_utf`**
  - tagged elements with UTF text
  - early notes and labels

- **`v3_binary`**
  - binary elements, minimal text

- **`v4`**
  - tagged elements:
    - `L`/`l` → line
    - `P`/`p` → point
    - `A`/`a` → area
    - `T`/`t` → text
    - `N`/`n` → note

- **`sgp`**
  - Scrap Geometry Packets:
    - binary blocks per scrap
    - internal record types for polylines, Béziers, text, symbols

- **`v6_binary_only`**
  - binary geometry only, no tagged text
  - used in hybrid v5/v6

- **`v5+`**
  - modern TD5/TD6 element streams
  - richer tags and attributes

---

## 5. Parser Responsibilities

The main parser should:

1. Read the version from the TDR file.
2. Use `dispatch_by_version(version)` to obtain:
   - `header_fmt`
   - `element_fmt`
3. Call:
   - `parse_header(r, header_fmt) -> TdrHeader`
   - `parse_elements(r, element_fmt, stats) -> list[GeometryElement]`

This keeps version handling centralised and makes it easy to add support for
new versions or special cases.

---

## 6. Extensibility

To add a new version:

1. Extend `VERSION_MAP` with the new version number.
2. Implement the corresponding header and element parsers.
3. Add tests for:
   - header parsing
   - element parsing
   - geometry normalisation

This approach keeps the codebase maintainable as more TDR variants are
encountered.

```

---

### SVG_Exporter_Design.md

```md
# SVG Exporter Design for TopoDroid TDR Files

This document outlines the design of the SVG exporter that will consume the
version‑neutral geometry model and produce SVG files for each scrap.

---

## 1. Goals

- Generate one SVG per scrap (`.tdr` file).
- Faithfully reproduce TopoDroid’s rendering:
  - walls and passage outlines
  - areas (floor, water, mud, etc.)
  - symbols
  - text labels
- Use metadata from:
  - `manifest`
  - `survey.sql`
- Keep the exporter **version‑agnostic** by relying on the unified geometry API.

---

## 2. Inputs

For each scrap:

- `TdrHeader`
  - version
  - schema flags
  - tag lists (`layer`, `wall`, `water`)
  - bounding box
- `Scrap` object
  - list of `GeometryElement` instances:
    - `Polyline`
    - `CubicBezier`
    - `BezierSpline`
    - `TextLabel`
    - `Symbol`
- Metadata:
  - scrap shortname (`-1p`, `-1s`, etc.)
  - survey name
  - station mapping (from `survey.sql`)

---

## 3. SVG Structure

A typical SVG output:

```xml
<svg xmlns="http://www.w3.org/2000/svg"
     width="W" height="H"
     viewBox="xmin ymin width height">
  <g id="walls">
    <!-- polylines and Béziers for walls -->
  </g>
  <g id="areas">
    <!-- filled polygons / paths -->
  </g>
  <g id="symbols">
    <!-- symbol paths -->
  </g>
  <g id="labels">
    <!-- text elements -->
  </g>
</svg>
```

Coordinate system:

- Use the scrap’s bounding box to define `viewBox`.
- Optionally apply scaling and translation to fit a desired output size.

---

## 4. Mapping Geometry to SVG

### 4.1 Polyline → `<path>` or `<polyline>`

```xml
<path d="M x0 y0 L x1 y1 L x2 y2 ..."
      stroke="color"
      stroke-width="w"
      fill="none" />
```

or:

```xml
<polyline points="x0,y0 x1,y1 x2,y2 ..."
          stroke="color"
          stroke-width="w"
          fill="none" />
```

### 4.2 Cubic Bézier → `<path>`

```xml
<path d="M x0 y0 C x1 y1 x2 y2 x3 y3"
      stroke="color"
      stroke-width="w"
      fill="none" />
```

### 4.3 Bézier Spline → `<path>`

Chain multiple `C` commands:

```xml
<path d="M p0.x p0.y
         C p1.x p1.y p2.x p2.y p3.x p3.y
         C p4.x p4.y p5.x p5.y p6.x p6.y
         ..."
      stroke="color"
      stroke-width="w"
      fill="none" />
```

### 4.4 TextLabel → `<text>`

```xml
<text x="x" y="y"
      font-size="fs"
      fill="color"
      text-anchor="middle">
  Station 4
</text>
```

### 4.5 Symbol → `<use>` or `<path>`

Symbols can be:

- predefined SVG paths (e.g. in `<defs>`)
- inline paths per symbol

Example:

```xml
<use href="#symbol-pit"
     x="x" y="y"
     transform="rotate(angle x y)" />
```

---

## 5. Style Mapping

Styles (color, width, dash, fill) are derived from:

- tag lists (`layer`, `wall`, `water`)
- schema flags
- symbol kinds

The exporter should maintain a style map:

```python
STYLE_MAP = {
    "wall": Style(stroke="#000", width=1.0),
    "water": Style(stroke="#00f", width=1.0),
    "mud": Style(stroke="#964B00", width=0.8),
    ...
}
```

Each `GeometryElement` carries a `style` or a tag that can be resolved into a
style.

---

## 6. Exporter API

Suggested interface:

```python
def export_scrap_to_svg(scrap: Scrap,
                        header: TdrHeader,
                        metadata: ScrapMetadata) -> str:
    """
    Return SVG as a string for the given scrap.
    """
```

Where `ScrapMetadata` includes:

- scrap shortname
- survey name
- station mapping
- optional rendering options

---

## 7. Incremental Implementation Plan

1. Implement minimal exporter:
   - walls as polylines
   - station numbers as text
   - simple bounding box viewBox
2. Add Bézier support:
   - render cubic segments and splines
3. Add areas:
   - fill polygons / paths
4. Add symbols:
   - define symbol shapes in `<defs>`
   - render with `<use>`
5. Refine styles:
   - map tags to colors, widths, fills
6. Integrate metadata:
   - titles, labels, survey info

This allows gradual evolution from a basic visualisation to a faithful
TopoDroid-style rendering.

```

---

## 1. Outline the module structure

Here’s a concrete module layout you can adopt:

```text
topodroid_tdr/
  tdr_reader.py      # low-level binary reader
  tdr_formats.py     # version map + header/element dispatch
  tdr_header.py      # header parsers, TdrHeader dataclass
  tdr_model.py       # geometry dataclasses (Polyline, Bezier, TextLabel, Symbol, Scrap)
  tdr_sgp.py         # Scrap Geometry Packet parser (sgp element_fmt)
  tdr_v3.py          # v3 element parsers
  tdr_v4.py          # v4 element parsers
  tdr_v5_v6.py       # v5+/v6 element parsers
  tdr_checker.py     # CLI diagnostics, stats, histograms
  tdr_exporter.py    # SVG exporter
  tests/             # unit tests
    test_header_v4.py
    test_sgp_parser.py
    test_geometry_model.py
    test_exporter_minimal.py
```

Key ideas:

- **`tdr_reader.py`**: one `Reader` class used everywhere.
- **`tdr_formats.py`**: `VERSION_MAP` and `dispatch_by_version`.
- **`tdr_sgp.py`**: all SGP-specific logic isolated.
- **`tdr_model.py`**: version-neutral geometry and header types.
- **`tdr_checker.py`**: no parsing logic, only uses the above.

---

## 2. Design the SGP parser (high-level)

In `tdr_sgp.py`:

```python
from .tdr_model import Scrap, Polyline, CubicBezier, BezierSpline, TextLabel, Symbol
from .tdr_reader import Reader

def parse_sgp_blocks(r: Reader, header: TdrHeader) -> Scrap:
    """
    Parse all Scrap Geometry Packets from the current position in the Reader
    and return a Scrap object containing version-neutral geometry elements.
    """
    elements: list[GeometryElement] = []

    while r.remaining() > 0:
        # 1. Read block header
        packet_type = chr(r.read_byte())   # e.g. 'L', 'A', 'S', etc.
        type_index = r.read_byte()
        group_index = r.read_byte()
        group_name = read_cstring(r)       # e.g. "wall", "water", "layer"
        reserved = r.read_uint32_be()
        packet_version = r.read_uint16_be()
        record_count = r.read_uint32_be()  # or payload length, depending on version

        # 2. Dispatch by packet_type
        if packet_type in ("L", "l"):
            elements.extend(parse_sgp_lines(r, record_count, group_name))
        elif packet_type in ("A", "a"):
            elements.extend(parse_sgp_areas(r, record_count, group_name))
        elif packet_type in ("S", "s"):
            elements.extend(parse_sgp_symbols(r, record_count, group_name))
        elif packet_type in ("T", "t"):
            elements.extend(parse_sgp_texts(r, record_count, group_name))
        else:
            # Unknown packet type: skip or log
            skip_sgp_payload(r, record_count)

    return Scrap(header=header, elements=elements)
```

Each `parse_sgp_*` function:

- reads the appropriate number of records
- decodes floats and tags
- constructs `Polyline`, `CubicBezier`, `BezierSpline`, `TextLabel`, `Symbol`

You can start with:

- `parse_sgp_lines()` → only polylines
- `parse_sgp_texts()` → text labels
- then extend to Béziers and symbols once you understand their binary layout.

---

## 3. First test suite (minimal but useful)

In `tests/test_sgp_parser.py`:

```python
import io
from topodroid_tdr.tdr_reader import Reader
from topodroid_tdr.tdr_model import TdrHeader
from topodroid_tdr.tdr_sgp import parse_sgp_blocks

def make_fake_sgp_line_packet() -> bytes:
    # Construct a minimal SGP block with one line polyline
    # This is synthetic and can be adjusted as you learn the real format.
    b = bytearray()
    b.extend(b"L")          # packet_type
    b.extend(b"\x00")       # type_index
    b.extend(b"\x04")       # group_index
    b.extend(b"wall\x00")   # group_name (cstring)
    b.extend((0).to_bytes(4, "big"))   # reserved
    b.extend((1).to_bytes(2, "big"))   # packet_version
    b.extend((1).to_bytes(4, "big"))   # record_count

    # Payload: one polyline with 2 points (x0,y0,x1,y1)
    # Here we just use known float encodings.
    import struct
    b.extend(struct.pack(">f", 0.0))
    b.extend(struct.pack(">f", 0.0))
    b.extend(struct.pack(">f", 10.0))
    b.extend(struct.pack(">f", 5.0))

    return bytes(b)

def test_sgp_parses_minimal_line():
    data = make_fake_sgp_line_packet()
    r = Reader(io.BytesIO(data))
    header = TdrHeader(
        version=400020,
        schema_flags=1,
        layer_tags=[],
        wall_tags=["wall"],
        water_tags=[],
        bbox=None,
    )

    scrap = parse_sgp_blocks(r, header)
    assert len(scrap.elements) == 1
    line = scrap.elements[0]
    assert line.points == [(0.0, 0.0), (10.0, 5.0)]
```

You can add similar tests for:

- text labels (`test_sgp_parses_text_label`)
- multiple packets (`test_sgp_multiple_blocks`)
- integration with `dispatch_by_version` (`test_version_map_sgp`)

This gives you a safety net while you refine the real SGP parsing logic from actual files.

If you’d like, next step we can sketch `tdr_reader.Reader` and the core geometry dataclasses in `tdr_model.py` so you’ve got a concrete starting point to wire all this together.