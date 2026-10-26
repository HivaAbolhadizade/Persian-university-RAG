# Data provenance, safety, and publishing guidance

This **complete-results edition** retains the project's historical notebook outputs, extracted text, retrieval artifacts, evaluation reports and code. It is an **academic NLP course prototype**, not an official university service.

## Published historical artifacts

- Notebooks 01, 02, 03 include original output cells, figures and execution counts from the course-project run.
- `data/processed/`: extracted Persian policy text, metadata, document/page/chunk Parquet files, quality summaries and document catalogs.
- `data/retrieval/`: historical FAISS, BM25 and Chroma retrieval assets, embeddings, benchmark outputs and evaluation figures.
- `data/generation/`: selected generation experiment results/reports, excluding response caches.
- `reports/`: selected figures and curated written summaries. Raw provider-result dumps were not bundled.

## Exclusions

- **Original university regulations PDFs** in `data/raw/`. Their reuse terms are not independently verified.
- `.env`, API secrets, local provider settings, `logs/`, `data/generation/cache/`, raw full answer logs, local virtual environments and node_modules.
- The course report PDF and official university logo.

## Redistribution rights and privacy

**Crucial:** The included `data/processed/` files reproduce **extracted text from the source policy documents**. Public availability of source PDFs does **not** automatically grant permission to republish their full text, even when transformed to Parquet/JSON. **Before pushing publicly, check the source documents' license or university policy**, attribution, and whether the data includes personal information, names, signatures, or restricted content. If you cannot verify permission, remove `data/processed/`, `data/retrieval/` and related files containing source passages before pushing; notebook figures/aggregate summaries are safer to publish. University names reflect the data's original context, not endorsement.

Some archived output and metadata include the original workstation's absolute paths and file titles. No API key has intentionally been bundled; perform your own final secret scan before publishing.

## Serialized artifact security

The repository includes historical BM25 pickle/joblib files. **Never load `.pkl` or `.joblib` from untrusted repositories**: deserialization can execute arbitrary Python code. These artifacts are from the user's supplied archive and are provided for historical reproducibility. Chroma/FAISS files are version-sensitive and should be rebuilt when dependencies or corpus ordering change.

## API and evaluation caveats

- This is a local experimental prototype; avoid exposing it directly to the Internet without security hardening.
- Automated heuristic answer accuracy and citation validity are not expert-verified correctness.
- Provider availability differed across previous runs, making cross-mode accuracy comparisons imperfect.
- Local runs may use cloud providers with billing, rate limits, and data-handling constraints.
- If an API key is ever leaked publicly, **revoke and rotate it immediately**.

## Licensing

No default license is inserted. The project owner must decide the license for their own code separately from any third-party source content and pretrained-model licensing.
