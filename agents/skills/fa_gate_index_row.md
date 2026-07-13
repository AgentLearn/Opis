---
name: fa_gate_index_row
agent: fa
binding: GATE_INDEX_ROW_PROMPT
---
Given this gate file, output a single markdown table row to append to the gates index.
Format (pipe-separated, no leading/trailing pipes):
 <name> | <kind: gate|sentinel|regulator> | <comma-separated input slot types> | <comma-separated output slot types> | <true|false>

Output only the table row, nothing else.