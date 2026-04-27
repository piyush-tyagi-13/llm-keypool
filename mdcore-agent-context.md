# mdcore - Agent Context Document

**What it is:** CLI tool for personal markdown knowledge base management. Local, LLM-agnostic. Reads and writes a vault of markdown files intelligently.

**Full name:** Markdown CORE AI - Classification, Organisation, Retrieval & Entry
**PyPI:** `markdowncore-ai` | **CLI command:** `mdcore` | **Version:** 1.0.0
**GitHub:** https://github.com/piyush-tyagi-13/markdown-core-ai
**Local repo:** `/Users/azzbeeter/Documents/GitHub/context-portability-tool`
**Config:** `~/.mdcore/config.yaml`
**Live config:** Gemini backend (`gemini-2.5-flash-lite`), Gemini embeddings (`models/gemini-embedding-001`)

---

## Two Flows

### Flow A - Retrieval (`mdcore search <topic>`)
1. Keyword pre-filter (BM25)
2. Vector search (ChromaDB)
3. Chunk stitching + context assembly
4. LLM synthesis - reformats excerpts into a cited briefing
5. Writes output to `<vault>/mdcore-output/<date>-<slug>.md`

`--raw` skips synthesis entirely (fully LLM-free). `synthesise_model` config key controls which model synthesises.

### Flow B - Ingestion (`mdcore ingest [--file doc.md]`)
1. Embed incoming doc + vector search vault for candidates
2. **Classification** - UPDATE existing file or NEW file
   - Auto-UPDATE: similarity > 0.82 AND doc is not self-contained
   - Auto-NEW: similarity < 0.65
   - LLM `classify()` call only in ambiguous 0.65-0.82 zone
   - `_is_self_contained()`: 2+ H2 headings + table or 3+ list items = bypass auto-UPDATE
3. **Folder routing** (NEW only): semantic pre-filter from top-k matches + LLM `route_folder()` picks folder
4. **Conflict detection**: similarity 0.88-0.97 flags conflict
5. **Proposal**: LLM `propose()` always generates human-readable proposal
6. User approves - then writes file + triggers targeted reindex

---

## Commands

```bash
mdcore init                    # interactive setup wizard -> writes ~/.mdcore/config.yaml
mdcore index                   # scan vault, show diff, confirm, index delta
mdcore index --force           # wipe manifest + chroma_db + embed_cache and reindex from scratch
mdcore search <topic>          # Flow A - synthesised briefing
mdcore search <topic> --raw    # Flow A - raw excerpts, no LLM
mdcore search <topic> --verbose
mdcore ingest                  # Flow B - paste document
mdcore ingest --file doc.md    # Flow B - ingest from file
mdcore map                     # generate <vault>/.mdcore-meta.yaml folder map
mdcore map --repair            # remove stale folder entries from map
mdcore status                  # index health + drift warnings
mdcore eval [topic]            # quality evaluation checklist
mdcore config                  # open config in editor
mdcore config --validate
```

---

## Package Structure

```
mdcore/
+-- cli/commands.py              # Typer commands, Rich UI
+-- core/
|   +-- indexer/                 # VaultScanner, ManifestManager, TextSplitter,
|   |                            # EmbeddingEngine, DocumentLoader, IndexWriter
|   +-- retriever/               # KeywordPreFilter, VectorSearcher, ChunkStitcher,
|   |                            # ContextAssembler, ContextFormatter, SourceRanker
|   +-- ingester/                # ClassificationEngine, ConflictDetector, FolderRouter,
|   |                            # ProposalGenerator, SummaryEmbedder, SummaryReceiver
|   +-- writer/                  # BackupManager, FrontmatterInjector, FileWriter, IndexTrigger
|   +-- vault_map.py             # manages <vault>/.mdcore-meta.yaml
+-- llm/llm_layer.py             # LLMLayer: classify(), propose(), synthesise(), route_folder()
+-- store/vector_store.py        # ChromaDB wrapper
+-- config/models.py             # Pydantic models - MdCoreConfig, LLMConfig, etc.
+-- config/loader.py             # YAML loader, default path ~/.mdcore/config.yaml
+-- utils/logging.py             # get_logger(), rotating file handler
```

---

## LLM Layer

File: `mdcore/llm/llm_layer.py`

- **`classify(summary, candidates)`** - UPDATE vs NEW decision
- **`propose(classification, existing_content, incoming_summary)`** - human-readable proposal
- **`synthesise(query, raw_context)`** - Flow A briefing
- **`route_folder(document, folders, descriptions)`** - picks target folder
- **`_invoke(prompt)`** - internal, handles primary + fallback LLM, logs tokens
- **`_log_tokens(label, response)`** - normalizes token usage across all backends
- **`_extract_token_usage(response_metadata)`** - handles Gemini/OpenAI/Anthropic/Ollama formats

LangSmith: set `langsmith_api_key` + `langsmith_project` in config. Wired via env vars in `LLMLayer.__init__()`.

Supported backends: `ollama`, `openai`, `anthropic`, `gemini`, `huggingface`

---

## Key Config Fields

```yaml
llm:
  backend: gemini
  model: gemini-2.5-flash-lite
  synthesise_model: gemini-2.5-flash-lite
  api_key: <key>
  fallback_backend: null
  fallback_model: null
  langsmith_api_key: null
  langsmith_project: mdcore

embeddings:
  backend: gemini
  api_model: models/gemini-embedding-001
  api_key: <key>

ingester:
  similarity_threshold_high: 0.82
  similarity_threshold_low: 0.65
  conflict_similarity_min: 0.88
  conflict_similarity_max: 0.97

retriever:
  top_k: 15
  similarity_threshold: 0.65
  keyword_prefilter: true

indexer:
  chunk_size: 512
  chunk_overlap: 64
  heading_aware_splitting: true
```

---

## Data Directories

| Path | Purpose |
|---|---|
| `~/.mdcore/config.yaml` | main config |
| `~/.mdcore/chroma_db` | vector store |
| `~/.mdcore/manifest.json` | index manifest |
| `~/.mdcore/embed_cache` | embedding cache (pkl) |
| `~/.mdcore/backups` | file backups before write |
| `~/.mdcore/logs` | rotating logs (INFO default) |
| `<vault>/.mdcore-meta.yaml` | optional folder map (travels with vault) |
| `<vault>/mdcore-output/` | Flow A output files |

---

## Known Issues / History

- **Embedding dimension mismatch**: stale `embed_cache.pkl` from old model causes ChromaDB errors. Fix: `mdcore index --force`
- **Auto-UPDATE on self-contained docs**: `_is_self_contained()` heuristic bypasses the high-threshold shortcut for structured docs
- **False conflict warnings**: thresholds raised to 0.88-0.97 after 0.81-0.83 range caused too many false positives
- **Wrong folder routing from token overlap**: replaced naive routing with two-stage semantic pre-filter + LLM
- **`langchain-google-genai` missing**: was optional `[gemini]` extra, moved to core deps in 1.3.3

---

## Install / Upgrade

```bash
uv tool install markdowncore-ai               # install
uv tool install markdowncore-ai --force --refresh   # upgrade
```
