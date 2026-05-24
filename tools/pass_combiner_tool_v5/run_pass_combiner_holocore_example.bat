@echo off
setlocal
python pass_combiner.py ^
  --profile holocore ^
  --base HoloCore.zip ^
  --order-file holocore_pass_order.txt ^
  --project-root-name HoloCore ^
  --output-dir HoloCore_combined ^
  --output-zip HoloCore_combined.zip ^
  --output-patch-zip HoloCore_combined_PATCH_ONLY.zip ^
  --output-diff HoloCore_combined.diff ^
  --report-dir pass_combiner_reports ^
  --compileall ^
  --emit-file-manifest ^
  --emit-symbol-manifest ^
  --fail-on-symbol-removal ^
  --emit-repo-handoff ^
  --repo-name GLITCHEDMATR1X/GX-Prototype-Lab
endlocal
