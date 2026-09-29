from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ObjectConfig(Strict):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    name: str = Field(min_length=1, max_length=100)


class TaskConfig(Strict):
    template: Literal["sensor", "gripper", "vtol", "custom"] = "sensor"
    description: str = Field(min_length=1, max_length=12000)
    path: str | None = None


class Objective(Strict):
    metric: str
    direction: Literal["minimize", "maximize"]
    target: float | None = None


class Constraint(Strict):
    metric: str
    operator: Literal["<=", ">="]
    value: float
    unit: str


class RunOptions(Strict):
    iterations: int = Field(default=6, ge=1, le=50, strict=True)
    budget_usd: float = Field(default=10, gt=0, le=1000)
    mode: Literal["live", "replay"] = "live"


class Continuation(Strict):
    seed_candidate_id: str


class RunConfig(Strict):
    version: Literal[1] = 1
    object: ObjectConfig
    task: TaskConfig
    objective: Objective
    constraints: list[Constraint] = Field(default_factory=list, max_length=30)
    run: RunOptions = Field(default_factory=RunOptions)
    continuation: Continuation | None = None


def parse_yaml(content: str) -> RunConfig:
    if len(content.encode()) > 100_000:
        raise ValueError("YAML must be smaller than 100 KB")

    # No custom tags; duplicate keys are rejected, not silently overwritten.
    class UniqueLoader(yaml.SafeLoader):
        pass

    def mapping(loader, node):
        result = {}
        for key, value in node.value:
            name = loader.construct_object(key)
            if name in result:
                raise ValueError(f"Duplicate YAML key: {name}")
            result[name] = loader.construct_object(value)
        return result

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    try:
        return RunConfig.model_validate(yaml.load(content, Loader=UniqueLoader))
    except (yaml.YAMLError, RecursionError) as exc:
        raise ValueError("Invalid YAML") from exc


class WorkspaceSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="forbid", env_prefix="DAVINCI_PRODUCT_")
    storage: Literal["local", "atlas"] = "local"
    database: str = "da_vinci_product"
    port: int = Field(default=8741, ge=1024, le=65535)
    model: str = "gpt-6-astra"
    # Explicit workspace accounting rates, USD per million tokens; not a price quote.
    input_usd_per_million: float = Field(default=20, gt=0)
    output_usd_per_million: float = Field(default=75, gt=0)
    pricing_model: str = "gpt-6-astra"
    daily_budget_usd: float = Field(default=50, gt=0)
    output_tokens: int = Field(default=6000, ge=1000, le=32000)


def workspace_settings(root: Path):
    path = root / "workspace.yaml"
    return WorkspaceSettings(**(yaml.safe_load(path.read_text()) if path.exists() else {}))
