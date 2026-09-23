# V5 ALIGNMENT — ROLE-SWAP PHASE 1

This role-swap freeze **reuses** the immutable V5 scientific freeze. It does
not create V6 biology.

| Component | V5 expected | Role-swap observed | Match |
|-----------|-------------|--------------------|-------|
| scientific_core | `86af163a1e427c83ed0010fbca69ba6a9f81b7a97ae1eda2f1be35179a8ea463` | same | YES |
| validator | `cf6d6c5b26d74de9f475ba6d4d7de3ddef9b95d222c08efbbc202a2164d38672` | same | YES |
| action_registry | `185390460dd990516b89eab036b5c5da11e2d28ef3371c5e4917a4e2fd6ac899` | same | YES |
| planner_prompt | `fcffbc11cf6afbe84731c15854d37e85d929b966318acc45567f5332819d0f63` | same | YES |
| critic_prompt | `8b04802de10aea03d24b26633a17d68415db74db3ba82034b6b8d1cf75f2b60e` | same | YES |
| family_definitions | `ed4210640e318b8ed94ebf6d72b9c37afa9039eed858fdd54c4165fbcce09605` | same | YES |
| ortholog / reference assets | `9434a1902236ed7245361e47af1986357969a3bf8ec210062f889dc84580ff92` | same | YES |

Parent tag: `GENOME_SKEPTIC_V5_VALIDATOR_REPAIR`

Verification: `python -c "from scripts.model_poc_v5.freeze import verify_v5_freeze; ..."`  
Recorded in: `ROLE_SWAP_FREEZE_CHECK.json`

**v5_biology_modified:** NO  
**second_target_created:** NO
