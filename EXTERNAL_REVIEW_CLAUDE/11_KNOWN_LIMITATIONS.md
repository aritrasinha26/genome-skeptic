# Known limitations

1. Only **41 / 60** cases had resolved independent truth.
2. **19 / 60** were `TRUTH_UNCERTAIN`.
3. Half of rpoB cases (15 / 30) were truth-uncertain.
4. All **15** truth-evaluable rpoB cases were **positive**.
5. Therefore **rpoB specificity is not estimable**.
6. M60 is 60 genome-target cases across **two** endpoints, not a universal genome annotation benchmark.
7. tetA/rpoB were chosen after D8/D12 development experience, **but before M60 sampling**.
8. tuf/lacZ were not manuscript-primary because development exposed unresolved endpoint/instrument limitations.
9. Sol analysis is **post-hoc**.
10. Mechanistic error analysis is **post-hoc**.
11. Same observed accuracy between Agentic and Exhaustive is **NOT** a formal equivalence result.
12. Number of deterministic analyses and wall-clock runtime are **distinct** efficiency measures.
13. Truth adjudication used two independent **evidence routes** but **not** two independent human expert reviewers.
14. D20 filesystem history: candidate pool used for exclusion; partial V5 prescreen exists and was blocked; final D20 cohort never locked; M60 flags `d20_touched: false` mean results/labels were not opened — **not** that the directory was absent. JSON `created_utc` vs git freeze author date disagree for some manifests.

---

## Additional limitations discovered from the repository

15. **tetA sensitivity is 0 / 7** for all GS arms and for AMRFinderPlus. The “33/41” headline is almost entirely tetA true-negative specificity (19/19) plus rpoB true-positive recall (14/15).
16. Conventional tetA 20/26 is driven by 19 TN + 1 TP; GS tetA is 19 TN + 0 TP. Pooled accuracy can hide a complete miss of the positive class.
17. Specialist 34/41 **pools two tools**. tetA specialist did not outperform GS; rpoB specialist did.
18. Challenge cases were selected using **frozen V4.1 deterministic ambiguity scores** — selection on Det instruments.
19. Truth numeric gates **overlap** GS validator thresholds; packaged family FASTAs were **copied** into truth SOURCE_FREEZE.
20. One human-adjudicated label change (position 34) entered the final denominator; no sensitivity analysis excluding that change is in the primary script.
21. Genome FASTA files, truth evidence trees, human-review packets, eligible pool JSON, and run logs are **not all on GitHub** (gitignore). Independent re-execution of measurements requires re-download via recorded accessions/SHA256s.
22. Freeze git commit author date is earlier than some JSON `created_utc` values stored **inside that commit** (see `PROVENANCE_VERIFICATION.md`).
23. Windows CRLF vs LF hashing: advertised hashes mix working-tree CRLF and LF-normalized conventions.
24. Production M60 used WSL Python **3.11.16**; freeze-manifest environment block records Windows Python **3.13.1** with BLAST/HMMER unavailable. Do not treat the freeze-manifest `environment` object as the M60 execution host.
25. Qwen quantization `Q4_K_M` is documented in the V2 agentic freeze with the same digest as M60 locks, not in `M60_ENVIRONMENT.json`.
26. Agentic `m0 ≠ m_final` on 60/60 cases, yet endpoints matched Det 60/60: follow-up measurements were **non-decision-changing** under the validator. Efficiency claims about “useful” analyses need this caveat.
27. n=41 is small; Wilson intervals are wide (GS 0.660–0.898). Zero discordant pairs make bootstrap CI degenerate at 0–0 and McNemar undefined — that is a **feature of complete concordance**, not a precision claim about a non-zero effect.
28. No preregistered analysis of positive-class performance as primary; tetA 0/7 can be under-emphasized if only pooled accuracy is quoted.
29. Sol adapter / `openai_api` provider is **not** in frozen M60 `providers.py`; reproducing Sol requires the post-hoc code copy.
30. D8/D12 truth protocols differ from M60 truth (e.g. D8 used PGAP AMR corroboration). Do not meta-analyze D8/D12/M60 accuracies as one experiment.
