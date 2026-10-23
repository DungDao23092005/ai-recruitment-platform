<#
.SYNOPSIS
    Restores a SQL Server backup into a NEW, isolated database after safety
    checks, then validates it with DBCC CHECKDB and schema/data probes.

.DESCRIPTION
    Safety model:
      * The target database is mandatory and must be a new database.
      * The active application database (DATABASE_NAME from .env), system
        databases, and any explicitly protected database are rejected.
      * Any target that already exists on the server is rejected. The script
        never uses WITH REPLACE and never drops or overwrites a database.
      * The backup file must exist. If a .sha256 sidecar is present (the backup
        script creates one), it is verified before any restore.
      * The backup is copied into the container, its SHA-256 is re-checked, and
        RESTORE VERIFYONLY is run before RESTORE DATABASE.
      * Logical file names are read from RESTORE FILELISTONLY; target physical
        files are derived from the target database name and the server's
        default data/log directories.
      * After restore, DBCC CHECKDB and key table probes must succeed.

    The script never runs automatically and is not called by application
    startup, tests, or deployment tooling.

.PARAMETER BackupPath
    Host path to the .bak file.

.PARAMETER TargetDatabase
    New, isolated database name to create. Must match [A-Za-z0-9_]{1,100}.

.PARAMETER ChecksumFile
    Optional path to a .sha256 sidecar. Defaults to "$BackupPath.sha256".
    If the file is absent and this parameter was not explicitly supplied, the
    restore continues with a warning after RESTORE VERIFYONLY. If explicitly
    supplied, a missing checksum file is a hard failure.

.PARAMETER DryRun
    Performs the full preflight: checksum, copy, hash comparison, RESTORE
    VERIFYONLY, RESTORE FILELISTONLY, target/file collision checks. It does NOT
    execute RESTORE DATABASE, DBCC CHECKDB, or create a database.

.EXAMPLE
    .\scripts\database\restore_mssql.ps1 `
        -BackupPath D:\backups\ai-recruitment-platform\mssql\ai_recruitment_platform_20260101T000000000Z.bak `
        -TargetDatabase ai_recruitment_platform_restore_drill `
        -DryRun

.EXAMPLE
    # Run only after the owner confirms an isolated drill environment.
    .\scripts\database\restore_mssql.ps1 `
        -BackupPath D:\backups\ai-recruitment-platform\mssql\ai_recruitment_platform_20260101T000000000Z.bak `
        -TargetDatabase ai_recruitment_platform_restore_drill

.NOTES
    Exit codes:
      0  success (or successful dry run)
      1  unexpected failure
      2  usage/target guard rejected the request
      3  I/O, Docker, or container command failure
      4  checksum mismatch
      5  RESTORE VERIFYONLY failed
      6  RESTORE DATABASE failed
      7  post-restore validation failed
#>

[CmdletBinding()]
param(
    [string]$BackupPath = '',
    [string]$TargetDatabase = '',
    [string]$ContainerName = 'recruitment_mssql',
    [string]$EnvFile = '',
    [string]$SqlUser = '',
    [string]$SqlPassword = '',
    [string]$SqlToolsPath = '/opt/mssql-tools18/bin/sqlcmd',
    [string]$ChecksumFile = '',
    [string[]]$ProtectedDatabases = @(),
    [string]$TargetDataDirectory = '',
    [string]$TargetLogDirectory = '',
    [int]$FileNumber = 1,
    [switch]$DryRun,
    [switch]$NoRun
)

$ErrorActionPreference = 'Stop'

function Write-Log {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [ValidateSet('INFO', 'WARN', 'ERROR')][string]$Level = 'INFO'
    )
    $timestamp = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    Write-Host "[$timestamp] [$Level] $Message"
}

function Throw-RestoreError {
    param(
        [Parameter(Mandatory = $true)][int]$Code,
        [Parameter(Mandatory = $true)][string]$Message
    )
    $exception = New-Object System.Exception($Message)
    $exception.Data['ExitCode'] = $Code
    throw $exception
}

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Key
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith('#')) {
            continue
        }
        $separator = $trimmed.IndexOf('=')
        if ($separator -lt 1) {
            continue
        }
        $candidateKey = $trimmed.Substring(0, $separator).Trim()
        if ($candidateKey -ne $Key) {
            continue
        }
        $value = $trimmed.Substring($separator + 1).Trim()
        if ($value.Length -ge 2) {
            $first = $value.Substring(0, 1)
            $last = $value.Substring($value.Length - 1, 1)
            if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
        return $value
    }
    return $null
}

function Assert-DatabaseIdentifier {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ($Value -notmatch '^[A-Za-z0-9_]{1,100}$') {
        Throw-RestoreError -Code 2 -Message 'Database name must be 1-100 characters of letters, digits or underscore.'
    }
}

function Assert-SafeRestoreTarget {
    param(
        [Parameter(Mandatory = $true)][string]$TargetDatabase,
        [string[]]$ProtectedDatabases = @(),
        [string[]]$ExistingDatabases = @()
    )
    if ([string]::IsNullOrWhiteSpace($TargetDatabase)) {
        Throw-RestoreError -Code 2 -Message 'TargetDatabase is required.'
    }
    if ($TargetDatabase -notmatch '^[A-Za-z0-9_]{1,100}$') {
        Throw-RestoreError -Code 2 -Message 'TargetDatabase must be 1-100 characters of letters, digits or underscore.'
    }

    $normalizedTarget = $TargetDatabase.ToLowerInvariant()
    $systemDatabases = @('master', 'model', 'msdb', 'tempdb')
    $protected = @($systemDatabases + @($ProtectedDatabases)) |
        Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } |
        ForEach-Object { ([string]$_).ToLowerInvariant() }
    if ($protected -contains $normalizedTarget) {
        Throw-RestoreError -Code 2 -Message "Refusing to restore over protected/active database '$TargetDatabase'."
    }

    $existing = @($ExistingDatabases) |
        Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } |
        ForEach-Object { ([string]$_).ToLowerInvariant() }
    if ($existing -contains $normalizedTarget) {
        Throw-RestoreError -Code 2 -Message "Target database '$TargetDatabase' already exists. The script never drops or overwrites a database."
    }
}

function Read-ChecksumSidecar {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Checksum file does not exist: $Path"
    }
    $text = Get-Content -LiteralPath $Path -Raw
    if ([string]::IsNullOrWhiteSpace($text)) {
        throw "Checksum file is empty: $Path"
    }
    $firstLine = ($text -split "`r?`n")[0].Trim()
    if ([string]::IsNullOrWhiteSpace($firstLine)) {
        throw "Checksum file has no hash line: $Path"
    }
    $parts = $firstLine -split '\s+'
    $hash = $parts[0]
    if ($hash -notmatch '^[A-Fa-f0-9]{64}$') {
        throw "Checksum file does not contain a valid SHA-256 hash: $Path"
    }
    $fileName = $null
    if ($parts.Count -ge 2) {
        $fileName = $parts[1].TrimStart('*')
    }
    return [pscustomobject]@{
        Hash     = $hash.ToLowerInvariant()
        FileName = $fileName
    }
}

function Test-FileChecksum {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string]$ExpectedHash
    )
    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        return $false
    }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $FilePath).Hash.ToLowerInvariant()
    return $actual -eq $ExpectedHash.ToLowerInvariant()
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @()
    )
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $allOutput = & $FilePath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    return [pscustomobject]@{
        Output   = @($allOutput)
        ExitCode = $exitCode
    }
}

function Invoke-SqlCmd {
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [Parameter(Mandatory = $true)][string]$SqlUser,
        [string]$SqlPassword = '',
        [Parameter(Mandatory = $true)][string]$Query,
        [string]$Database = '',
        [string]$Separator = '',
        [string]$SqlToolsPath = '/opt/mssql-tools18/bin/sqlcmd'
    )
    $arguments = New-Object System.Collections.Generic.List[string]
    $arguments.Add('exec')
    if (-not [string]::IsNullOrEmpty($SqlPassword)) {
        $arguments.Add('-e')
        $arguments.Add("SQLCMDPASSWORD=$SqlPassword")
    }
    $arguments.Add($ContainerName)
    $arguments.Add($SqlToolsPath)
    foreach ($item in @('-S', 'localhost', '-U', $SqlUser, '-C', '-b', '-r1', '-h', '-1', '-W')) {
        $arguments.Add($item)
    }
    if (-not [string]::IsNullOrEmpty($Separator)) {
        $arguments.Add('-s')
        $arguments.Add($Separator)
    }
    if (-not [string]::IsNullOrEmpty($Database)) {
        $arguments.Add('-d')
        $arguments.Add($Database)
    }
    $arguments.Add('-Q')
    $arguments.Add($Query)
    return Invoke-NativeCommand -FilePath 'docker' -Arguments $arguments.ToArray()
}

function Write-CommandOutput {
    param([object[]]$Output)
    foreach ($line in @($Output)) {
        if ($null -ne $line -and -not [string]::IsNullOrWhiteSpace([string]$line)) {
            Write-Log ([string]$line)
        }
    }
}

function Test-ContainerRunning {
    param([Parameter(Mandatory = $true)][string]$ContainerName)
    $result = Invoke-NativeCommand -FilePath 'docker' -Arguments @(
        'inspect', '-f', '{{.State.Running}}', $ContainerName
    )
    if ($result.ExitCode -ne 0) {
        return $false
    }
    return (@($result.Output | ForEach-Object { ([string]$_).Trim() }) -contains 'true')
}

function ConvertFrom-RestoreFileList {
    param([string[]]$Lines)
    $files = New-Object System.Collections.Generic.List[object]
    foreach ($rawLine in @($Lines)) {
        $text = [string]$rawLine
        if (-not $text.Contains('|')) {
            continue
        }
        $parts = $text.Split('|')
        if ($parts.Count -lt 3) {
            continue
        }
        $fileType = $parts[2].Trim()
        if ($fileType -ne 'D' -and $fileType -ne 'L') {
            continue
        }
        $logicalName = $parts[0].Trim()
        $physicalName = $parts[1].Trim()
        if ([string]::IsNullOrWhiteSpace($logicalName) -or [string]::IsNullOrWhiteSpace($physicalName)) {
            continue
        }
        $files.Add([pscustomobject]@{
            LogicalName  = $logicalName
            PhysicalName = $physicalName
            FileType     = $fileType
        })
    }
    if ($files.Count -eq 0) {
        throw 'RESTORE FILELISTONLY returned no data/log files.'
    }
    return $files.ToArray()
}

function Join-ContainerPath {
    param(
        [Parameter(Mandatory = $true)][string]$Directory,
        [Parameter(Mandatory = $true)][string]$FileName
    )
    if ([string]::IsNullOrWhiteSpace($Directory)) {
        throw 'Container directory cannot be empty.'
    }
    return ($Directory.TrimEnd('/') + '/' + $FileName)
}

function New-RestoreMovePlan {
    param(
        [Parameter(Mandatory = $true)][object[]]$Files,
        [Parameter(Mandatory = $true)][string]$TargetDatabase,
        [Parameter(Mandatory = $true)][string]$DataDirectory,
        [Parameter(Mandatory = $true)][string]$LogDirectory
    )
    $dataFiles = @($Files | Where-Object { $_.FileType -eq 'D' })
    $logFiles = @($Files | Where-Object { $_.FileType -eq 'L' })
    if ($dataFiles.Count -eq 0) {
        throw 'Backup contains no data files (type D).'
    }
    if ($logFiles.Count -eq 0) {
        throw 'Backup contains no transaction log files (type L).'
    }

    $moves = New-Object System.Collections.Generic.List[string]
    $targetFiles = New-Object System.Collections.Generic.List[string]

    $index = 0
    foreach ($file in $dataFiles) {
        $index++
        $fileName = if ($index -eq 1) { "$TargetDatabase.mdf" } else { "${TargetDatabase}_$index.ndf" }
        $targetPath = Join-ContainerPath -Directory $DataDirectory -FileName $fileName
        $logical = ([string]$file.LogicalName).Replace("'", "''")
        $moves.Add("MOVE N'$logical' TO N'$targetPath'")
        $targetFiles.Add($targetPath)
    }

    $index = 0
    foreach ($file in $logFiles) {
        $index++
        $fileName = if ($index -eq 1) { "${TargetDatabase}_log.ldf" } else { "${TargetDatabase}_log$index.ldf" }
        $targetPath = Join-ContainerPath -Directory $LogDirectory -FileName $fileName
        $logical = ([string]$file.LogicalName).Replace("'", "''")
        $moves.Add("MOVE N'$logical' TO N'$targetPath'")
        $targetFiles.Add($targetPath)
    }

    $uniqueTargets = @($targetFiles | ForEach-Object { ([string]$_).ToLowerInvariant() } | Select-Object -Unique)
    if ($uniqueTargets.Count -ne $targetFiles.Count) {
        throw 'Generated restore target paths are not unique.'
    }

    return [pscustomobject]@{
        Moves       = $moves.ToArray()
        TargetFiles = $targetFiles.ToArray()
    }
}

function Get-ContainerSha256 {
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [Parameter(Mandatory = $true)][string]$ContainerPath
    )
    $result = Invoke-NativeCommand -FilePath 'docker' -Arguments @(
        'exec', $ContainerName, 'sha256sum', $ContainerPath
    )
    if ($result.ExitCode -ne 0) {
        Write-CommandOutput -Output $result.Output
        Throw-RestoreError -Code 3 -Message 'Could not compute the backup SHA-256 inside the container.'
    }
    $hashLine = @(
        $result.Output |
            Where-Object { ([string]$_) -match '^[A-Fa-f0-9]{64}\s' } |
            Select-Object -First 1
    )
    if ($hashLine.Count -eq 0) {
        Throw-RestoreError -Code 3 -Message 'Could not parse the container SHA-256 output.'
    }
    return (([string]$hashLine[0]) -split '\s+')[0].ToLowerInvariant()
}

function Invoke-RestoreMain {
    $containerTemp = $null
    try {
        if ([string]::IsNullOrWhiteSpace($BackupPath)) {
            Throw-RestoreError -Code 2 -Message 'BackupPath is required.'
        }
        if ([string]::IsNullOrWhiteSpace($TargetDatabase)) {
            Throw-RestoreError -Code 2 -Message 'TargetDatabase is required.'
        }
        Assert-DatabaseIdentifier -Value $TargetDatabase

        $resolvedBackup = @(Resolve-Path -LiteralPath $BackupPath -ErrorAction SilentlyContinue)
        if ($resolvedBackup.Count -eq 0) {
            Throw-RestoreError -Code 3 -Message "Backup file does not exist: $BackupPath"
        }
        $hostBackupPath = $resolvedBackup[0].ProviderPath
        if (-not (Test-Path -LiteralPath $hostBackupPath -PathType Leaf)) {
            Throw-RestoreError -Code 3 -Message "Backup path is not a file: $hostBackupPath"
        }

        $repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).ProviderPath
        if ([string]::IsNullOrWhiteSpace($EnvFile)) {
            $EnvFile = Join-Path $repoRoot '.env'
        }

        $activeDatabase = Get-DotEnvValue -Path $EnvFile -Key 'DATABASE_NAME'
        if ([string]::IsNullOrWhiteSpace($SqlUser)) {
            $SqlUser = Get-DotEnvValue -Path $EnvFile -Key 'DATABASE_USER'
        }
        if ([string]::IsNullOrWhiteSpace($SqlUser)) {
            $SqlUser = 'sa'
        }
        if ([string]::IsNullOrWhiteSpace($SqlPassword)) {
            $SqlPassword = Get-DotEnvValue -Path $EnvFile -Key 'DATABASE_PASSWORD'
        }
        if ([string]::IsNullOrWhiteSpace($SqlPassword)) {
            $SqlPassword = Get-DotEnvValue -Path $EnvFile -Key 'MSSQL_SA_PASSWORD'
        }

        $protected = @($ProtectedDatabases)
        if (-not [string]::IsNullOrWhiteSpace($activeDatabase)) {
            $protected += $activeDatabase
        }

        $checksumExplicit = -not [string]::IsNullOrWhiteSpace($ChecksumFile)
        if (-not $checksumExplicit) {
            $ChecksumFile = "$hostBackupPath.sha256"
        }
        $hostHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $hostBackupPath).Hash.ToLowerInvariant()

        if (Test-Path -LiteralPath $ChecksumFile -PathType Leaf) {
            $checksum = Read-ChecksumSidecar -Path $ChecksumFile
            if (-not (Test-FileChecksum -FilePath $hostBackupPath -ExpectedHash $checksum.Hash)) {
                Throw-RestoreError -Code 4 -Message "Checksum mismatch for $hostBackupPath (sidecar $ChecksumFile)."
            }
            Write-Log "Checksum verified: $hostHash"
        }
        elseif ($checksumExplicit) {
            Throw-RestoreError -Code 4 -Message "Checksum file was explicitly supplied but does not exist: $ChecksumFile"
        }
        else {
            Write-Log 'WARNING: no .sha256 sidecar found. Continuing after RESTORE VERIFYONLY; checksum provenance is not proven.' -Level WARN
        }

        if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
            Throw-RestoreError -Code 3 -Message 'The docker CLI is not available on PATH.'
        }
        if (-not (Test-ContainerRunning -ContainerName $ContainerName)) {
            Throw-RestoreError -Code 3 -Message "SQL Server container '$ContainerName' is not running."
        }
        $toolsCheck = Invoke-NativeCommand -FilePath 'docker' -Arguments @(
            'exec', $ContainerName, 'test', '-x', $SqlToolsPath
        )
        if ($toolsCheck.ExitCode -ne 0) {
            Throw-RestoreError -Code 3 -Message "sqlcmd was not found in the container at $SqlToolsPath."
        }
        if ([string]::IsNullOrWhiteSpace($SqlPassword)) {
            Throw-RestoreError -Code 3 -Message 'No SQL password was supplied or found in DATABASE_PASSWORD/MSSQL_SA_PASSWORD.'
        }

        $databasesResult = Invoke-SqlCmd `
            -ContainerName $ContainerName `
            -SqlUser $SqlUser `
            -SqlPassword $SqlPassword `
            -SqlToolsPath $SqlToolsPath `
            -Query 'SET NOCOUNT ON; SELECT name FROM sys.databases ORDER BY name;'
        if ($databasesResult.ExitCode -ne 0) {
            Write-CommandOutput -Output $databasesResult.Output
            Throw-RestoreError -Code 3 -Message 'Could not list SQL Server databases.'
        }
        $existingDatabases = @(
            $databasesResult.Output |
                ForEach-Object { ([string]$_).Trim() } |
                Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        )
        Assert-SafeRestoreTarget `
            -TargetDatabase $TargetDatabase `
            -ProtectedDatabases $protected `
            -ExistingDatabases $existingDatabases

        $containerTemp = "/tmp/ai-recruitment-restore-$([Guid]::NewGuid().ToString('N')).bak"
        Write-Log "Copying backup into container temporary path: $containerTemp"
        $copyResult = Invoke-NativeCommand -FilePath 'docker' -Arguments @(
            'cp', $hostBackupPath, "${ContainerName}:$containerTemp"
        )
        if ($copyResult.ExitCode -ne 0) {
            Write-CommandOutput -Output $copyResult.Output
            Throw-RestoreError -Code 3 -Message "docker cp failed with exit code $($copyResult.ExitCode)."
        }

        $containerHash = Get-ContainerSha256 -ContainerName $ContainerName -ContainerPath $containerTemp
        if ($containerHash -ne $hostHash) {
            Throw-RestoreError -Code 4 -Message 'Backup SHA-256 changed while copying into the container.'
        }

        Write-Log 'Running RESTORE VERIFYONLY WITH CHECKSUM ...'
        $verifyResult = Invoke-SqlCmd `
            -ContainerName $ContainerName `
            -SqlUser $SqlUser `
            -SqlPassword $SqlPassword `
            -SqlToolsPath $SqlToolsPath `
            -Query "RESTORE VERIFYONLY FROM DISK = N'$containerTemp' WITH FILE = $FileNumber, CHECKSUM;"
        Write-CommandOutput -Output $verifyResult.Output
        if ($verifyResult.ExitCode -ne 0) {
            Throw-RestoreError -Code 5 -Message 'RESTORE VERIFYONLY failed; the backup is not restored.'
        }

        Write-Log 'Reading logical file names with RESTORE FILELISTONLY ...'
        $fileListResult = Invoke-SqlCmd `
            -ContainerName $ContainerName `
            -SqlUser $SqlUser `
            -SqlPassword $SqlPassword `
            -SqlToolsPath $SqlToolsPath `
            -Separator '|' `
            -Query "RESTORE FILELISTONLY FROM DISK = N'$containerTemp' WITH FILE = $FileNumber;"
        if ($fileListResult.ExitCode -ne 0) {
            Write-CommandOutput -Output $fileListResult.Output
            Throw-RestoreError -Code 5 -Message 'RESTORE FILELISTONLY failed.'
        }
        $backupFiles = @(ConvertFrom-RestoreFileList -Lines $fileListResult.Output)

        if ([string]::IsNullOrWhiteSpace($TargetDataDirectory) -or [string]::IsNullOrWhiteSpace($TargetLogDirectory)) {
            $pathResult = Invoke-SqlCmd `
                -ContainerName $ContainerName `
                -SqlUser $SqlUser `
                -SqlPassword $SqlPassword `
                -SqlToolsPath $SqlToolsPath `
                -Query "SET NOCOUNT ON; SELECT CAST(SERVERPROPERTY('InstanceDefaultDataPath') AS nvarchar(4000)); SELECT CAST(SERVERPROPERTY('InstanceDefaultLogPath') AS nvarchar(4000));"
            if ($pathResult.ExitCode -ne 0) {
                Write-CommandOutput -Output $pathResult.Output
                Throw-RestoreError -Code 3 -Message 'Could not read SQL Server default data/log directories.'
            }
            $pathLines = @(
                $pathResult.Output |
                    ForEach-Object { ([string]$_).Trim() } |
                    Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
            )
            if ($pathLines.Count -lt 2) {
                Throw-RestoreError -Code 3 -Message 'SQL Server did not return both default data and log directories.'
            }
            if ([string]::IsNullOrWhiteSpace($TargetDataDirectory)) {
                $TargetDataDirectory = $pathLines[0]
            }
            if ([string]::IsNullOrWhiteSpace($TargetLogDirectory)) {
                $TargetLogDirectory = $pathLines[1]
            }
        }

        $movePlan = New-RestoreMovePlan `
            -Files $backupFiles `
            -TargetDatabase $TargetDatabase `
            -DataDirectory $TargetDataDirectory `
            -LogDirectory $TargetLogDirectory

        $stillMissingResult = Invoke-SqlCmd `
            -ContainerName $ContainerName `
            -SqlUser $SqlUser `
            -SqlPassword $SqlPassword `
            -SqlToolsPath $SqlToolsPath `
            -Query "SET NOCOUNT ON; SELECT CASE WHEN DB_ID(N'$TargetDatabase') IS NULL THEN 0 ELSE 1 END;"
        if ($stillMissingResult.ExitCode -ne 0) {
            Write-CommandOutput -Output $stillMissingResult.Output
            Throw-RestoreError -Code 3 -Message 'Could not re-check the target database name.'
        }
        $targetExists = @($stillMissingResult.Output | ForEach-Object { ([string]$_).Trim() }) -contains '1'
        if ($targetExists) {
            Throw-RestoreError -Code 2 -Message "Target database '$TargetDatabase' appeared during preflight. Aborting."
        }

        foreach ($targetFile in $movePlan.TargetFiles) {
            $fileCheck = Invoke-NativeCommand -FilePath 'docker' -Arguments @(
                'exec', $ContainerName, 'test', '-e', $targetFile
            )
            if ($fileCheck.ExitCode -eq 0) {
                Throw-RestoreError -Code 2 -Message "Target physical file already exists: $targetFile"
            }
            if ($fileCheck.ExitCode -ne 1) {
                Throw-RestoreError -Code 3 -Message "Could not check target physical file: $targetFile"
            }
        }

        Write-Log "Restore plan for [$TargetDatabase]:"
        foreach ($move in $movePlan.Moves) {
            Write-Log "  $move"
        }

        if ($DryRun) {
            Write-Log 'DRY RUN complete. RESTORE DATABASE, DBCC CHECKDB and validation were NOT executed.' -Level WARN
            return 0
        }

        $restoreQuery = "RESTORE DATABASE [$TargetDatabase] FROM DISK = N'$containerTemp' WITH FILE = $FileNumber, " +
            (($movePlan.Moves -join ', ') + ', RECOVERY, STATS = 10;')
        Write-Log "Restoring into isolated database [$TargetDatabase] ..."
        $restoreResult = Invoke-SqlCmd `
            -ContainerName $ContainerName `
            -SqlUser $SqlUser `
            -SqlPassword $SqlPassword `
            -SqlToolsPath $SqlToolsPath `
            -Query $restoreQuery
        Write-CommandOutput -Output $restoreResult.Output
        if ($restoreResult.ExitCode -ne 0) {
            Throw-RestoreError -Code 6 -Message "RESTORE DATABASE failed with exit code $($restoreResult.ExitCode). The target database was not dropped automatically."
        }

        Write-Log 'Running DBCC CHECKDB ...'
        $checkDbResult = Invoke-SqlCmd `
            -ContainerName $ContainerName `
            -SqlUser $SqlUser `
            -SqlPassword $SqlPassword `
            -SqlToolsPath $SqlToolsPath `
            -Query "DBCC CHECKDB ([$TargetDatabase]) WITH NO_INFOMSGS;"
        Write-CommandOutput -Output $checkDbResult.Output
        if ($checkDbResult.ExitCode -ne 0) {
            Throw-RestoreError -Code 7 -Message 'DBCC CHECKDB failed. The restored database was left in place for inspection.'
        }

        $validationQuery = @"
SET NOCOUNT ON;
SELECT 'state=' + state_desc FROM sys.databases WHERE name = N'$TargetDatabase';
SELECT 'tables=' + CAST(COUNT(*) AS varchar(20)) FROM sys.tables;
SELECT 'users=' + CAST(COUNT(*) AS varchar(20)) FROM dbo.users;
SELECT 'jobs=' + CAST(COUNT(*) AS varchar(20)) FROM dbo.jobs;
SELECT 'resumes=' + CAST(COUNT(*) AS varchar(20)) FROM dbo.resumes;
SELECT 'knowledge_documents=' + CAST(COUNT(*) AS varchar(20)) FROM dbo.knowledge_documents;
"@
        $validationResult = Invoke-SqlCmd `
            -ContainerName $ContainerName `
            -SqlUser $SqlUser `
            -SqlPassword $SqlPassword `
            -SqlToolsPath $SqlToolsPath `
            -Database $TargetDatabase `
            -Query $validationQuery
        Write-CommandOutput -Output $validationResult.Output
        if ($validationResult.ExitCode -ne 0) {
            Throw-RestoreError -Code 7 -Message 'Post-restore schema/data probes failed. The restored database was left in place for inspection.'
        }
        $validationLines = @(
            $validationResult.Output |
                ForEach-Object { ([string]$_).Trim() } |
                Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        )
        if (-not ($validationLines -contains 'state=ONLINE')) {
            Throw-RestoreError -Code 7 -Message "Restored database '$TargetDatabase' is not ONLINE."
        }

        Write-Log "Restore completed and validated: [$TargetDatabase]"
        Write-Log 'The restored database was intentionally left in place. The script never drops it.'
        return 0
    }
    catch {
        $exitCode = 1
        if ($_.Exception.Data -and $_.Exception.Data.Contains('ExitCode')) {
            $exitCode = [int]$_.Exception.Data['ExitCode']
        }
        Write-Log $_.Exception.Message -Level ERROR
        return $exitCode
    }
    finally {
        if ($containerTemp) {
            $cleanup = Invoke-NativeCommand -FilePath 'docker' -Arguments @(
                'exec', '--user', 'root', $ContainerName, 'rm', '-f', $containerTemp
            )
            if ($cleanup.ExitCode -ne 0) {
                Write-Log "Could not remove container temporary backup: $containerTemp" -Level WARN
            }
        }
    }
}

if (-not $NoRun) {
    exit (Invoke-RestoreMain)
}
