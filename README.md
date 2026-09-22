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

**Fully open source, no paid APIs, no GPU required.** Every model runs
locally and every weight is Apache-2.0. A clone needs Ollama and a laptop.

**Models** — `ColQwen2` (Apache-2.0) for multi-vector page retrieval, giving
late interaction locally. ColPali is deliberately *not* used: its PaliGemma
backbone ships under the Gemma licence. `Qwen2.5-VL` via Ollama for
extraction, small tier by default and the larger one where confidence is low.

**Infrastructure** — Python · LangGraph · Qdrant (multi-vector) · Postgres +
pgvector · Langfuse · Prefect · Docker Compose. Apache-2.0 or MIT throughout.

**Live APIs** — all free, no key or no card: OpenSanctions (denied-party
screening), USITC HTS (tariff validation), UN Comtrade (trade flows),
AISStream (vessel AIS).

**Memory note.** ColQwen2-2B and Qwen2.5-VL-7B do not co-reside comfortably
in 16GB, so indexing and extraction run as sequential batch phases rather
than one live pipeline. That is a real constraint on the design, not a
tuning detail.

## Evaluation corpus

No free, openly-licensed corpus of real scanned trade documents with
extraction ground truth exists — those documents are commercially sensitive.
So the corpus is assembled in three layers, and results are always reported
against the real ones alongside the generated ones:

- **Retrieval** on **ViDoRe**, so the headline number sits next to published
  ColPali results rather than a private baseline of our own choosing.
- **Extraction** on **CORD** (CC BY 4.0) and **DocLayNet**
  (CDLA-Permissive-1.0). DocILE is excluded: research-access only, which a
  fully-open project cannot redistribute.
- **Reconciliation** on a generated bundle corpus, seeded from real public
  data — HS codes from USITC HTS, vessels and ports from this repo's own AIS
  collector, trade flows from UN Comtrade, entity names from OpenSanctions.
  Cross-document reconciliation *cannot* be evaluated on a found corpus:
  measuring whether an invoice disagrees with a declaration needs every
  discrepancy labelled, which is only free if you inject them yourself.

Generated corpora inflate scores when the generator and the extractor share
assumptions. The mitigation is structural — a synthetic number is never
published without the ViDoRe and CORD numbers beside it.

## Running the collector

The AIS collector must run continuously for six-plus weeks before the
dwell-time work in the roadmap can start, so it runs as a launchd agent
rather than a terminal process:

```bash
./scripts/install-collector-agent.sh          # install and start
./scripts/install-collector-agent.sh --uninstall
tail -f ~/Library/Logs/clearway-ais.log
```

**This repo lives at `~/Developer/clearway`, not under `~/Documents`.** That
is deliberate: `~/Documents` is TCC-protected, and a launchd agent is denied
access to it even though Terminal is allowed, so the agent dies with
"Operation not permitted" before it runs. A symlink at
`~/Documents/github/clearway` keeps the old path working for humans; the
scripts resolve with `pwd -P` so the agent always gets the real path.

Only one collector may write at a time — it takes an exclusive lock beside
the database. The schema has no uniqueness constraint, so two writers would
silently duplicate rows and skew every dwell-time figure derived from them.

## Roadmap

- [x] Port-call collector (AIS) — running, feeds dwell-time forecasting
- [x] Model client layer — local Ollama tiers with throughput accounting
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
