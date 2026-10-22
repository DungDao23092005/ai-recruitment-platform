"""Guards for Alembic revision identifiers and the migration graph.

Alembic stores the applied revision in ``alembic_version.version_num``, which is
``VARCHAR(32)``. A longer identifier only fails when ``alembic upgrade`` runs,
so these checks fail fast in CI instead. The graph assertions also catch
duplicate identifiers, missing parents, cycles and multiple heads.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"
_ALEMBIC_DIR = _BACKEND_DIR / "alembic"

_MAX_REVISION_LENGTH = 32
_EXPECTED_BASE = "0001_initial_schema"
_EXPECTED_HEAD = "add_resume_confirmation"


def _parents(down_revision) -> tuple[str, ...]:
    if down_revision is None:
        return ()
    if isinstance(down_revision, str):
        return (down_revision,)
    return tuple(down_revision)


def _script_directory() -> ScriptDirectory:
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", str(_ALEMBIC_DIR))
    return ScriptDirectory.from_config(config)


def _revisions():
    # walk_revisions raises Alembic's CommandError/CycleDetected when the graph
    # is broken, so materialising this list is itself a graph check.
    return list(_script_directory().walk_revisions())


def test_revision_ids_fit_alembic_version_column():
    for revision in _revisions():
        assert len(revision.revision) <= _MAX_REVISION_LENGTH, (
            f"revision {revision.revision!r} exceeds "
            f"{_MAX_REVISION_LENGTH} characters"
        )
        for parent in _parents(revision.down_revision):
            assert len(parent) <= _MAX_REVISION_LENGTH, (
                f"down_revision {parent!r} of {revision.revision!r} exceeds "
                f"{_MAX_REVISION_LENGTH} characters"
            )


def test_revision_ids_are_unique():
    identifiers = [revision.revision for revision in _revisions()]
    assert len(identifiers) == len(set(identifiers))


def test_every_referenced_parent_exists():
    revisions = _revisions()
    identifiers = {revision.revision for revision in revisions}
    for revision in revisions:
        for parent in _parents(revision.down_revision):
            assert parent in identifiers, (
                f"{revision.revision!r} references missing parent {parent!r}"
            )


def test_graph_has_single_root_and_expected_head():
    script = _script_directory()

    assert tuple(script.get_bases()) == (_EXPECTED_BASE,)
    assert tuple(script.get_heads()) == (_EXPECTED_HEAD,)

    head = script.get_revision(_EXPECTED_HEAD)
    assert head is not None
    assert _parents(head.down_revision) == ("add_match_explain_idempotency",)

    previous_head = script.get_revision("add_match_explain_idempotency")
    assert previous_head is not None
    assert _parents(previous_head.down_revision) == (
        "add_interview_eval_uniqueness",
    )

    evaluator_revision = script.get_revision("add_interview_eval_uniqueness")
    assert evaluator_revision is not None
    assert _parents(evaluator_revision.down_revision) == (
        "add_hiring_pipeline_tables",
    )
