from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "company_free_subscription.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "company_free_subscription", _MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


company_free_migration = _load_migration()


def test_downgrade_preflight_blocks_when_company_free_plans_exist():
    mock_bind = MagicMock(spec=sa.engine.Connection)

    # First scalar_one() call is for _count_company_free_plans
    mock_bind.execute.return_value.scalar_one.return_value = 2

    with patch.object(company_free_migration.op, "get_bind", return_value=mock_bind), \
         patch.object(company_free_migration.op, "drop_constraint") as mock_drop_constraint, \
         patch.object(company_free_migration.op, "drop_index") as mock_drop_index, \
         patch.object(company_free_migration.op, "create_check_constraint") as mock_create_constraint:

        with pytest.raises(RuntimeError) as exc_info:
            company_free_migration.downgrade()

        assert "Cannot downgrade wave1_5_company_free" in str(exc_info.value)
        assert "2 Company Free plan row(s) exist" in str(exc_info.value)

        # Proves zero DDL was executed
        mock_drop_constraint.assert_not_called()
        mock_drop_index.assert_not_called()
        mock_create_constraint.assert_not_called()


def test_downgrade_preflight_blocks_when_company_free_subscriptions_exist():
    mock_bind = MagicMock(spec=sa.engine.Connection)

    # _count_company_free_plans returns 0, _count_company_free_subscriptions returns 1
    mock_bind.execute.return_value.scalar_one.side_effect = [0, 1]

    with patch.object(company_free_migration.op, "get_bind", return_value=mock_bind), \
         patch.object(company_free_migration.op, "drop_constraint") as mock_drop_constraint, \
         patch.object(company_free_migration.op, "drop_index") as mock_drop_index, \
         patch.object(company_free_migration.op, "create_check_constraint") as mock_create_constraint:

        with pytest.raises(RuntimeError) as exc_info:
            company_free_migration.downgrade()

        assert "Cannot downgrade wave1_5_company_free" in str(exc_info.value)
        assert "1 Company Free subscription row(s) exist" in str(exc_info.value)

        # Proves zero DDL was executed
        mock_drop_constraint.assert_not_called()
        mock_drop_index.assert_not_called()
        mock_create_constraint.assert_not_called()


def test_downgrade_proceeds_when_no_company_free_rows_exist():
    mock_bind = MagicMock(spec=sa.engine.Connection)

    # Both count queries return 0
    mock_bind.execute.return_value.scalar_one.side_effect = [0, 0]
    # Check if index and constraints exist:
    # 1. new index exists (drop)
    # 2. new subscription constraint exists (drop)
    # 3. old subscription constraint does not exist (re-create)
    # 4. new plan constraint exists (drop)
    # 5. old plan constraint does not exist (re-create)
    mock_bind.execute.return_value.scalar.side_effect = [1, 1, None, 1, None]

    with patch.object(company_free_migration.op, "get_bind", return_value=mock_bind), \
         patch.object(company_free_migration.op, "drop_constraint") as mock_drop_constraint, \
         patch.object(company_free_migration.op, "drop_index") as mock_drop_index, \
         patch.object(company_free_migration.op, "create_check_constraint") as mock_create_constraint:

        company_free_migration.downgrade()

        # DDL is executed only when preflight passes
        mock_drop_index.assert_called_once_with(
            company_free_migration.COMPANY_FREE_INDEX,
            table_name="recruitment_plans",
        )
        assert mock_drop_constraint.call_count >= 1
        assert mock_create_constraint.call_count >= 1
