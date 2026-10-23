$ErrorActionPreference = 'Stop'

$backupScript = Join-Path $PSScriptRoot '..\backup_mssql.ps1'
$restoreScript = Join-Path $PSScriptRoot '..\restore_mssql.ps1'

. $backupScript -NoRun
. $restoreScript -NoRun

Describe 'Backup helpers' {
    It 'creates a UTC millisecond backup filename' {
        $timestamp = [DateTime]::new(2026, 1, 2, 3, 4, 5, 678, [DateTimeKind]::Utc)
        Get-BackupFileName -DatabaseName 'ai_recruitment_platform' -UtcNow $timestamp |
            Should Be 'ai_recruitment_platform_20260102T030405678Z.bak'
    }

    It 'parses .env values without exposing or mangling them' {
        $path = Join-Path $TestDrive '.env'
        Set-Content -LiteralPath $path -Value @(
            '# comment',
            'DATABASE_NAME=ai_recruitment_platform',
            'QUOTED="quoted-value"',
            'WITH_SPACES = spaced-value '
        )

        Get-DotEnvValue -Path $path -Key 'DATABASE_NAME' | Should Be 'ai_recruitment_platform'
        Get-DotEnvValue -Path $path -Key 'QUOTED' | Should Be 'quoted-value'
        Get-DotEnvValue -Path $path -Key 'WITH_SPACES' | Should Be 'spaced-value'
        Get-DotEnvValue -Path $path -Key 'MISSING' | Should BeNullOrEmpty
    }

    It 'accepts safe database identifiers and rejects unsafe ones' {
        { Assert-DatabaseIdentifier -Value 'restore_drill_2026' } | Should Not Throw
        { Assert-DatabaseIdentifier -Value 'bad-name' } | Should Throw
        { Assert-DatabaseIdentifier -Value "bad'name" } | Should Throw
    }

    It 'refuses to overwrite an existing backup file' {
        $path = Join-Path $TestDrive 'existing.bak'
        Set-Content -LiteralPath $path -Value 'backup'

        {
            Assert-BackupTargetAvailable -Directory $TestDrive -FileName 'existing.bak'
        } | Should Throw
    }

    It 'refuses to overwrite an existing checksum sidecar' {
        $path = Join-Path $TestDrive 'new.bak'
        Set-Content -LiteralPath "$path.sha256" -Value 'sidecar'

        {
            Assert-BackupTargetAvailable -Directory $TestDrive -FileName 'new.bak'
        } | Should Throw
    }

    It 'writes a lowercase SHA-256 sidecar and refuses to replace it' {
        $path = Join-Path $TestDrive 'sample.bak'
        Set-Content -LiteralPath $path -Value 'sample backup'

        $hash = New-ChecksumSidecar -FilePath $path
        $sidecar = "$path.sha256"

        $hash | Should Match '^[a-f0-9]{64}$'
        Test-Path -LiteralPath $sidecar | Should Be $true
        (Get-Content -LiteralPath $sidecar -Raw) | Should Match ([regex]::Escape($hash))
        (Get-Content -LiteralPath $sidecar -Raw) | Should Match 'sample\.bak'

        { New-ChecksumSidecar -FilePath $path } | Should Throw
    }
}

Describe 'Restore safety guards' {
    It 'rejects system databases' {
        { Assert-SafeRestoreTarget -TargetDatabase 'master' } | Should Throw
        { Assert-SafeRestoreTarget -TargetDatabase 'msdb' } | Should Throw
    }

    It 'rejects the active source database and configured protected databases' {
        {
            Assert-SafeRestoreTarget -TargetDatabase 'ai_recruitment_platform' `
                -ProtectedDatabases @('ai_recruitment_platform')
        } | Should Throw
    }

    It 'rejects an existing target database instead of overwriting it' {
        {
            Assert-SafeRestoreTarget -TargetDatabase 'restore_drill' `
                -ExistingDatabases @('restore_drill')
        } | Should Throw
    }

    It 'accepts a new isolated target database' {
        {
            Assert-SafeRestoreTarget -TargetDatabase 'restore_drill_2026' `
                -ProtectedDatabases @('ai_recruitment_platform') `
                -ExistingDatabases @('ai_recruitment_platform', 'ai_recruitment_platform_test')
        } | Should Not Throw
    }

    It 'rejects unsafe target names' {
        { Assert-SafeRestoreTarget -TargetDatabase 'bad-name' } | Should Throw
        { Assert-SafeRestoreTarget -TargetDatabase ' ' } | Should Throw
    }
}

Describe 'Restore parsing helpers' {
    It 'parses only data and log rows from RESTORE FILELISTONLY output' {
        $lines = @(
            'LogicalName|PhysicalName|Type|FileGroupName|Size',
            'ai_recruitment_platform|/var/opt/mssql/data/ai_recruitment_platform.mdf|D|PRIMARY|1',
            'ai_recruitment_platform_log|/var/opt/mssql/data/ai_recruitment_platform_log.ldf|L|NULL|2',
            'something_else|/tmp/other|S|NULL|3'
        )

        $files = ConvertFrom-RestoreFileList -Lines $lines

        @($files).Count | Should Be 2
        $files[0].LogicalName | Should Be 'ai_recruitment_platform'
        $files[0].FileType | Should Be 'D'
        $files[1].LogicalName | Should Be 'ai_recruitment_platform_log'
        $files[1].FileType | Should Be 'L'
    }

    It 'rejects FILELISTONLY output with no data or log files' {
        { ConvertFrom-RestoreFileList -Lines @('header only') } | Should Throw
    }

    It 'joins container paths without duplicating slashes' {
        Join-ContainerPath -Directory '/var/opt/mssql/data/' -FileName 'x.mdf' |
            Should Be '/var/opt/mssql/data/x.mdf'
    }

    It 'builds a unique MOVE plan without touching the source filenames' {
        $files = @(
            [pscustomobject]@{ LogicalName = 'db'; PhysicalName = '/old/db.mdf'; FileType = 'D' },
            [pscustomobject]@{ LogicalName = 'db2'; PhysicalName = '/old/db2.ndf'; FileType = 'D' },
            [pscustomobject]@{ LogicalName = 'db_log'; PhysicalName = '/old/db_log.ldf'; FileType = 'L' }
        )

        $plan = New-RestoreMovePlan -Files $files -TargetDatabase 'restore_drill' `
            -DataDirectory '/var/opt/mssql/data' `
            -LogDirectory '/var/opt/mssql/data'

        @($plan.TargetFiles).Count | Should Be 3
        $plan.TargetFiles[0] | Should Be '/var/opt/mssql/data/restore_drill.mdf'
        $plan.TargetFiles[1] | Should Be '/var/opt/mssql/data/restore_drill_2.ndf'
        $plan.TargetFiles[2] | Should Be '/var/opt/mssql/data/restore_drill_log.ldf'
        $plan.Moves[0] | Should Be "MOVE N'db' TO N'/var/opt/mssql/data/restore_drill.mdf'"
        $plan.Moves[2] | Should Be "MOVE N'db_log' TO N'/var/opt/mssql/data/restore_drill_log.ldf'"
    }

    It 'rejects a backup with no data files or no log files' {
        $dataOnly = @(
            [pscustomobject]@{ LogicalName = 'db'; PhysicalName = '/old/db.mdf'; FileType = 'D' }
        )
        $logOnly = @(
            [pscustomobject]@{ LogicalName = 'db_log'; PhysicalName = '/old/db_log.ldf'; FileType = 'L' }
        )

        {
            New-RestoreMovePlan -Files $dataOnly -TargetDatabase 'restore_drill' `
                -DataDirectory '/var/opt/mssql/data' -LogDirectory '/var/opt/mssql/data'
        } | Should Throw

        {
            New-RestoreMovePlan -Files $logOnly -TargetDatabase 'restore_drill' `
                -DataDirectory '/var/opt/mssql/data' -LogDirectory '/var/opt/mssql/data'
        } | Should Throw
    }
}

Describe 'Checksum verification' {
    It 'reads a sidecar and strips the sha256sum binary marker' {
        $path = Join-Path $TestDrive 'checksum.txt'
        $hash = 'a' * 64
        Set-Content -LiteralPath $path -Value "$hash *backup.bak"

        $result = Read-ChecksumSidecar -Path $path

        $result.Hash | Should Be $hash
        $result.FileName | Should Be 'backup.bak'
    }

    It 'rejects malformed or empty sidecars' {
        $malformed = Join-Path $TestDrive 'malformed.sha256'
        Set-Content -LiteralPath $malformed -Value 'not-a-hash'
        { Read-ChecksumSidecar -Path $malformed } | Should Throw

        $empty = Join-Path $TestDrive 'empty.sha256'
        Set-Content -LiteralPath $empty -Value ''
        { Read-ChecksumSidecar -Path $empty } | Should Throw
    }

    It 'compares file content hashes case-insensitively' {
        $path = Join-Path $TestDrive 'checksum-target.bak'
        Set-Content -LiteralPath $path -Value 'content'
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash

        Test-FileChecksum -FilePath $path -ExpectedHash $hash.ToLowerInvariant() |
            Should Be $true
        Test-FileChecksum -FilePath $path -ExpectedHash ('0' * 64) |
            Should Be $false
    }
}
