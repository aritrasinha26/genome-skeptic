# Code path manifest

Production call graph is described in `02_SYSTEM_ARCHITECTURE.md`.

Hashes are SHA256 of working-tree bytes and LF-normalized bytes.
On Windows, CRLF files may differ from git LF blobs; see `PROVENANCE_VERIFICATION.md`.

| relative path | SHA256 (working tree) | SHA256 (LF-normalized) | purpose | status |
|---|---|---|---|---|
| `scripts/run_m60_position.py` | `4278c24f080c04ab0be590254a9ee51a0331c66b0b4c9448bc7fa96650819884` | `4278c24f080c04ab0be590254a9ee51a0331c66b0b4c9448bc7fa96650819884` | M60 runner; freeze verify; arms; specialist; position lock | prospective |
| `scripts/select_m60_cohort.py` | `a0a69e2a4e7d7291758e1bf2548c663b06fba5335ce13bd1ebbdcf7210860832` | `026fd87251826d37f5156b804df57dffe5b79b3aad190d0c83d102bf24c2ab40` | M60 cohort selection seed 20260920 | prospective |
| `scripts/build_m60_exclusion_manifest.py` | `d783d336cb9ac10a93f5e4765045a92fe686d2ebf0aec2dcbd7dc15f5efab905` | `28bff14f03ed18d840f25bcbc8616684bd1891182818f6171e00af627498a4f4` | Exclusion set before sampling | prospective |
| `scripts/finalize_m60_predictions.py` | `4048ee5fd3aca569cd4ca903bf31f8a418938b2aadef16eb0edec2d2b13932f7` | `4048ee5fd3aca569cd4ca903bf31f8a418938b2aadef16eb0edec2d2b13932f7` | Aggregate prediction lock | prospective |
| `scripts/freeze_m60_truth_sources.py` | `dc9562be585e88e4b2d01cc714ece81d9c6f60abcb4aa4bf4c5ac0f6aaf9c3db` | `dc9562be585e88e4b2d01cc714ece81d9c6f60abcb4aa4bf4c5ac0f6aaf9c3db` | Truth source freeze | prospective |
| `scripts/adjudicate_m60_truth.py` | `cefc306f35af83d93cb625d278469f94f5afbda28e1e6dc91f44ebd5690b2fed` | `cefc306f35af83d93cb625d278469f94f5afbda28e1e6dc91f44ebd5690b2fed` | Two-route automated truth | prospective |
| `scripts/lock_m60_truth.py` | `4bc916d4b89fdf9a55b9bd5984a4d4cf1350406fde53e082d4ce1c327b2a1ae9` | `4bc916d4b89fdf9a55b9bd5984a4d4cf1350406fde53e082d4ce1c327b2a1ae9` | Phase 3 truth lock | prospective |
| `scripts/lock_m60_phase3b.py` | `ad8fe0691d8624981e61721c91bb1ceb80a015c5f7a3759c0a3948307f657ce4` | `ad8fe0691d8624981e61721c91bb1ceb80a015c5f7a3759c0a3948307f657ce4` | Human review + final truth lock | prospective |
| `scripts/m60_truth_common.py` | `0cf2fad0b9858e6a44e60ec5cba3771226b704d14f5c33651e440054bbee056e` | `0cf2fad0b9858e6a44e60ec5cba3771226b704d14f5c33651e440054bbee056e` | Truth gates and path guards | prospective |
| `scripts/score_m60_phase4.py` | `589141cbab4a399bc3219f3d1c8ffddb8a2f839a178be1e36148157e63daea90` | `589141cbab4a399bc3219f3d1c8ffddb8a2f839a178be1e36148157e63daea90` | One-shot unblind statistics | prospective |
| `scripts/freeze_manuscript_v4_1.py` | `dd984cb248b336db5eda732d967daf9beb8b108300becc6556b788a5140018d0` | `f3d1e40dc3eebf76a67b40aca03696ffdee33990facb630cf5948861e86e4b5f` | V4.1 freeze writer | development/freeze |
| `src/genome_skeptic/manuscript/arms.py` | `fe24047e8213f50550c237157f7a9e372b355f4e4f6db5593bc973133bead4e9` | `3cec8901d9eff83bcb3fcf795d58b6f1d0bc7172088f8cc738107b39c3f2b45f` | GS arm aliases | frozen |
| `src/genome_skeptic/manuscript/scientific_core.py` | `19c50f381ad74b5c8d656d739a9bd14090f31ae24da393e89d7e775296bc5412` | `e5eba4963a7e9910b2835399dd2228ee2d3666e259b94b9c86209505d44d1fff` | Shared-core hasher | frozen |
| `src/genome_skeptic/agents/assembly_loop.py` | `1d16daf228cb3d3cfccd61656205a4054b1480bb7cd38a4f15088c8ed781f114` | `92c3fd3818b43d042b3896e0aea5a294ee53f7fba46a708315dd2d52305f8383` | Initial measurement collection; evidence ledger helpers | frozen |
| `src/genome_skeptic/agents/assembly_loop_v4_1_dev.py` | `76841a49c2511a034c0944210b65e3d21ca5104499c75855d3062c8bf7ecc9e9` | `76841a49c2511a034c0944210b65e3d21ca5104499c75855d3062c8bf7ecc9e9` | V4.1 loop; policies; planner/critic prompts | frozen |
| `src/genome_skeptic/agents/assembly_loop_v2.py` | `d755436b3dee093a7e8a3f48e00122e3c41d6571a1735c14e02c6a0bc72afe4f` | `4d51b11f6692d5fa8f9d7092c09bc18d3303bbdcccf2a3d461d861197d539ded` | Registered action execution | frozen |
| `src/genome_skeptic/agents/action_catalog.py` | `f1f76ed5bd9dce28fd04f7be0eae263ea4d391d0754193d77923ffebaa06e26a` | `ea4e1794a697a92c0e191f7e915c15d87b3d1a743588d168deb2f74c85a34bd4` | Base action registry | frozen |
| `src/genome_skeptic/agents/action_catalog_v4_1_dev.py` | `bed8e3d19fcb91178299c9200ea63c7bcde830cc87f92a13566ca5f9b61286a2` | `bed8e3d19fcb91178299c9200ea63c7bcde830cc87f92a13566ca5f9b61286a2` | V4.1 extra actions; ranking | frozen |
| `src/genome_skeptic/agents/planner_views_v4_1_dev.py` | `a342f4ff1611d1cb40ee1f3ade36c61654a6ca3a4e1db49bfeb6148775ca6d7b` | `a342f4ff1611d1cb40ee1f3ade36c61654a6ca3a4e1db49bfeb6148775ca6d7b` | Planner/critic views | frozen |
| `src/genome_skeptic/agents/diagnostic_needs_v4_1_dev.py` | `006645e6791132715a245ddeeeb5cebd5a8741da1330fddc69e8325fe463ca9f` | `006645e6791132715a245ddeeeb5cebd5a8741da1330fddc69e8325fe463ca9f` | Needs + family_identity_is_decisive | frozen |
| `src/genome_skeptic/agents/ollama.py` | `e02cef1f7a1921b99d6d144a33039564da83471064bf99013530e565108e9b09` | `e02cef1f7a1921b99d6d144a33039564da83471064bf99013530e565108e9b09` | Ollama JSON client | frozen |
| `src/genome_skeptic/agents/adapter.py` | `7bb18c22323fd4cf9f56c57b979950493c724107b6e6a06edf432783ffcc5bec` | `c80fd4f3af2cb31179d2be1c882594a913abb3504e5673c18bd9cb268c9f5029` | OpenAI-compatible adapter | frozen |
| `src/genome_skeptic/agents/providers.py` | `b29eae9339d9a508a2d497ea2a19dc3f2cac958211503391d7485b47c65dd6f3` | `37389754a12ec812236647cfa263928e2865ad21e6f13e918654985202f1bea0` | Production M60 providers (Qwen/Ollama) | frozen |
| `src/genome_skeptic/eval/baselines.py` | `778efbc91bd2becf35c53717b84166099e78222999bae970b386c31156ccaa46` | `246afdca53320b170e977421af69033e1859b1993d133dd50ba09740fdf1b790` | Conventional arm | frozen |
| `src/genome_skeptic/eval/evaluate_real.py` | `5375e34ebcb0fd41333178ec44d12dcbb4b4f7094222b7973a372dc0f4b29e4f` | `9a59b393803394a58196efa2629f278d50adfe3208f69b941a0474019f25f56f` | System dispatch including conventional | frozen |
| `src/genome_skeptic/validators/falsification.py` | `a062415a7a30c76b1f52c4958e953aca9d75f56f28f4f3893db0ca8a62ec6966` | `02f9676acc1b2f1e7be722a45fb23189f3b3a805f952eaac4435bfb6a1a01ed1` | TargetMeasurements; classify_polarity; build_target_gene_claim | frozen |
| `src/genome_skeptic/validators/family_orthology.py` | `c175eec390a15783c15dc0f6874ce27cd1d3354d465f4fc8a958353fd0bed95e` | `28844e6206000c550769663e483ae38e685ddf62a5b133bf349f7e789f9b2b53` | collect_family_evidence; family_detects_orthologue | frozen |
| `src/genome_skeptic/validators/competitive_family.py` | `19d73cdf1255d4f1e8379d453b5838a581c3e8c4802005f771f771c7c4ae7cdc` | `183ee7b5ee114c8941f86102f5f6dcbfca2ad459d1d4d486d3607674a161550a` | discriminate_family | frozen |
| `src/genome_skeptic/validators/locus_v4_dev.py` | `d3d0f7be07637e8199932a74e3da33ab28a40fff58d45b8a8e1161029ece5982` | `9d501123f0e4ac40c086c5c683447a939f29cbae91b580f7bc3a78886ddd3c84` | refine_weak_family_classification | frozen |
| `src/genome_skeptic/validators/locus_reconstruction.py` | `8cce6d6c1f9953a9089bc5b35a4a1878185f06f8b62d4901d6f35456a8d80ade` | `2a0a19ffa1db342e6515ec88a8baed2f151442ee30be84cfd37b06a5746ba7ff` | domain_only architecture | frozen |
| `src/genome_skeptic/validators/homology.py` | `a972961fb4f8bf16940d37b52bc02ed8a7a56dc19ac52b3ea9a2311c32019b45` | `42f107e8a04fcbab84f4dbcbafd7af416f18066154d66df84755d32da20d0ea0` | strong_hit thresholds | frozen |
| `src/genome_skeptic/config.py` | `1daf2c00ddf5b9307e8b753000b7058af09080922c574517718cd1fb5dbfe3a3` | `1daf2c00ddf5b9307e8b753000b7058af09080922c574517718cd1fb5dbfe3a3` | Biological thresholds | frozen |
| `src/genome_skeptic/families.py` | `fc13a07c21df567893a39ac5c70d986b7d8b9bc1bd1c2e6237b546ed2ac128df` | `a5605a596eb7a1197e4a929786c62db7e20ed537a061367e2e83feacf81c8554` | Family loader | frozen |
| `config/qwen_agentic_dev.yaml` | `32c4492db261c4185191b908a32886d05050d00831cf91790ae88a3b24bea744` | `abbbc8dbe4df4c859bcbb86bdd0c0abc800648a0a1a422778e933d36048abc00` | M60 Agentic Qwen config | frozen-config |
| `config/sol56_high_posthoc.yaml` | `662a878420a1e8bd015c72e414b037249d6aa2415746621e9a135ec33dcf6bfa` | `662a878420a1e8bd015c72e414b037249d6aa2415746621e9a135ec33dcf6bfa` | Sol post-hoc config | post-hoc |
| `EXTERNAL_REVIEW_CLAUDE/posthoc_code/src/genome_skeptic/agents/providers.py` | `08302df8486bfc6889811fa9a61b8976153718d5f86edb58c35fda35e504b69c` | `08302df8486bfc6889811fa9a61b8976153718d5f86edb58c35fda35e504b69c` | Sol openai_api adapter (NOT frozen M60 src) | post-hoc |
| `EXTERNAL_REVIEW_CLAUDE/posthoc_code/scripts/run_sol56_full_ablation.py` | `ff4f04ad3587621f8cf8454217d7ce5a7b5285cd608d2126e1e986d372468556` | `ff4f04ad3587621f8cf8454217d7ce5a7b5285cd608d2126e1e986d372468556` | Sol full ablation runner | post-hoc |
| `manuscript_benchmark/POSTHOC_ERROR_ANALYSIS/_extract_frozen_error_artifacts.py` | `3bb61845e4549d95fe3da583e407ff4b025bf6555a00fac6ec0a3434e8d34b6e` | `3bb61845e4549d95fe3da583e407ff4b025bf6555a00fac6ec0a3434e8d34b6e` | Read-only forensic extract | post-hoc |
