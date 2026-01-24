# Implementation Plan - Fix HIL Empty Content Error

## Goal
Fix the issue where applying HIL revisions returns an "empty content" error message, even though the original document is preserved. The goal is to align the backend's `QualityService` logic with the robust CLI implementation in `mlx_vomo.py` and `auto_fix_apostilas.py`.

## Problem Description
The user reports: "Erro: o backend retornou conteúdo vazio. O documento original foi preservado."
This occurs in the `apply-revisions` endpoint when `revised_content` evaluates to empty.
Currently, `QualityService.apply_structural_fixes_from_issues` (and `apply_approved_fixes`) writes content to a temp file, calls the auto-fix script, and then *always* reads the file back.
If no fixes are applied, the auto-fix script does not write to the file. While the file *should* retain original content, always reading it back adds unnecessary I/O risk and potential encoding/buffer issues that might return empty strings.
The CLI `mlx_vomo.py` only reads the file back `if result['fixes_applied']`.

## Proposed Changes

### [apps/api]

#### [MODIFY] [quality_service.py](file:///Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/services/quality_service.py)
*   Update `apply_structural_fixes_from_issues` method:
    *   Check `result.get('fixes_applied')` before reading `tmp_path`.
    *   If no fixes applied, or list is empty, return original `content` directly.
    *   Only read `new_content` from disk if fixes were applied.
*   Update `apply_approved_fixes` method (for consistency):
    *   Apply the same logic: only read `tmp_path` if fixes were reported as applied.
