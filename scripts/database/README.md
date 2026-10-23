# SQL Server backup, restore drill, and Qdrant reindex

These are manual operations. Nothing here is called by application startup,
tests, or deployment tooling.

## Safety model

- The backup script writes a `COPY_ONLY` backup, runs `RESTORE VERIFYONLY`, and
  compares SHA-256 hashes between the container and host before writing a
  sidecar.
- The restore script only restores into a **new, isolated** database. It rejects
  system databases, the active `DATABASE_NAME`, explicit protected databases,
  and any target that already exists. It never uses `REPLACE` and never drops a
  database.
- The Qdrant reindex CLI is dry-run by default. It never creates, recreates, or
  deletes a collection or point. Writes require `--execute`.
- A host-local backup is not disaster recovery. Copy backups to independent
  storage and test restores outside this host.

## SQL Server backup

```powershell
.\scripts\database\backup_mssql.ps1 `
  -BackupDirectory 'D:\backups\ai-recruitment-platform\mssql'
```

Artifacts:

- `<database>_<UTC timestamp>.bak`
- `<database>_<UTC timestamp>.bak.sha256`

Details:

- The backup is written under `/tmp` in the `recruitment_mssql` container, not
  into the MSSQL data volume, and is removed after the copy.
- Database, login, and password default to `.env`
  (`DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD` / `MSSQL_SA_PASSWORD`).
- Old backups are never pruned automatically.
- `-DryRun` prints the planned paths without creating directories, contacting
  Docker, running SQL, or writing files.

## Restore drill

Always start with a dry run:

```powershell
.\scripts\database\restore_mssql.ps1 `
  -BackupPath 'D:\backups\ai-recruitment-platform\mssql\<file>.bak' `
  -TargetDatabase 'ai_recruitment_platform_restore_drill_20261023' `
  -DryRun
```

The dry run:

1. Finds and verifies the sidecar checksum when present.
2. Copies the backup into the container and re-checks SHA-256.
3. Runs `RESTORE VERIFYONLY` and `RESTORE FILELISTONLY`.
4. Checks the target database name and physical filenames for collisions.
5. Prints the generated `MOVE` plan, then stops.

The real restore is intentionally manual and requires an isolated target:

```powershell
.\scripts\database\restore_mssql.ps1 `
  -BackupPath 'D:\backups\ai-recruitment-platform\mssql\<file>.bak' `
  -TargetDatabase 'ai_recruitment_platform_restore_drill_20261023'
```

The script restores the database, runs `DBCC CHECKDB`, checks `ONLINE` state,
and probes `dbo.users`, `dbo.jobs`, `dbo.resumes`, and
`dbo.knowledge_documents`. It leaves the restored database in place for
inspection; dropping it is a separate, explicit owner action.

Exit codes: `0` success/dry-run, `1` unexpected, `2` usage/target guard, `3`
I/O/Docker, `4` checksum, `5` verify/filelist, `6` restore, `7` validation.

## Qdrant reindex

Run from `backend/` with the project virtual environment. Dry-run is the
default:

```powershell
$env:DATABASE_HOST = '127.0.0.1'
.\.venv\Scripts\python.exe -m scripts.reindex_qdrant --dry-run
```

Writing vectors requires an explicit `--execute`:

```powershell
$env:DATABASE_HOST = '127.0.0.1'
.\.venv\Scripts\python.exe -m scripts.reindex_qdrant --collection jobs --execute
```

Use `--collection resumes jobs knowledge` or `--collection all` to select
collections. `--batch-size` defaults to `50`.

What is rebuilt:

- `resumes`: confirmed primary, non-deleted resumes of active candidates, via
  `AIMatchingService._reindex_resume`.
- `jobs`: all non-deleted jobs (draft + published), via
  `JobService._reindex_job`.
- `knowledge`: published, non-deleted `knowledge_documents` rows, using the
  same chunker and embedding service as `scripts.seed_knowledge.py`.

Important behaviour:

- Collection presence and vector dimension `384` are checked before any write.
  A missing collection is an error; the CLI does not create it.
- Existing points are not deleted. Legacy knowledge points with random ids
  remain alongside the deterministic new ids.
- Jobs and knowledge may have more Qdrant points than SQL source rows. This CLI
  does not reconcile or delete orphan points.
- The development database currently has zero `knowledge_documents` rows.
  Rebuilding knowledge from the committed Markdown corpus is a separate
  seeding operation, not this CLI.
- The local backend container is built from an image without a bind mount, so a
  new host-side script is not visible inside `recruitment_backend` until the
  image is rebuilt or the code is copied in.

## Verification

```powershell
Invoke-Pester -Script .\scripts\database\tests -PassThru
```

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/unit/scripts/test_reindex_qdrant.py -q
```
