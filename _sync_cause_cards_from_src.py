"""一次性脚本：从 roxie-rag-service 本地源码的 pydantic 模型生成 dtc-cause-cards 最新契约，
并同步到 myskills/dtc-cause-cards-skill/tool-schema.json。

远端服务不可达时，本地源码 checkout 即最新契约来源。
通过 stub 包按文件路径加载模型，避免触发 dtc_rag 包 __init__ 的重依赖链。
"""
import importlib.util
import json
import sys
import types
from pathlib import Path

RAG_SRC = Path(r"E:\codes\cop_pro\software\AI_China\Dev\trunk\services\Platform\roxie-rag-service\src")
LOCAL_SCHEMA = Path("myskills/dtc-cause-cards-skill/tool-schema.json")


def load_module(fqname: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(fqname, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[fqname] = module
    spec.loader.exec_module(module)
    return module


def make_package(fqname: str, path: Path) -> types.ModuleType:
    pkg = types.ModuleType(fqname)
    pkg.__path__ = [str(path)]
    sys.modules[fqname] = pkg
    return pkg


# stub 包层级：dtc_rag / dtc_rag.context / dtc_rag.cause_cards
make_package("dtc_rag", RAG_SRC / "dtc_rag")
make_package("dtc_rag.context", RAG_SRC / "dtc_rag" / "context")
make_package("dtc_rag.cause_cards", RAG_SRC / "dtc_rag" / "cause_cards")
load_module("dtc_rag.context.vocab", RAG_SRC / "dtc_rag" / "context" / "vocab.py")
load_module("dtc_rag.context.normalizer", RAG_SRC / "dtc_rag" / "context" / "normalizer.py")
models = load_module("dtc_rag.cause_cards.models", RAG_SRC / "dtc_rag" / "cause_cards" / "models.py")

input_schema = models.CauseCardsRequest.model_json_schema()
output_schema = models.CauseCardsResponse.model_json_schema()

local = json.loads(LOCAL_SCHEMA.read_text(encoding="utf-8"))
old_in = local.get("input_schema")
old_out = local.get("output_schema")

local["input_schema"] = input_schema
local["output_schema"] = output_schema
LOCAL_SCHEMA.write_text(
    json.dumps(local, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)


def fields(schema):
    if not isinstance(schema, dict):
        return {}
    out = dict(schema.get("properties") or {})
    for d in (schema.get("$defs") or {}).values():
        for k, v in (d.get("properties") or {}).items():
            out[f"{d.get('title', '?')}.{k}"] = v
    return out


new_in_fields = sorted(fields(input_schema))
new_out_fields = sorted(fields(output_schema))
print("input_schema 顶层字段:", sorted((input_schema.get("properties") or {}).keys()))
print("output_schema 顶层字段:", sorted((output_schema.get("properties") or {}).keys()))
print("$defs(out):", sorted((output_schema.get("$defs") or {}).keys()))
print("input changed:", json.dumps(old_in, sort_keys=True, ensure_ascii=False) != json.dumps(input_schema, sort_keys=True, ensure_ascii=False))
print("output changed:", json.dumps(old_out, sort_keys=True, ensure_ascii=False) != json.dumps(output_schema, sort_keys=True, ensure_ascii=False))
