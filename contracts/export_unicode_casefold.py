"""Export the actual Python Unicode folding table used by source-role matching."""
import json
import unicodedata
from pathlib import Path

mapping = {str(point): chr(point).casefold() for point in range(0x110000)
    if chr(point).casefold() != chr(point)}
target = Path(__file__).resolve().parent / "unicode-casefold.json"
target.write_text(json.dumps({"unicodeVersion": unicodedata.unidata_version, "casefold": mapping},
    ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
print("Exported Python Unicode", unicodedata.unidata_version, "casefold mappings:", len(mapping))
