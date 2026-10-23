"""Use grammars installed at build/setup time; repository processing never downloads code."""

import os
import threading
from functools import lru_cache
from pathlib import Path

from devproof_agent.models import AgentError

_lock = threading.Lock()
_configured = False
LANGUAGES = ("java", "python", "javascript", "typescript", "tsx")


@lru_cache(maxsize=8)
def parser(language: str):
    import tree_sitter_language_pack as pack
    global _configured
    with _lock:
        if not _configured:
            cache = Path(os.environ.get("TREE_SITTER_CACHE_ROOT", str(Path.cwd() / ".build" / "parser-cache"))).resolve()
            pack.configure(pack.PackConfig(cache_dir=str(cache)))
            _configured = True
        if language not in LANGUAGES or language not in pack.downloaded_languages():
            raise AgentError("PARSER_UNAVAILABLE", "所需语法资源尚未在构建或环境准备阶段安装")
        return pack.get_parser(language)
