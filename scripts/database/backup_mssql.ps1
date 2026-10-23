<#
.SYNOPSIS
    Creates a verified SQL Server backup for the AI Recruitment Platform and
    copies it to a host directory with a SHA-256 sidecar checksum.

.DESCRIPTION
    The script is intentionally explicit: it never runs automatically and it
    never deletes older backups. It uses the running Microsoft SQL Server
    container (default: recruitment_mssql), writes the backup into the
    container's writable /tmp layer (not the database volume), verifies it with
    RESTORE VERIFYONLY, copies it to the host, and compares SHA-256 hashes
    before writing the .sha256 sidecar.

    A backup stored only in a directory on this host is NOT an off-site copy
    and does not protect against host loss, disk failure, ransomware, or theft.

.PARAMETER BackupDirectory
    Required host directory that will receive the .bak and .sha256 files.
    The directory is created when the backup runs. It is never pruned.

.PARAMETER DatabaseName
    Database to back up. Defaults to DATABASE_NAME from the repository .env.
    Only letters, digits and underscores are accepted.

.PARAMETER SqlUser
    SQL login. Defaults to DATABASE_USER from .env, then "sa".

.PARAMETER SqlPassword
    SQL password. Defaults to DATABASE_PASSWORD, then MSSQL_SA_PASSWORD from
    .env. The value is passed to sqlcmd through SQLCMDPASSWORD and is never
    written to the log.

.PARAMETER FileNumber
    Backup set number to verify. Defaults to 1 (the backup this script creates).

.PARAMETER DryRun
    Prints the planned artifact path without creating directories, contacting
    Docker, executing SQL, or writing any file.

.EXAMPLE
    .\scripts\database\backup_mssql.ps1 `
        -BackupDirectory D:\backups\ai-recruitment-platform\mssql

.EXAMPLE
    .\scripts\database\backup_mssql.ps1 `
        -BackupDirectory D:\backups\ai-recruitment-platform\mssql `
        -DatabaseName ai_recruitment_platform -DryRun

.NOTES
    Exit code 0 means every step succeeded. Any non-zero exit code means the
    backup was not certified as complete.
#>

[CmdletBinding()]
param(
    [string]$BackupDirectory = '',
    [string]$DatabaseName = '',
    [string]$ContainerName = 'recruitment_mssql',
    [string]$EnvFile = '',
    [string]$SqlUser = '',
    [string]$SqlPassword = '',
    [string]$SqlToolsPath = '/opt/mssql-tools18/bin/sqlcmd',
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
        throw "Database name must be 1-100 characters of letters, digits or underscore."
    }
}

function Get-BackupFileName {
    param(
        [Parameter(Mandatory = $true)][string]$DatabaseName,
        [DateTime]$UtcNow = [DateTime]::UtcNow
    )
    $stamp = $UtcNow.ToUniversalTime().ToString(
        "yyyyMMdd'T'HHmmssfff'Z'",
        [System.Globalization.CultureInfo]::InvariantCulture
    )
    return "$DatabaseName`_$stamp.bak"
}

function Assert-BackupTargetAvailable {
    param(
        [Parameter(Mandatory = $true)][string]$Directory,
        [Parameter(Mandatory = $true)][string]$FileName
    )
    $target = Join-Path -Path $Directory -ChildPath $FileName
    if (Test-Path -LiteralPath $target) {
        throw "Refusing to overwrite an existing backup: $target"
    }
    $sidecar = "$target.sha256"
    if (Test-Path -LiteralPath $sidecar) {
        throw "Refusing to overwrite an existing checksum sidecar: $sidecar"
    }
    return $target
}

function New-ChecksumSidecar {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath
    )
    $sidecar = "$FilePath.sha256"
    if (Test-Path -LiteralPath $sidecar) {
        throw "Refusing to overwrite existing checksum file: $sidecar"
    }
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $FilePath).Hash.ToLowerInvariant()
    $fileName = [System.IO.Path]::GetFileName($FilePath)
    $content = "$hash  $fileName`n"
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($sidecar, $content, $encoding)
    return $hash
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

function Invoke-BackupMain {
    $containerTemp = $null
    try {
        if ([string]::IsNullOrWhiteSpace($BackupDirectory)) {
            throw 'BackupDirectory is required. Choose a host directory outside the repository.'
        }

        $repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).ProviderPath
        if ([string]::IsNullOrWhiteSpace($EnvFile)) {
            $EnvFile = Join-Path $repoRoot '.env'
        }

        if ([string]::IsNullOrWhiteSpace($DatabaseName)) {
            $DatabaseName = Get-DotEnvValue -Path $EnvFile -Key 'DATABASE_NAME'
        }
        if ([string]::IsNullOrWhiteSpace($DatabaseName)) {
            throw "DatabaseName was not supplied and DATABASE_NAME was not found in $EnvFile."
        }
        Assert-DatabaseIdentifier -Value $DatabaseName

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
        if ([string]::IsNullOrWhiteSpace($SqlPassword)) {
            throw 'No SQL password was supplied or found in DATABASE_PASSWORD/MSSQL_SA_PASSWORD.'
        }

        if (-not [System.IO.Path]::IsPathRooted($BackupDirectory)) {
            $BackupDirectory = Join-Path (Get-Location).Path $BackupDirectory
        }
        $BackupDirectory = [System.IO.Path]::GetFullPath($BackupDirectory)
        $fileName = Get-BackupFileName -DatabaseName $DatabaseName
        $hostBackupPath = Join-Path -Path $BackupDirectory -ChildPath $fileName

        if ($DryRun) {
            Write-Log "DRY RUN: no directory, Docker, SQL or file operation will be performed."
            Write-Log "Planned host artifact: $hostBackupPath"
            Write-Log "Planned checksum artifact: $hostBackupPath.sha256"
            Write-Log "Database: $DatabaseName | Container: $ContainerName | SQL login: $SqlUser"
            Write-Log "Backup is host-local only; copy it off-host for disaster recovery."
            return 0
        }

        if (Test-Path -LiteralPath $BackupDirectory -PathType Leaf) {
            throw "BackupDirectory points to a file: $BackupDirectory"
        }
        if (-not (Test-Path -LiteralPath $BackupDirectory)) {
            $null = New-Item -ItemType Directory -Path $BackupDirectory -Force
        }

        $hostBackupPath = Assert-BackupTargetAvailable `
            -Directory $BackupDirectory `
            -FileName $fileName

        if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
            throw 'The docker CLI is not available on PATH.'
        }
        if (-not (Test-ContainerRunning -ContainerName $ContainerName)) {
            throw "SQL Server container '$ContainerName' is not running."
        }

        $toolsCheck = Invoke-NativeCommand -FilePath 'docker' -Arguments @(
            'exec', $ContainerName, 'test', '-x', $SqlToolsPath
        )
        if ($toolsCheck.ExitCode -ne 0) {
            throw "sqlcmd was not found in the container at $SqlToolsPath."
        }

        $databaseCheck = Invoke-SqlCmd `
            -ContainerName $ContainerName `
            -SqlUser $SqlUser `
            -SqlPassword $SqlPassword `
            -SqlToolsPath $SqlToolsPath `
            -Query "SET NOCOUNT ON; SELECT CASE WHEN DB_ID(N'$DatabaseName') IS NULL THEN 0 ELSE 1 END;"
        if ($databaseCheck.ExitCode -ne 0) {
            Write-CommandOutput -Output $databaseCheck.Output
            throw "Could not query SQL Server for database '$DatabaseName'."
        }
        $databaseExists = @($databaseCheck.Output | ForEach-Object { ([string]$_).Trim() }) -contains '1'
        if (-not $databaseExists) {
            throw "Database '$DatabaseName' does not exist or is not visible to login '$SqlUser'."
        }

        $containerTemp = "/tmp/$fileName"
        $tempCheck = Invoke-NativeCommand -FilePath 'docker' -Arguments @(
            'exec', $ContainerName, 'test', '-e', $containerTemp
        )
        if ($tempCheck.ExitCode -eq 0) {
            throw "Refusing to reuse an existing container file: $containerTemp"
        }

        Write-Log "Starting COPY_ONLY backup of [$DatabaseName] to $containerTemp ..."
        $backupQuery = "BACKUP DATABASE [$DatabaseName] TO DISK = N'$containerTemp' WITH COPY_ONLY, CHECKSUM, STATS = 10;"
        $backupResult = Invoke-SqlCmd `
            -ContainerName $ContainerName `
            -SqlUser $SqlUser `
            -SqlPassword $SqlPassword `
            -SqlToolsPath $SqlToolsPath `
            -Query $backupQuery
        Write-CommandOutput -Output $backupResult.Output
        if ($backupResult.ExitCode -ne 0) {
            throw "BACKUP DATABASE failed with exit code $($backupResult.ExitCode)."
        }

        Write-Log "Running RESTORE VERIFYONLY WITH CHECKSUM ..."
        $verifyQuery = "RESTORE VERIFYONLY FROM DISK = N'$containerTemp' WITH FILE = $FileNumber, CHECKSUM;"
        $verifyResult = Invoke-SqlCmd `
            -ContainerName $ContainerName `
            -SqlUser $SqlUser `
            -SqlPassword $SqlPassword `
            -SqlToolsPath $SqlToolsPath `
            -Query $verifyQuery
        Write-CommandOutput -Output $verifyResult.Output
        if ($verifyResult.ExitCode -ne 0) {
            throw "RESTORE VERIFYONLY failed with exit code $($verifyResult.ExitCode)."
        }

        $containerHashResult = Invoke-NativeCommand -FilePath 'docker' -Arguments @(
            'exec', $ContainerName, 'sha256sum', $containerTemp
        )
        if ($containerHashResult.ExitCode -ne 0) {
            Write-CommandOutput -Output $containerHashResult.Output
            throw 'Could not compute the backup SHA-256 inside the container.'
        }
        $containerHashLine = @(
            $containerHashResult.Output |
                Where-Object { ([string]$_) -match '^[A-Fa-f0-9]{64}\s' } |
                Select-Object -First 1
        )
        if ($containerHashLine.Count -eq 0) {
            throw 'Could not parse the container SHA-256 output.'
        }
        $containerHash = (([string]$containerHashLine[0]) -split '\s+')[0].ToLowerInvariant()

        Write-Log "Copying backup to $hostBackupPath ..."
        $copyResult = Invoke-NativeCommand -FilePath 'docker' -Arguments @(
            'cp', "${ContainerName}:$containerTemp", $hostBackupPath
        )
        if ($copyResult.ExitCode -ne 0) {
            Write-CommandOutput -Output $copyResult.Output
            if (Test-Path -LiteralPath $hostBackupPath) {
                Remove-Item -LiteralPath $hostBackupPath -Force -ErrorAction SilentlyContinue
            }
            throw "docker cp failed with exit code $($copyResult.ExitCode)."
        }
        if (-not (Test-Path -LiteralPath $hostBackupPath -PathType Leaf)) {
            throw 'docker cp reported success but the host backup file is missing.'
        }

        $hostHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $hostBackupPath).Hash.ToLowerInvariant()
        if ($hostHash -ne $containerHash) {
            Remove-Item -LiteralPath $hostBackupPath -Force -ErrorAction SilentlyContinue
            throw 'Host backup SHA-256 does not match the container backup. Partial file removed.'
        }

        $sidecarHash = New-ChecksumSidecar -FilePath $hostBackupPath
        if ($sidecarHash -ne $hostHash) {
            throw 'Checksum sidecar was written but does not match the backup hash.'
        }

        $sizeBytes = (Get-Item -LiteralPath $hostBackupPath).Length
        Write-Log 'Backup completed and verified.'
        Write-Log "Artifact: $hostBackupPath"
        Write-Log "Checksum: $hostBackupPath.sha256 (SHA-256 $hostHash)"
        Write-Log "Size: $sizeBytes bytes"
        Write-Log 'WARNING: this is a host-local backup only. Copy it to independent storage for disaster recovery.'
        return 0
    }
    catch {
        Write-Log $_.Exception.Message -Level ERROR
        Write-Log 'Backup did NOT complete successfully.' -Level ERROR
        if ($containerTemp) {
            Write-Log "Container temporary file will be removed by cleanup: $containerTemp" -Level WARN
        }
        return 1
    }
    finally {
        if ($containerTemp) {
            $cleanup = Invoke-NativeCommand -FilePath 'docker' -Arguments @(
                'exec', '--user', 'root', $ContainerName, 'rm', '-f', $containerTemp
            )
            if ($cleanup.ExitCode -ne 0) {
                Write-Log "Could not remove container temporary file: $containerTemp" -Level WARN
            }
        }
    }
}

if (-not $NoRun) {
    exit (Invoke-BackupMain)
}
