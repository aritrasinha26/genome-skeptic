#!/usr/bin/env bash
rm -rf /home/aritr/m60_work/truth_evidence/position_01_GCF_049943055.1_rpoB_RNAP_beta
pgrep -af 'adjudicate_m60_truth|tblastn' || echo none
