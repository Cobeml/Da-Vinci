"""Discoverable wire schemas, shipped as a resource as well as exposed offline/HTTP."""

import json

from davinci.product.tasks import RESOURCES


def build_catalog():
    from davinci.product import contracts as c
    from davinci.product import lifecycle_api as api
    from davinci.product import managed_contracts as managed
    from davinci.product import measurement_contracts as measurements
    from davinci.product import memory_contracts as memory
    from davinci.product import tool_contracts as tools
    from davinci.product.mechanism.contracts import SliderSettings
    from davinci.product.memory_api import Capture, Reindex
    from davinci.product.simulation_contracts import AdapterDescriptor, ArtifactManifest, SimulationSpec
    from davinci.product.structural.contracts import StructuralSettings
    from davinci.product.transfers import ContinueExperiment, Handoff

    models = [
        SliderSettings,
        measurements.RecordMeasurement,
        measurements.MeasurementInput,
        measurements.CalibrationFit,
        measurements.CalibrationValidation,
        measurements.EvidenceExport,
        measurements.EvidenceRestore,
        tools.ToolNeed,
        tools.ToolDefinition,
        tools.ToolProposal,
        tools.ToolVersionCommand,
        tools.ToolPromotion,
        tools.ToolPin,
        tools.ToolInvocation,
        tools.ManagedToolProposal,
        tools.PlateArguments,
        StructuralSettings,
        ContinueExperiment,
        Handoff,
        managed.ManagedRequest,
        managed.SearchPolicy,
        managed.RequirementsOutput,
        managed.TestPlanOutput,
        managed.SetupOutput,
        managed.DiagnosisOutput,
        managed.Answers,
        managed.StageInput,
        memory.Experience,
        memory.MemorySearch,
        memory.MemoryNote,
        memory.ExactInputs,
        memory.Supersession,
        memory.MemoryBundle,
        memory.MemoryImport,
        memory.MemoryExport,
        Capture,
        Reindex,
        AdapterDescriptor,
        ArtifactManifest,
        SimulationSpec,
        c.OperationStatus,
        c.PlanReadiness,
        c.ReportExport,
        c.CLIEnvelope,
        c.OpenExperiment,
        c.Command,
        c.Plan,
        c.Candidate,
        c.Verification,
        c.TestResult,
        c.EvaluationResult,
        c.ExperienceReference,
        api.PlanCommand,
        api.FixtureCommand,
        api.VerificationCommand,
        api.FreezeCommand,
        api.CandidateCommand,
        api.ReflectionCommand,
        api.ReferenceBuildCommand,
    ]
    return {
        "version": 2,
        "schemas": {m.__name__: m.model_json_schema() for m in models},
        "cli_envelope": {"version": 2, "ok": "boolean", "data": "JSON value"},
        "exit_codes": {
            "0": "operation succeeded (does not imply design acceptance)",
            "1": "unexpected or local IO error",
            "2": "invalid input",
            "3": "service unavailable",
            "4": "revision, ownership or idempotency conflict",
            "5": "not found",
            "6": "job interrupted or cancelled",
            "7": "wait timed out; job may still be running",
        },
        "job_states": ["queued", "running", "completed", "interrupted", "cancelled"],
    }


def schema_catalog():
    return json.loads(RESOURCES.joinpath("external/schemas.json").read_text())
