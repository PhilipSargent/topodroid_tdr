Absolutely, Philip — and since you asked for **two `.md` files**, I’ll produce both of them cleanly, ready to drop straight into your repo.

No file‑creation tools are used; I’m simply giving you the full Markdown content so you can paste them into your project as:

- `REFactor_Plan.md`
- `Geometry_Model.md`

Both are structured, version‑neutral, and aligned with the future SVG exporter.

---

# 📄 **REFactor_Plan.md**

```md
# TopoDroid TDR Parser — High‑Level Refactor Plan

This document summarises the architectural direction for the next phase of the
TopoDroid TDR parsing project. The goal is to evolve from exploratory parsing
(`tdr_checker.py`) into a stable, reusable parsing core that will later support
a full SVG exporter.

---

## 1. Project Goal (Reformulated)

The TDR parser must:

1. **Understand** the structure of `.tdr` files across multiple historical
   TopoDroid versions (v3, v4, hybrid v4/SGP, v5, v6).
2. **Demonstrate** that understanding via diagnostics, sanity checks, and
   structural validation.
3. **Normalise** geometry into a version‑neutral in‑memory model.
4. **Export** each scrap to SVG (later), enriched with metadata from:
   - `manifest`
   - `survey.sql`

`tdr_checker.py` is the *format‑exploration tool*.
`tdr_exporter.py` will be the *production SVG generator*.

---

## 2. High‑Level Refactor Direction

### 2.1 Separate concerns into modules

**`tdr_reader.py`**
- Low‑level binary I/O
- `Reader` class, endian helpers, `read_uint16_be`, `read_bytes`, etc.

**`tdr_formats.py`**
- Version dispatch table
- Header parsers
- Element parsers (v3, v4, SGP, v5, v6)

**`tdr_model.py`**
- Version‑neutral geometry dataclasses:
  - `Polyline`
  - `CubicBezier`
  - `BezierSpline`
  - `TextLabel`
  - `Symbol`
  - `Scrap`
- Unified `TdrHeader`

**`tdr_checker.py`**
- CLI + diagnostics
- Stats, histograms, corruption reports
- No parsing logic

**`tdr_exporter.py`**
- SVG writer (later)
- Consumes `Scrap` + metadata

---

### 2.2 Replace version ladder with declarative table

```python
VERSION_MAP = {
    602012: ("v6_cstring_header", "v5+"),
    602011: ("v6_length_header", "v5+"),
    501040: ("v5_length_header2", "v6_binary_only"),
    400001: ("v4_header", "v4"),
    400020: ("v4_header", "sgp"),
    401092: ("v4_header", "sgp"),
    301040: ("v3_header", "v3_binary"),
    301004: ("v3_header", "v3_utf"),
}
```

This makes version support explicit and easy to extend.

---

### 2.3 Unify header parsing

All header parsers return:

```python
@dataclass
class TdrHeader:
    version: int
    schema_flags: int
    layer_tags: list[str]
    wall_tags: list[str]
    water_tags: list[str]
    bbox: tuple[float, float, float, float] | None
```

This removes version‑specific branching in the rest of the code.

---

### 2.4 Introduce a version‑neutral geometry API

All element parsers emit instances of:

- `Polyline`
- `CubicBezier`
- `BezierSpline`
- `TextLabel`
- `Symbol`

This allows the SVG exporter to be completely version‑agnostic.

---

### 2.5 Separate parsing from printing

Parsers **return data**, not print it.

`tdr_checker.py` handles all human‑facing output.

This makes the parsing core reusable.

---

### 2.6 Add small test fixtures

Create `tests/` with synthetic `.tdr` blobs for each version.

Tests should verify:

- header correctness
- element counts
- SGP text extraction
- Bézier decoding

This stabilises the refactor.

---

## 3. Concrete Next Steps

1. Extract `Reader` into `tdr_reader.py`.
2. Replace version ladder with `VERSION_MAP`.
3. Add `"sgp"` element format for 400020/401092.
4. Implement `TdrHeader` and geometry dataclasses in `tdr_model.py`.
5. Refactor `parse_header()` and `parse_elements()` to return structured objects.
6. Implement `parse_elements_sgp()` to decode Scrap Geometry Packets.
7. Begin a minimal `tdr_exporter.py` that draws:
   - walls (polylines)
   - station numbers (text)
   - bounding box

This proves the end‑to‑end pipeline.

---

## 4. Long‑Term Goal

A complete, version‑neutral SVG exporter that faithfully reproduces TopoDroid’s
scrap rendering, including Bézier curves, text labels, symbols, and styles.

```

---

# 📄 **Geometry_Model.md**

```md
# Geometry Model for Version‑Neutral TDR Parsing

This document summarises the geometry types used by TopoDroid internally and
defines the version‑neutral geometry API required for correct parsing and SVG
export.

---

## 1. What TopoDroid Actually Draws

TopoDroid uses **two fundamental geometry primitives**:

### 1.1 Straight Line Segments
Used for:
- walls
- passage outlines
- splays
- survey legs
- symbol stems
- area boundaries

### 1.2 Cubic Bézier Curves
Used for:
- smoothed wall outlines
- smoothed passage outlines
- scrap boundaries
- sketch strokes
- arrows and flow lines
- symbol shapes

Relevant TD source classes include:
- `Bezier.java`
- `BezierSpline.java`
- `Spline.java`
- `SketchPath.java`
- `SketchLine.java`
- `SketchArea.java`
- `SketchSymbol.java`

These implement:
- cubic Bézier segments
- multi‑segment Bézier splines
- Catmull–Rom → Bézier smoothing
- path flattening
- geometry packet serialization

---

## 2. Scrap Geometry Packets (SGP)

Older TDR versions (400020, 401092, 501040) store **all geometry** inside
Scrap Geometry Packets:

- polylines
- cubic Bézier segments
- Bézier splines
- text labels
- symbols
- station numbers
- cached render buffers

SGPs contain binary records, not v4/v5/v6 tagged elements.

Text labels appear as:

```
54                # 'T'
float32 x
float32 y
uint8 length
<UTF‑8 text>
```

---

## 3. Required Geometry API

To faithfully reproduce TD’s rendering, the parser must support:

### 3.1 Polyline

```python
@dataclass
class Polyline:
    points: list[Point]
    style: Style
```

### 3.2 Cubic Bézier Segment

```python
@dataclass
class CubicBezier:
    p0: Point
    p1: Point
    p2: Point
    p3: Point
    style: Style
```

### 3.3 Bézier Spline

```python
@dataclass
class BezierSpline:
    segments: list[CubicBezier]
    style: Style
```

### 3.4 Text Label

```python
@dataclass
class TextLabel:
    x: float
    y: float
    text: str
    style: Style
```

### 3.5 Symbol

```python
@dataclass
class Symbol:
    x: float
    y: float
    kind: str
    rotation: float
    style: Style
```

### 3.6 Scrap Container

```python
@dataclass
class Scrap:
    header: TdrHeader
    elements: list[GeometryElement]
```

---

## 4. Why SVG Export Requires Bézier Support

SVG supports cubic Bézier curves natively:

```
M x0 y0
C x1 y1, x2 y2, x3 y3
```

Flattening Béziers into polylines would:
- lose smoothness
- distort passage shapes
- break symbol geometry
- degrade sketch strokes

Therefore, Bézier support is mandatory.

---

## 5. Summary

TopoDroid uses a mixture of:
- polylines
- cubic Bézier curves
- Bézier splines
- text labels
- symbols

A version‑neutral geometry API must support all of these to allow accurate
parsing and faithful SVG export.

```

---

If you want, I can also produce:

- `Scrap_Geometry_Packets.md`  
- `Version_Map.md`  
- `SVG_Exporter_Design.md`

or start rewriting one of your existing modules in the new structure.