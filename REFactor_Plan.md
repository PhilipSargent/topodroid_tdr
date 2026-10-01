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
