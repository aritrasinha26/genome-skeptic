# Provenance verification

Computed 2026-09-21 during construction of this audit package.

Hash method: SHA256 of file bytes. Where Windows checkout uses CRLF, **LF-normalized** SHA256 is also reported (`\r\n` → `\n`).

**MATCH** below means the expected identifier equals at least one of: working-tree bytes, LF-normalized bytes, or the value recorded inside a freeze/lock JSON (for hashes that are not themselves a file SHA256).

Git commit and tag are git objects, not file hashes.

---

## Frozen identifiers

### Git commit `8f66868850a98494778966bd729b88a6fc2952eb`

| | |
|---|---|
| EXPECTED | `8f66868850a98494778966bd729b88a6fc2952eb` |
| OBSERVED | `8f66868850a98494778966bd729b88a6fc2952eb` |
| MATCH | **YES** |
| Message | Freeze Genome Skeptic V4.1 manuscript system |
| Author date | 2026-09-20 03:01:32 +0100 (02:01:32 UTC) |

### Tag `GENOME_SKEPTIC_V4_1_MANUSCRIPT`

| | |
|---|---|
| EXPECTED | tag name `GENOME_SKEPTIC_V4_1_MANUSCRIPT` pointing at freeze commit |
| OBSERVED tag object | `d63b225537b6e686c9188198940d54b67705200d` (annotated tag) |
| OBSERVED peeled commit | `8f66868850a98494778966bd729b88a6fc2952eb` |
| MATCH | **YES** (tag exists; points at expected commit) |

Do **not** move or rewrite this tag.

### Scientific-core hash

| | |
|---|---|
| EXPECTED | `22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0` |
| OBSERVED | `22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0` (field `scientific_core.scientific_core_hash` in freeze manifest) |
| MATCH | **YES** |

Independent recomputation of this composite hash on a Windows CRLF checkout can differ from the freeze-time value even when source content is unchanged. Treat the freeze-manifest field plus per-file `source_file_hashes` as the canonical record.

### System manifest SHA256

File: `manuscript_benchmark/GENOME_SKEPTIC_V4_1_MANUSCRIPT_manifest.json`

| | |
|---|---|
| EXPECTED | `97a94dfefcecc855ebbba2010fd3f02f79ae84fbc61ca0f173e718d6bffd863b` |
| OBSERVED working-tree | `97a94dfefcecc855ebbba2010fd3f02f79ae84fbc61ca0f173e718d6bffd863b` |
| OBSERVED LF-normalized | `46cf897d69b5f182f24059a3e21f865202aafd0ed65d531ec94cc11e381a1442` |
| OBSERVED git blob (freeze/HEAD) | same as LF-normalized |
| MATCH | **YES** (expected = working-tree / sidecar hash) |

Sidecar: `manuscript_benchmark/GENOME_SKEPTIC_V4_1_MANUSCRIPT_manifest.sha256.json`.

### M60 protocol v1.1 SHA256

File: `manuscript_benchmark/M60_PROTOCOL_V1_1.md`

| | |
|---|---|
| EXPECTED | `73aebeba60e7c03390920c866541a977f86776a2711f804e0b960c08a3aa8660` |
| OBSERVED working-tree (CRLF) | `4f07f33f80733cc30869f46cbf96bcc1b7b7aa537cfbf52215ce7a0cfa401c20` |
| OBSERVED LF-normalized | `73aebeba60e7c03390920c866541a977f86776a2711f804e0b960c08a3aa8660` |
| MATCH | **YES after LF normalization** |

**FLAG (line endings, not content):** a naive SHA256 of the Windows working-tree file does not equal the advertised hash. The sidecar `M60_PROTOCOL_V1_1.md.sha256.json` records the LF hash. `PRE_TRUTH_CHAIN.json` also records the LF hash.

Original protocol `manuscript_benchmark/M60_PROTOCOL.md`:

| | |
|---|---|
| Frozen original protocol SHA256 | `30de5efc92d1b2b0db9de0db6f8f98b965397b6adac17052603b3ab44b74df4f` |
| OBSERVED LF-normalized | `30de5efc92d1b2b0db9de0db6f8f98b965397b6adac17052603b3ab44b74df4f` |
| MATCH | **YES** |

### M60 cohort SHA256

File: `manuscript_benchmark/M60_COHORT_MANIFEST.json`

| | |
|---|---|
| EXPECTED | `014950b8af086c1148b68292276cdcc50f22844e14e1836381072dd936d51655` |
| OBSERVED working-tree | `014950b8af086c1148b68292276cdcc50f22844e14e1836381072dd936d51655` |
| MATCH | **YES** |

CSV sidecar: `8756823e9ec214f2c14bbeb1a8e916f312db4acd6c8d2d7d3b1d78601d199d02`.

### M60 prediction-lock manifest SHA256

File: `manuscript_benchmark/M60_PREDICTION_LOCK_MANIFEST.json`

| | |
|---|---|
| EXPECTED | `5317b33fa554f81855fa6c68854ad732c5f5127fc0ad41f224fede9159a90791` |
| OBSERVED | `5317b33fa554f81855fa6c68854ad732c5f5127fc0ad41f224fede9159a90791` |
| MATCH | **YES** |

### Truth-source manifest SHA256

File: `manuscript_benchmark/TRUTH_M60/M60_TRUTH_SOURCE_MANIFEST.json`

| | |
|---|---|
| EXPECTED | `640138da0b28ede009ca4a7fae2edb0cb70e855178e82df25c94434993e18483` |
| OBSERVED | `640138da0b28ede009ca4a7fae2edb0cb70e855178e82df25c94434993e18483` |
| MATCH | **YES** |

### Original truth SHA256

File: `manuscript_benchmark/TRUTH_M60/M60_EXTERNAL_TRUTH_LOCKED.json`

| | |
|---|---|
| EXPECTED | `bb37539060efd3e89e0bd548fe1d0e573991dab0816bdead729286cbfcfedb38` |
| OBSERVED | `bb37539060efd3e89e0bd548fe1d0e573991dab0816bdead729286cbfcfedb38` |
| MATCH | **YES** |

### Original truth-lock manifest SHA256

File: `manuscript_benchmark/TRUTH_M60/M60_TRUTH_LOCK_MANIFEST.json`

| | |
|---|---|
| EXPECTED | `f6636498de4f7ebc61b50fc85a5a1f48065100b27bfb5eda29e712249fe8c491` |
| OBSERVED | `f6636498de4f7ebc61b50fc85a5a1f48065100b27bfb5eda29e712249fe8c491` |
| MATCH | **YES** |

### Final human-reviewed truth SHA256

File: `manuscript_benchmark/TRUTH_M60/M60_EXTERNAL_TRUTH_FINAL_LOCKED.json`

| | |
|---|---|
| EXPECTED | `a64dea4fd429ede5ea543404fba71e49280495efbbf6d68dc6de324eec35a4a9` |
| OBSERVED | `a64dea4fd429ede5ea543404fba71e49280495efbbf6d68dc6de324eec35a4a9` |
| MATCH | **YES** |

### Final truth-lock manifest SHA256

File: `manuscript_benchmark/TRUTH_M60/M60_TRUTH_FINAL_LOCK_MANIFEST.json`

| | |
|---|---|
| EXPECTED | `787f7a96224c2c61b21a8747bc9e9e46025b126e4b9d0f5b9dd38b4b89f54eb4` |
| OBSERVED | `787f7a96224c2c61b21a8747bc9e9e46025b126e4b9d0f5b9dd38b4b89f54eb4` |
| MATCH | **YES** |

### Sol 5-case preflight manifest

File: `manuscript_benchmark/SOL56_SMALL_PREFLIGHT/SOL56_5CASE_MANIFEST.json`

| | |
|---|---|
| EXPECTED | `7b8ef9e24a5a6a395b6a685ef035f2671fff84bc75b7c3d9ab88553ef0bebc27` |
| OBSERVED | `7b8ef9e24a5a6a395b6a685ef035f2671fff84bc75b7c3d9ab88553ef0bebc27` |
| MATCH | **YES** |

Copied into this repository for GitHub review from the local Sol ablation worktree. Sidecar agrees.

### Full Sol ablation manifest

File: `manuscript_benchmark/SOL56_FULL_ABLATION/SOL56_M60_MANIFEST.json`

| | |
|---|---|
| EXPECTED | `2a9f86956ca12026b4ff39fc7bcaf297db992ba4db53421a9482683ae1885a39` |
| OBSERVED | `2a9f86956ca12026b4ff39fc7bcaf297db992ba4db53421a9482683ae1885a39` |
| MATCH | **YES** |

---

## Additional flags (not hash mismatches of the advertised freeze set)

### Git author date vs JSON `created_utc`

The freeze git commit `8f66868` is dated **2026-09-20 02:01:32 UTC**, but files **inside that commit** include JSON `created_utc` stamps later the same day (D8_MANIFEST `12:43:42Z`; D12_MANIFEST `16:58:41Z`).

Possible interpretations (reviewer to choose; this package does not adjudicate):

- the git freeze commit is a packaging snapshot whose author date is not the operational clock
- machine/clock labeling issues
- later-dated JSON was present when the freeze commit object was written

Operational scientific chronology in this package prefers JSON `created_utc` / `hashed_utc` and M60 selection/lock timestamps. Git history on GitHub has three commits on `master` as of audit construction:

1. `8f66868` Freeze Genome Skeptic V4.1 manuscript system
2. `e92e59d` Publish Genome Skeptic source, docs, and locked M60 artifacts
3. `968d057` Add remaining locked prediction manifests omitted from the previous snapshot

### D8_MANIFEST line endings

| | |
|---|---|
| Exclusion manifest records D8 SHA256 | `37862918643052fa8cb81ff5e180161973a6dd5311aef62bd78c59f8ea74cdbd` |
| Working-tree D8_MANIFEST.json | same (CRLF) |
| Git blob (LF) | `18771fe0a049776591237c7be425e11d2c58871501f68f34036f7cd71a477687` |

Content matches after line-ending normalization.

### No frozen artifact failed the advertised scientific identifier after CRLF handling

No expected freeze/lock hash was found to refer to a **different document**. The only advertised-file mismatch without LF normalization is protocol v1.1 on a CRLF checkout.
