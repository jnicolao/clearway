# Clearway

**Multimodal trade-document clearance copilot.** Reads a shipment's document
bundle as images, extracts every field with a pixel-level citation, reconciles
fields across documents, and flags what will hold the shipment at customs.

> **Status: in development.** Nothing in this repo works yet. There are no
> benchmark numbers published below because none have been measured — see
> [Evaluation](#evaluation) for why that matters here.

---

## The problem

Cross-border shipments move on a bundle of documents: bill of lading,
commercial invoice, packing list, certificate of origin, customs declaration.
They arrive as scanned PDFs, phone photos, and stamped faxes — multi-language,
skewed, partly handwritten.

Clearance rarely stalls because one document is wrong. It stalls because the
documents **disagree with each other**: the invoice value doesn't match the
declaration, the HS code doesn't match the goods description, the consignee on
the B/L isn't the consignee on the cert. Every day held is demurrage.

Clearway reconciles the bundle and produces a triage packet: a risk score, the
specific discrepancies, and a cropped image of the evidence behind each claim.

## Approach

Two decisions separate this from a document-parsing wrapper.

**Documents are read as images, not as OCR text.** Retrieval uses
late-interaction multi-vector matching over page images — via a hosted
embedding API — so layout, stamps, and table structure survive into the
model's context instead of being flattened into a text blob first.

**Every assertion is grounded in a pixel region.** Each extracted field carries
a page and bounding box, and a second model re-verifies the claim against only
that crop. Ungrounded claims become countable rather than a matter of opinion —
which is what makes the hallucination rate in the eval table a measurement and
not a vibe.

## Architecture

```
intake ──▶ classify ──▶ extract ──▶ reconcile ──▶ comply ──▶ forecast ──▶ critic
             │             │            │            │           │          │
        doc type &    VLM + bbox   cross-doc     sanctions,   dwell-time  re-verify
        quality gate   citations   field diff    tariff code   risk       vs. crop
                                                                             │
                                              low confidence ──▶ human review
```

Human review is a graph interrupt, not a separate app. Corrections flow back
into the eval set, so the review queue is also the training signal.

## Evaluation

The eval harness is the point of this project, not an afterthought to it.

| Axis | Metric | Status |
|---|---|---|
| Page retrieval vs. OCR-chunk baseline | nDCG@5, Recall@10, MRR | not yet measured |
| Field extraction | F1 across document types | not yet measured |
| Groundedness | ungrounded-claim rate | not yet measured |
| Judge calibration | Cohen's κ vs. human labels | not yet measured |
| Robustness | F1 degradation across 9 perturbations | not yet measured |
| Cost | $ per document, p95 latency | not yet measured |

Numbers land here when they are measured on a held-out set, and not before.

## Stack

**No GPU anywhere.** Inference is hosted, so a clone runs on a laptop with two
API keys — which is also what production looks like. Self-hosting a 7B model
was never the interesting part of this project.

**Models** — `jina-embeddings-v4` in multi-vector mode for page embeddings,
which gives late interaction without self-hosting ColPali. `claude-haiku-4-5`
for bulk extraction, escalating to `claude-opus-5` where confidence is low.
Every call returns token usage, so cost per document is a measurement and not
an estimate.

**Infrastructure** — Python · LangGraph · Qdrant (multi-vector) · Postgres +
pgvector · Langfuse · Prefect · Docker Compose. All CPU-only.

**Live APIs** — OpenSanctions (denied-party screening), USITC HTS (tariff
validation), UN Comtrade (trade flows), AISStream (vessel AIS).

## Roadmap

- [x] Port-call collector (AIS) — running, feeds dwell-time forecasting
- [x] Model client layer — tiered VLM calls with usage accounting
- [ ] Ingestion pipeline and document corpus
- [ ] Visual retrieval index, end to end
- [ ] Eval harness v1 and the retrieval baseline comparison
- [ ] Grounded extraction with bounding-box citations
- [ ] LangGraph orchestration and the critic pass
- [ ] Compliance checks against live APIs
- [ ] Human-in-the-loop review and tracing
- [ ] Dwell-time forecasting and the robustness suite

## License

MIT — see [LICENSE](LICENSE).
