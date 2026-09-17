import re
from pathlib import Path

import pytest

from dw_agent_runtime.registry import ConfigError
from dw_agent_runtime.toolsets import ToolsetRegistry
from dw_kernel.errors import NotFoundError

pytestmark = pytest.mark.unit

TOOLSET = """\
schema_version: "1.0"
toolset_id: sales_chat
version: "1.0.0"
tools:
  - { name: crm.read_account, version: "1.2.0" }
  - { name: crm.create_task, version: "1.0.0" }
"""


def write_toolset(directory: Path, body: str, filename: str = "sales_chat@1.0.0.yaml") -> Path:
    path = directory / filename
    path.write_text(body, encoding="utf-8")
    return path


def test_a_toolset_resolves_to_ordered_pins(tmp_path: Path) -> None:
    registry = ToolsetRegistry()
    registry.load_file(write_toolset(tmp_path, TOOLSET))

    toolset = registry.resolve("sales_chat", "1.0.0")
    assert toolset.pins == (("crm.read_account", "1.2.0"), ("crm.create_task", "1.0.0"))


def test_pinning_two_versions_of_one_tool_is_refused(tmp_path: Path) -> None:
    body = TOOLSET.replace(
        '  - { name: crm.create_task, version: "1.0.0" }',
        '  - { name: crm.read_account, version: "1.0.0" }',
    )
    with pytest.raises(ConfigError, match=re.escape("crm.read_account")):
        ToolsetRegistry().load_file(write_toolset(tmp_path, body))


def test_an_empty_toolset_is_refused(tmp_path: Path) -> None:
    body = TOOLSET.split("tools:")[0] + "tools: []\n"
    with pytest.raises(ConfigError, match="invalid"):
        ToolsetRegistry().load_file(write_toolset(tmp_path, body))


def test_an_unknown_field_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="invalid"):
        ToolsetRegistry().load_file(write_toolset(tmp_path, TOOLSET + "notes: hello\n"))


def test_malformed_yaml_names_the_file_it_came_from(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=re.escape("sales_chat@1.0.0.yaml")):
        ToolsetRegistry().load_file(write_toolset(tmp_path, "tools: [unbalanced\n"))


def test_duplicate_toolset_version_is_refused(tmp_path: Path) -> None:
    registry = ToolsetRegistry()
    registry.load_file(write_toolset(tmp_path, TOOLSET))
    with pytest.raises(ConfigError, match="already registered"):
        registry.load_file(write_toolset(tmp_path, TOOLSET, filename="copy.yaml"))


def test_unknown_toolset_is_not_found(tmp_path: Path) -> None:
    registry = ToolsetRegistry()
    registry.load_file(write_toolset(tmp_path, TOOLSET))
    with pytest.raises(NotFoundError):
        registry.resolve("sales_chat", "9.0.0")
