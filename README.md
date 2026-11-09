# Clearway

**A synthetic trade-document corpus with exact ground truth.** Generates
bundles of commercial invoices, packing lists and bills of lading that all
describe one shipment, with a measured bounding box for every field, labelled
disagreements between the documents, and realistic scan damage whose
annotations follow the pixels.

> **Status: complete, archived 9 November 2026.** This started as the
> evaluation foundation for a document-reconciliation copilot. The corpus
> generator and the vessel data collection were finished; the copilot that
> would have been evaluated against them was not built. Everything in the repo
> works and is tested — 187 tests, passing in CI.

## Why it exists

Customs clearance stalls when a shipment's documents disagree with each other:
the packing list quantity doesn't match the invoice, or the consignee on the
bill of lading isn't the invoice buyer. Building something that catches this
needs an evaluation set where every disagreement is labelled.

No such set is public. Real bills of lading and customs declarations are
commercially sensitive, so annotated scans aren't published. Even if they
were, cross-document reconciliation couldn't be scored on found documents
without hand-labelling every discrepancy across every bundle. Injecting the
discrepancies yourself is the only way to get labels that are both exact and
free.

## What a bundle contains

```
<seed>-<n>/
├── shipment.json              the truth, never modified
├── discrepancies.json         what was injected, where, and of what type
├── invoice.png / .json        page image + every field's value, box and quad
├── packing_list.png / .json
└── bill_of_lading.png / .json
```

The three documents carry deliberately different views of one shipment.
Prices appear only on the invoice, and gross weight and a notify party only
on the bill of lading, so a reconciler can't simply diff every field.

## Why the labels can be trusted

**Boxes are measured, not inferred.** Each page is drawn field by field with
Pillow, and a field's box is the rectangle its text was drawn into. A test
renders every page again without each field, diffs the two images, and
asserts the changed pixels fall inside that field's box.

**Discrepancies never touch the truth.** They are applied as render-time
overrides, so `shipment.json` stays the canonical record. A separate test
reads the rendered pages the way a reconciler would, re-derives every
disagreement independently, and asserts the result matches the recorded labels
exactly — no unlabelled defects. Seven types are implemented: quantity, party,
weight, date, value, HS code and missing document. An eighth, defined against
a customs declaration, was scoped and deliberately left out rather than faked
against the documents that exist.

**Annotations follow the pixels through damage.** There are nine degradation
axes, each with a severity in [0, 1]. Rotation, perspective and crop return a
homography, and every box is mapped through the composed transform; mapped
boxes measured within 1px of the actual ink. Blur, JPEG, exposure, speckle,
bilevel and stamps change pixels without moving them. Rotated boxes are kept
as quadrilaterals, since a rotated box isn't a box.

**Seeded from real public data.** Line items come from 252 USITC HTS tariff
lines, vessel names from the collector below, and container numbers carry
valid ISO 6346 check digits. The same seed produces byte-identical output.

More detail on each decision is in [docs/corpus-generator.md](docs/corpus-generator.md).

## Usage

```bash
uv sync
uv run python -m clearway.corpus.generate --seed 7 --count 100 --out bundles/
uv run python -m clearway.corpus.generate --seed 7 --count 100 --degrade 3 --severity 0.6 --out scanned/
uv run pytest
```

`--discrepancy-rate` (default 0.6) sets the share of bundles that carry
defects. The rest are clean on purpose: without clean bundles a reconciler's
false-positive rate can't be measured.

## AIS collector

`clearway.ais` recorded vessel position reports from AISStream around
Mombasa, Dar es Salaam and Durban from 21 September to 9 November 2026 —
75,545 reports from 367 vessels — running as a launchd agent behind a
single-writer lock.

One finding worth keeping: **every report came from Durban.** Seven weeks of
continuous collection produced nothing at Mombasa or Dar es Salaam, though
the bounding boxes were checked against the harbour coordinates. That points
to a gap in terrestrial AIS receiver coverage on that stretch of coast rather
than a configuration error. The collected data isn't published here.

## Not pursued

The copilot this corpus was built to evaluate was planned but not built:
visual page retrieval with ColQwen2, grounded field extraction, orchestration
with a critic pass, compliance checks against OpenSanctions and USITC HTS,
human review, and a dwell-time forecast from the AIS data. `clearway.models`
holds thin clients for local Ollama and ColQwen2, tested against injected
transports but never run against a model. The plan for each stage is in the
closed issues.

## License

MIT — see [LICENSE](LICENSE).
