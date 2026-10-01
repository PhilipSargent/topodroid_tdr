
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

