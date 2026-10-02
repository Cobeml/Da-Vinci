"""Shared, project-scoped engineering memory. No provider, cache execution, or paid calls."""

import base64
import fcntl
import hashlib
import json
import re
import uuid

from davinci.models import digest, now
from davinci.product.embeddings import Embeddings, tokens
from davinci.product.memory_contracts import (
    Applicability,
    EvidenceArtifact,
    ExactInputs,
    Experience,
    MemoryBundle,
    MemoryImport,
    MemoryNote,
    MemorySearch,
    SourceReference,
    Supersession,
)

COLLECTION = "experiences_v1"
MAX_BUNDLE = 16_000_000


class ExperienceMemory:
    def __init__(self, engine):
        self.engine, self.store, self.artifacts = engine, engine.store, engine.artifacts
        # A copied/moved workspace retains its logical namespace; unrelated workspaces get distinct IDs.
        marker = engine.root / "memory-workspace-id"
        with (engine.root / "memory-workspace.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if marker.is_symlink():
                raise ValueError("Memory workspace identity cannot be a symlink")
            if not marker.exists():
                marker.write_text(uuid.uuid4().hex)
            with marker.open() as stream:
                workspace_id = stream.read(100)
            if not re.fullmatch(r"[a-f0-9]{32}", workspace_id):
                raise ValueError("Invalid memory workspace identity")
        self.scope = {"workspace_id": workspace_id, "project_id": engine.options.project_id}
        self.embeddings = Embeddings(engine.options.embedding)
        self.store.ensure_experience_indexes()

    def _run(self, identity):
        row = self.store.get("runs", identity)
        if not row or any(row.get(k) != v for k, v in self.scope.items()):
            raise KeyError("Run not found in active project/workspace")
        return row

    def _public(self, row):
        return Experience.model_validate(
            {k: row[k] for k in Experience.model_fields if k in row}
        ).model_dump()

    def get(self, identity, *, verify=False):
        row = self.store.get(COLLECTION, identity)
        if not row or any(row.get(k) != v for k, v in self.scope.items()):
            raise KeyError("Experience not found")
        record = self._public(row)
        if verify:
            issues = list(record["evidence_issues"])
            for artifact in record["artifacts"]:
                try:
                    actual = self.store.get("artifacts", artifact["artifact_id"])
                    if not actual or any(actual[k] != artifact[k] for k in ("sha256", "size")):
                        raise ValueError("Invalid artifact reference")
                    self.artifacts.verify(artifact["artifact_id"])
                except (ValueError, KeyError, OSError):
                    issues.append("Missing or invalid artifact: " + artifact["artifact_id"])
            record["evidence_issues"] = sorted(set(issues))
        return record

    def _refs(self, identities):
        refs = []
        for identity in sorted(set(identities)):
            record = self.store.get("artifacts", identity)
            if record:
                refs.append(
                    EvidenceArtifact(
                        artifact_id=identity,
                        **{k: record[k] for k in ("sha256", "size", "name", "media_type")},
                    )
                )
        return refs

    def context(self, row):
        plan = row.get("plan", {})
        tests = plan.get("tests", [])
        specs = [t["simulation"] for t in tests if t.get("simulation")]
        phenomena = sorted({v for s in specs for v in s["phenomena"]})
        domain = "aerodynamics" if "attached_flow" in phenomena else "mechanical" if phenomena else ""
        return Applicability(
            domain=domain,
            phenomena=phenomena,
            material_models=sorted({s["material_model"] for s in specs}),
            materials=[m["name"] for m in plan.get("materials", [])],
            quantities={
                **{
                    f"material:{m['name']}:{name}": {
                        "minimum": q["value"],
                        "maximum": q["value"],
                        "unit": q["unit"],
                        "dimension": q["dimension"],
                    }
                    for m in plan.get("materials", [])
                    for name, q in m.get("properties", {}).items()
                },
                **{
                    f"load:{case['id']}:{name}": {
                        "minimum": q["value"],
                        "maximum": q["value"],
                        "unit": q["unit"],
                        "dimension": q["dimension"],
                    }
                    for t in tests
                    for case in t.get("load_cases", [])
                    for name, q in case.get("quantities", {}).items()
                },
            },
            processes=plan.get("metadata", {}).get("processes", []),
            load_regimes=plan.get("metadata", {}).get(
                "load_regimes", ["static"] if "linear_static" in phenomena else []
            ),
            assumptions=[a["description"] for a in plan.get("assumptions", [])],
        )

    def _persist(self, record, signature):
        record = Experience.model_validate(record).model_dump()
        if len(json.dumps(record, allow_nan=False).encode()) > 2_000_000:
            raise ValueError("Experience exceeds 2 MB; keep large evidence in artifacts")
        old = self.store.get(COLLECTION, record["id"])
        if old:
            if old.get("_signature") != signature:
                from davinci.product.lifecycle import Conflict

                raise Conflict("Memory operation identifier reused with different content")
            return self._public(old)
        text = " ".join(
            [
                record["request"],
                record["claim"],
                record["attempted_change"],
                " ".join(record["failure_modes"]),
                json.dumps(record["applicability"]),
            ]
        )
        vector = self.embeddings.encode(text)
        doc = {
            **record,
            "_id": record["id"],
            "_signature": signature,
            "search_text": text,
            "exact_hash": digest(record["exact_inputs"])
            if record["exact_inputs"] and record["local_evidence_status"] == "harness_observed"
            else None,
            "embedding_id": self.embeddings.identity if vector is not None else None,
            "embedding": vector,
        }
        if not self.store.insert_experience(doc):
            return self._persist(record, signature)
        return record

    def _base(self, row, identity, source, claim, kind):
        return dict(
            id=identity,
            created_at=now(),
            **self.scope,
            object_id=row["object_id"],
            kind=kind,
            source=source,
            request=row.get("description", row.get("config", {}).get("task", {}).get("description", "")),
            requirements=row.get("plan", {}).get("requirements", []),
            applicability=self.context(row),
            material_inputs=row.get("plan", {}).get("materials", []),
            load_inputs=[c for t in row.get("plan", {}).get("tests", []) for c in t.get("load_cases", [])],
            test_recipes=row.get("plan", {}).get("tests", []),
            claim=claim,
            confidence_basis="Author claim; not independently established",
            origin={**self.scope, "record_id": identity},
        )

    def observe(self, row, result):
        """Private harness projection of a committed result, not a client score submission."""
        current = self._run(row["_id"])
        result = next(r for r in current["results"] if r["id"] == result["id"])
        candidate = next(c for c in current["candidates"] if c["id"] == result["candidate_id"])
        identity = "experience-" + digest({**self.scope, "result": result["id"]})
        source = SourceReference(
            run_id=row["_id"],
            candidate_id=candidate["id"],
            result_id=result["id"],
            test_ids=[t["test_id"] for t in result["tests"]],
        )
        claim = "; ".join(
            t["test_id"] + ": " + t["status"] + " (" + t["reason"] + ")" for t in result["tests"]
        )
        record = self._base(current, identity, source, claim, "observation")
        ids = list(result["artifacts"].values()) + [result["source_artifact"], *row.get("plan_revisions", [])]
        refs = self._refs(ids)
        issues = [
            "Missing artifact metadata: " + identity for identity in set(ids) - {r.artifact_id for r in refs}
        ]
        supported = bool(
            result["evidence_complete"] and result.get("manifest", {}).get("complete") and not issues
        )
        exact = None
        step = self.store.get("artifacts", result["artifacts"].get("model.step", ""))
        src = self.store.get("artifacts", result["source_artifact"])
        capabilities = [a for name, a in result["artifacts"].items() if name.endswith("/capability.json")]
        if supported and step and src and capabilities:
            exact = ExactInputs(
                geometry_sha256=step["sha256"],
                source_sha256=src["sha256"],
                **{k: result[k] for k in ("suite_id", "evaluator_id", "runtime_id", "execution_id")},
                physical_inputs_hash=digest(
                    {
                        k: row["plan"].get(k)
                        for k in ("materials", "interfaces", "assumptions", "requirements", "tests")
                    }
                ),
                numerical_settings_hash=digest({"tests": row["plan"]["tests"], "runtime": row["runtime"]}),
                parameters_hash=digest(candidate["parameters"]),
                solver_observation_hash=digest(
                    [json.loads(self.artifacts.read(a)).get("probe", {}) for a in capabilities]
                ),
            )
        record.update(
            artifacts=refs,
            evidence_issues=issues,
            provenance={
                k: result[k]
                for k in ("suite_id", "evaluator_id", "runtime_id", "execution_id", "candidate_version")
            },
            exact_inputs=exact,
            attempted_change=candidate.get("change", ""),
            measured_outcomes=result["tests"],
            failure_modes=sorted({t["reason"] for t in result["tests"] if t["status"] != "pass"}),
            support="simulation_supported" if supported else "hypothesis",
            local_evidence_status="harness_observed",
            confidence_basis="Committed harness observations at declared screening fidelity; no general design lesson proven"
            if supported
            else "Incomplete execution evidence; failure/diagnostic record only",
        )
        return self._persist(record, digest({"result": result}))

    def note(self, request):
        request = MemoryNote.model_validate(request)
        row = self._run(request.experiment_id)
        source = request.source or SourceReference(run_id=row["_id"])
        if source.run_id != row["_id"]:
            raise ValueError("Note source must belong to its experiment")
        candidates = row.get("candidates", []) if row.get("lifecycle_version") == 2 else []
        if source.candidate_id and not any(c["id"] == source.candidate_id for c in candidates):
            raise ValueError("Unknown candidate reference")
        result = None
        if source.result_id:
            result = next(
                (
                    r
                    for r in row.get("results", [])
                    if r["id"] == source.result_id
                    and (not source.candidate_id or r["candidate_id"] == source.candidate_id)
                ),
                None,
            )
            if not result or not set(source.test_ids) <= {t["test_id"] for t in result["tests"]}:
                raise ValueError("Unknown result/test reference")
        elif source.test_ids:
            if not set(source.test_ids) <= {t["id"] for t in row.get("plan", {}).get("tests", [])}:
                raise ValueError("Unknown test reference")
        tools = []
        for identity in source.tool_ids:
            tool = self.store.get("tools", identity)
            if not tool or tool.get("run_id") != row["_id"] or tool.get("status") != "passed":
                raise ValueError("Tool reference needs passed checks in this source run")
            tools.append(
                {
                    k: tool[k]
                    for k in ("_id", "status", "validation", "checks", "source_commit", "task_version")
                    if k in tool
                }
            )
        identity = "experience-" + digest(
            {**self.scope, "actor": request.actor, "operation": request.operation_id}
        )
        record = self._base(row, identity, source, request.claim, request.kind)
        if request.applicability:
            record["applicability"] = request.applicability
        record["tested_tools"] = tools
        if result:
            record["artifacts"] = self._refs(result["artifacts"].values())
            record["measured_outcomes"] = result["tests"]
        # Linked evidence does not verify the author's causal/generalized claim.
        return self._persist(record, digest(request.model_dump()))

    def legacy_observe(self, row, candidate, evaluation, policy):
        if any(row.get(k) != v for k, v in self.scope.items()):
            return None
        identity = "experience-" + digest({**self.scope, "legacy_candidate": candidate["_id"]})
        record = self._base(
            row,
            identity,
            SourceReference(run_id=row["_id"], candidate_id=candidate["_id"], result_id=evaluation["_id"]),
            policy["lesson"],
            "lesson",
        )
        record.update(
            attempted_change=candidate.get("change", ""),
            measured_outcomes=[evaluation],
            failure_modes=[v["code"] for v in evaluation.get("violations", [])],
            confidence_basis="Legacy reflection is a hypothesis; original screening data linked, no test-first guarantees",
            artifacts=self._refs(candidate.get("artifacts", {}).values()),
        )
        return self._persist(record, digest({"candidate": candidate["_id"], "policy": policy["_id"]}))

    def applicability(self, record, target):
        source = Applicability.model_validate(record["applicability"])
        conflicts, unknown = [], []
        for key in ("domain", "phenomena", "material_models", "materials", "processes", "load_regimes"):
            a, b = getattr(source, key), getattr(target, key)
            if not a or not b:
                unknown.append(key)
            elif a != b if key == "domain" else not set(a) & set(b):
                conflicts.append(key)
        from davinci.product.units import convert

        for name, bound in source.quantities.items():
            required = target.quantities.get(name)
            if required is None:
                unknown.append(name)
                continue
            try:
                low = convert(required.minimum, required.unit, bound.unit, bound.dimension)
                high = convert(required.maximum, required.unit, bound.unit, bound.dimension)
                if low < bound.minimum or high > bound.maximum or required.dimension != bound.dimension:
                    conflicts.append(name)
            except ValueError:
                conflicts.append(name)
        if not source.quantities:
            unknown.append("quantitative_applicability")
        return {
            "status": "incompatible" if conflicts else "needs_review" if unknown else "compatible_metadata",
            "conflicts": conflicts,
            "unknown": unknown,
            "requires_new_validation": True,
        }

    def search(self, request):
        request = MemorySearch.model_validate(request)
        if request.experiment_id:
            metadata = self._run(request.experiment_id).get("opening", {}).get("metadata", {})
            if metadata.get("memory_retrieval") == "disabled":
                return {
                    "version": 1,
                    "items": [],
                    "next_cursor": None,
                    "candidate_count": 0,
                    "candidate_limit": 400,
                    "ranking_scope": "disabled by experiment policy",
                    "vector_status": "disabled",
                    "scope": self.scope,
                    "transfers_acceptance": False,
                }
            allowed = metadata.get("memory_record_ids")
            if allowed is not None:
                # Validate persisted policy and intersect caller narrowing; callers cannot widen it.
                allowed = MemorySearch(query=request.query, record_ids=allowed).record_ids
                request = request.model_copy(
                    update={
                        "record_ids": sorted(set(allowed) & set(request.record_ids))
                        if request.record_ids is not None
                        else allowed
                    }
                )
        target = request.applicability or (
            self.context(self._run(request.experiment_id)) if request.experiment_id else Applicability()
        )
        signature = digest(
            {**request.model_dump(exclude={"cursor"}), **self.scope, "embedding": self.embeddings.identity}
        )
        offset, before = 0, now()
        if request.cursor:
            try:
                cursor = json.loads(base64.urlsafe_b64decode(request.cursor))
                if cursor["signature"] != signature or not 0 <= cursor["offset"] <= 400:
                    raise ValueError("Cursor mismatch")
                offset, before = cursor["offset"], cursor["before"]
            except Exception as exc:
                raise ValueError("Invalid memory cursor") from exc
        terms = list(dict.fromkeys(tokens(request.query)))[:30]
        rows = self.store.experience_page(
            self.scope,
            terms=terms,
            include_superseded=request.include_superseded,
            before=before,
            record_ids=request.record_ids,
        )
        vector = self.embeddings.encode(request.query)
        vector_status = "disabled" if vector is None else "local_hash"
        if vector is not None and self.store.db is not None:
            try:
                hits = self.store.experience_vectors(self.scope, vector, self.embeddings.identity)
                # Preserve Atlas scores; never replace them by a lexical re-sort.
                rows = list(
                    {
                        r["_id"]: r
                        for r in rows + hits
                        if all(r.get(k) == v for k, v in self.scope.items()) and r["created_at"] <= before
                    }.values()
                )
                vector_status = "atlas_vector" if hits else "missing_vectors_lexical_fallback"
            except Exception:
                vector_status = "vector_index_unavailable_lexical_fallback"
        ranked = []
        for row in rows:
            if request.record_ids is not None and row["_id"] not in request.record_ids:
                continue
            if row.get("superseded_by") and not request.include_superseded:
                continue
            match = self.applicability(row, target)
            if match["status"] == "incompatible" and not request.include_incompatible:
                continue
            lexical = len(set(terms) & set(tokens(row["search_text"]))) / max(1, len(terms))
            semantic = row.get("semantic_score")
            if (
                semantic is None
                and vector is not None
                and row.get("embedding_id") == self.embeddings.identity
                and row.get("embedding")
            ):
                try:
                    semantic = self.embeddings.similarity(vector, row["embedding"])
                except (TypeError, ValueError):
                    pass
            quality = (
                0.4
                if row["local_evidence_status"] == "harness_observed" and row["support"] != "hypothesis"
                else 0.05
            )
            if row.get("evidence_issues") or row.get("superseded_by"):
                quality = 0
            score = (
                lexical
                + 0.25 * (semantic or 0)
                + quality
                + (
                    0.2
                    if match["status"] == "compatible_metadata"
                    else -0.8
                    if match["status"] == "incompatible"
                    else 0
                )
            )
            ranked.append(
                {
                    **self._public(row),
                    "applicability_check": match,
                    "ranking": {
                        "score": score,
                        "lexical_overlap": lexical,
                        "index_lexical_score": row.get("lexical_score"),
                        "semantic_score": semantic,
                        "evidence_quality": quality,
                    },
                    "evidence_rechecked": False,
                }
            )
        ranked.sort(key=lambda r: (-r["ranking"]["score"], r["id"]))
        page = ranked[offset : offset + request.limit]
        next_cursor = None
        if offset + request.limit < len(ranked):
            next_cursor = base64.urlsafe_b64encode(
                json.dumps(
                    {"signature": signature, "offset": offset + request.limit, "before": before}
                ).encode()
            ).decode()
        if vector is not None and not any(r["ranking"]["semantic_score"] is not None for r in ranked):
            vector_status = "missing_vectors_lexical_fallback"
        return {
            "version": 1,
            "items": page,
            "next_cursor": next_cursor,
            "candidate_count": len(ranked),
            "candidate_limit": 400,
            "ranking_scope": "bounded indexed candidate window",
            "vector_status": vector_status,
            "scope": self.scope,
            "transfers_acceptance": False,
        }

    def exact(self, inputs):
        inputs = ExactInputs.model_validate(inputs)
        rows = self.store.experience_page(self.scope, exact_hash=digest(inputs.model_dump()))
        valid = []
        for row in rows:
            item = self.get(row["_id"], verify=True)
            if (
                item["local_evidence_status"] == "harness_observed"
                and not item["evidence_issues"]
                and item["exact_inputs"] == inputs.model_dump()
            ):
                valid.append(item)
        return {
            "items": valid,
            "cache_enabled": False,
            "reusable_for_acceptance": False,
            "reason": "Exact evidence inspection only. Reexecution required: full environmental/deterministic equivalence is not established.",
        }

    def supersede(self, identity, command):
        command = Supersession.model_validate(command)
        old = self.get(identity)
        self.get(command.replacement_id)
        if identity == command.replacement_id:
            raise ValueError("An experience cannot supersede itself")
        # Reject cycles; source claims remain preserved and searchable explicitly.
        target = command.replacement_id
        for _ in range(100):
            if target == identity:
                raise ValueError("Supersession cycle")
            target = self.get(target)["superseded_by"]
            if target is None:
                break
        else:
            raise ValueError("Supersession chain too long")
        signature = digest(command.model_dump(exclude={"revision"}))
        raw = self.store.get(COLLECTION, identity)
        if raw.get("_supersession_signature") == signature:
            return old
        if old["superseded_by"]:
            raise ValueError("Already superseded; preserve prior history")
        updated = self.store.update(
            COLLECTION,
            identity,
            {
                "superseded_by": command.replacement_id,
                "supersession_reason": command.reason,
                "_supersession_signature": signature,
                "revision": old["revision"] + 1,
            },
            {**self.scope, "revision": command.revision, "superseded_by": None},
        )
        if not updated:
            from davinci.product.lifecycle import Conflict

            raise Conflict("Memory revision conflict")
        return self._public(updated)

    def export(self, ids, include_artifacts=False):
        records = [self.get(i, verify=True) for i in ids]
        blobs = {}
        size = 0
        if include_artifacts:
            for record in records:
                for ref in record["artifacts"]:
                    if ref["artifact_id"] in blobs:
                        continue
                    size += ref["size"]
                    if size > MAX_BUNDLE // 2:
                        raise ValueError("Portable artifact quota exceeded; export references only")
                    data = self.artifacts.read(ref["artifact_id"])
                    blobs[ref["artifact_id"]] = {**ref, "data_base64": base64.b64encode(data).decode()}
        return MemoryBundle(origin=self.scope, records=records, artifacts=list(blobs.values())).model_dump()

    def import_bundle(self, command):
        command = MemoryImport.model_validate(command)
        payload = command.model_dump()
        if len(json.dumps(payload).encode()) > MAX_BUNDLE:
            raise ValueError("Memory import exceeds 16 MB")
        signature = digest(payload)
        operation = "memory-import-" + digest(
            {**self.scope, "actor": command.actor, "operation": command.operation_id}
        )
        self.store.insert(
            "memory_operations_v1", {"_id": operation, "signature": signature, "status": "pending"}
        )
        previous = self.store.get("memory_operations_v1", operation)
        if previous["signature"] != signature:
            from davinci.product.lifecycle import Conflict

            raise Conflict("Memory import operation reused with different content")
        if previous.get("status") == "completed":
            return previous["result"]
        verified = {}
        for blob in command.bundle.artifacts:
            try:
                data = base64.b64decode(blob.data_base64, validate=True)
                if (
                    len(data) != blob.size
                    or hashlib.sha256(data).hexdigest() != blob.sha256
                    or blob.artifact_id != "artifact-" + blob.sha256
                ):
                    raise ValueError("Imported artifact checksum mismatch")
                verified[blob.artifact_id] = (blob, data)
            except Exception as exc:
                raise ValueError("Invalid imported artifact content") from exc
        for blob, data in verified.values():
            self.artifacts.put(data, blob.name, blob.media_type)
        mapping = {
            r.id: "experience-" + digest({"operation": operation, "origin": r.id})
            for r in command.bundle.records
        }
        if len(mapping) != len(command.bundle.records):
            raise ValueError("Duplicate imported record identity")
        imported = []
        for item in command.bundle.records:
            record = item.model_dump()
            issues = list(record["evidence_issues"])
            if item.superseded_by and item.superseded_by not in mapping:
                issues.append("Unresolved origin supersession reference: " + item.superseded_by)
            for ref in item.artifacts:
                blob = verified.get(ref.artifact_id)
                if not blob or blob[0].sha256 != ref.sha256 or blob[0].size != ref.size:
                    issues.append("Missing or invalid portable artifact: " + ref.artifact_id)
            record.update(
                id=mapping[item.id],
                **self.scope,
                created_at=now(),
                revision=0,
                local_evidence_status="imported_unverified",
                evidence_issues=sorted(set(issues)),
                superseded_by=mapping.get(item.superseded_by, item.superseded_by),
                import_history=[
                    *item.import_history,
                    {
                        "from": command.bundle.origin,
                        "source_id": item.id,
                        "destination": self.scope,
                        "actor": command.actor,
                        "operation_id": command.operation_id,
                        "source_evidence_status": item.local_evidence_status,
                    },
                ],
                confidence_basis=item.confidence_basis
                + " | Imported claim: not locally reproduced or authenticated",
            )
            imported.append(self._persist(record, signature))
        result = {"items": imported, "locally_reproduced": False, "cache_enabled": False}
        self.store.update(
            "memory_operations_v1",
            operation,
            {"status": "completed", "result": result},
            {"signature": signature},
        )
        return result

    def reindex(self, after_id=""):
        rows = self.store.experience_page(self.scope, limit=101, after_id=after_id)
        for row in rows[:100]:
            vector = self.embeddings.encode(row["search_text"])
            self.store.update(
                COLLECTION,
                row["_id"],
                {
                    "embedding": vector,
                    "embedding_id": self.embeddings.identity if vector is not None else None,
                },
                self.scope,
            )
        return {
            "processed": min(100, len(rows)),
            "next_cursor": rows[99]["_id"] if len(rows) > 100 else None,
            "embedding": self.embeddings.settings.model_dump(),
            "cost_usd": 0,
            "downloads": False,
        }
