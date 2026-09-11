# Corpus generator — scope

## Why this exists

Cross-document reconciliation is Clearway's core feature and **cannot be
evaluated on a found corpus**. Measuring whether the system catches an
invoice value disagreeing with a customs declaration requires every
discrepancy in every bundle to be labelled. On real documents that is
thousands of hours of annotation. Inject the discrepancies yourself and the
labels are free and exact.

The generator is not a substitute for real data. Retrieval is still measured
on ViDoRe and extraction on CORD. It exists because it produces the one thing
no public dataset has: **bundles of mutually-referring documents with known
inconsistencies**.

## What it emits

One bundle is one shipment. Per bundle:

```
bundles/<seed>-<n>/
├── shipment.json        canonical facts — the truth
├── discrepancies.json   what was injected, where, and of what type
├── invoice.png          rendered page image
├── invoice.json         every field: value + bounding box
├── packing_list.png
├── packing_list.json
├── bill_of_lading.png
└── bill_of_lading.json
```

Field annotations carry a bounding box because grounded extraction with pixel
citations is the project's thesis. A generator that emits boxes gives
extraction eval **bbox IoU for free** — a metric almost nothing in this space
reports.

## Rendering: draw directly, don't recover coordinates

Documents are drawn with Pillow onto a raster canvas, field by field.

The alternative — author HTML, render through a headless browser, recover
positions with `getBoundingClientRect()` — produces prettier documents and
drags in a browser dependency, a PDF step, and a coordinate-recovery step
that can silently drift.

Drawing directly means **the bounding box is the rectangle we drew into**.
No inference, no drift, exact ground truth. The cost is that templates are
more work to author. For three document types that trade is clearly worth it.
Revisit only if template variety becomes the bottleneck.

## Seeding from real public data

Nothing here is invented where a real value exists:

| Field | Source |
|---|---|
| HS codes, goods descriptions | USITC HTS bulk export (free, no auth) |
| Vessel names, MMSI, ports, dates | this repo's own AIS collector |
| Commodity flows, values, trade lanes | UN Comtrade |
| Sanctioned party names | OpenSanctions |

The AIS collector has no data until a key is in place, so the generator ships
with a small checked-in seed of real vessels and ports and prefers the live
database when it has rows. That keeps the generator independent of collector
uptime rather than blocked on it.

Ordinary shipper and consignee names are synthetic. **Real sanctioned names
appear only in bundles deliberately marked for the compliance eval**,
governed by a `sanctioned_party_rate` parameter — that is how detection
recall becomes measurable.

## Discrepancy taxonomy

This is the reconciliation label set. Each injection records its type, the
documents involved, and the fields involved.

| Type | Mechanism |
|---|---|
| `value_mismatch` | invoice total ≠ declared customs value |
| `quantity_mismatch` | packing list quantity ≠ invoice quantity |
| `party_mismatch` | consignee differs between B/L and invoice |
| `hs_code_mismatch` | HS code inconsistent with the goods description |
| `weight_mismatch` | B/L gross weight ≠ packing list total |
| `date_inconsistency` | B/L date precedes the invoice date |
| `currency_confusion` | declaration repeats the invoice figure in another currency |
| `missing_document` | a document required for that trade lane is absent |

A bundle may carry zero discrepancies. **Clean bundles are not filler** —
without them the false-positive rate is unmeasurable, and a reconciler that
flags everything would score perfectly.

## Degradation

The degradation pipeline is also the robustness suite. One piece of code,
two deliverables.

Rotation/skew · gaussian blur · JPEG crush · brightness and contrast ·
scanner speckle · perspective warp · partial crop · bilevel "fax" ·
stamp and signature overlay.

Each is parameterised by severity so the eval reports a degradation curve per
axis rather than one blended robustness number.

**The subtle part: boxes must follow the pixels.** Rotation and perspective
turn an axis-aligned box into a quadrilateral. Every degradation therefore
records its transform matrix, and annotations are mapped through the
composed transform rather than re-estimated. Getting this wrong produces a
corpus whose labels drift from its images — which would poison every
downstream number while looking fine.

## Determinism

Same seed, identical corpus — bytes included. An eval set that changes
underneath you makes every comparison between runs meaningless. All
randomness flows from one seeded generator passed explicitly; no module-level
`random` calls.

## Scope

**In**
- Three document types: commercial invoice, packing list, bill of lading
- Bundle ground truth, per-field values and bounding boxes
- The eight discrepancy types above, plus clean bundles
- Degradation with transform tracking
- `generate --seed N --count M --out DIR`

**Out, deliberately, until the above is measured**
- Certificate of origin, customs declaration (SAD)
- Handwriting synthesis
- Languages other than English
- Letterhead and logo variety beyond a few templates
- PDF output — Clearway reads page images, so a PDF step earns nothing

## Done means

1. **Boxes are correct.** For every field, cropping the annotated box and
   re-rendering that field alone produces a matching region. Automated, not
   eyeballed.
2. **Injections are honest.** Every discrepancy in `discrepancies.json`
   is present in the documents it names, and no unlisted inconsistency exists
   between bundle documents.
3. **Transforms compose.** A known corner survives a degradation chain and
   lands within tolerance of its mapped position.
4. **Determinism holds.** Two runs at one seed produce byte-identical output.
5. **Clean bundles are clean.** Bundles generated with zero injections
   contain no cross-document inconsistency.

## Effort

One to two weeks of real work, not a weekend. The Pillow templates are the
bulk of it; transform tracking is the part most likely to be subtly wrong.
Build it in that order: one document type end to end with box verification,
then the other two, then discrepancies, then degradation.
