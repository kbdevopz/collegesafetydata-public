<#
.SYNOPSIS
    Extracts NCES's official fall FTE and share of exclusively online students
    for 2015-2020 from the final IPEDS Access databases into etl/reference.

.DESCRIPTION
    Windows only. It needs the 64-bit "Microsoft Access Driver (*.mdb, *.accdb)"
    ODBC driver (Microsoft Access Database Engine 2016 Redistributable) and runs
    in Windows PowerShell 5.1 or PowerShell 7. The build itself does not need
    it: 02b_transform_ef_enrollment.py reads the CSV this script writes, which
    is committed in etl/reference. Run it only to check or refresh that CSV.

    For falls before 2021, NCES publishes its own FTE (table DRVEF<year>,
    columns FTE and PCTDEEXC, the percent of students enrolled exclusively in
    distance education) only inside the final Access database of that
    collection year, IPEDS_<yyyy>-<yy>_Final.zip (60 to 77 MB each). For each
    fall year 2015-2020 this script:
      1. downloads the zip into -ZipDir, unless it is already there,
      2. checks its size and SHA-256 against etl/reference/ipeds_official_sources.json
         and stops if they differ (NCES re-issued the file: look at what
         changed, then run again with -Record to record the new zip),
      3. extracts the .accdb (once),
      4. reads UNITID, FTE and PCTDEEXC from DRVEF<year>,
    and then writes etl/reference/ipeds_official_fte.csv (year, unitid, fte,
    pctdeexc; a blank cell is a value NCES left empty) and the sources file
    (url, size, SHA-256, database, table and row count of each zip).

.PARAMETER ZipDir
    Where the zips are kept and extracted (default data/raw/ipeds_official).

.PARAMETER Record
    Accept zips whose size or SHA-256 differ from the sources file (or a
    sources file that does not exist yet) and record them.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File etl\01c_extract_ipeds_official.ps1
#>
param(
    [string]$ZipDir = (Join-Path $PSScriptRoot "..\data\raw\ipeds_official"),
    [switch]$Record
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$FallYears = 2015..2020
$ReferenceDir = Join-Path $PSScriptRoot "reference"
$SourcesPath = Join-Path $ReferenceDir "ipeds_official_sources.json"
$CsvPath = Join-Path $ReferenceDir "ipeds_official_fte.csv"
$Invariant = [Globalization.CultureInfo]::InvariantCulture
$Utf8 = New-Object Text.UTF8Encoding $false

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "This script reads Microsoft Access databases through the Windows ODBC driver, so it runs on Windows only. The build does not need it: etl/reference/ipeds_official_fte.csv is committed."
}
if (-not [Environment]::Is64BitProcess) {
    throw "Run this script in 64-bit PowerShell: the Access ODBC driver it needs is the 64-bit one."
}
$driver = "Microsoft Access Driver (*.mdb, *.accdb)"
$installed = Get-ItemProperty "HKLM:\SOFTWARE\ODBC\ODBCINST.INI\ODBC Drivers" -ErrorAction SilentlyContinue
if (-not $installed -or -not ($installed.PSObject.Properties.Name -contains $driver)) {
    throw "The 64-bit ODBC driver '$driver' is not installed. Install the Microsoft Access Database Engine 2016 Redistributable (64-bit) from Microsoft, then run this script again."
}

# What was recorded for each zip (fall year -> entry)
$recorded = @{}
if (Test-Path $SourcesPath) {
    foreach ($entry in (Get-Content $SourcesPath -Raw | ConvertFrom-Json)) { $recorded[[int]$entry.fall_year] = $entry }
} elseif (-not $Record) {
    throw "$SourcesPath not found. Run with -Record to download the zips and record their size and SHA-256."
}

function Format-Cell($value) {
    if ($null -eq $value -or $value -is [DBNull]) { return "" }
    $number = [double]$value
    if ($number -ne [Math]::Floor($number)) { throw "DRVEF holds $value where a whole number is expected." }
    return ([long]$number).ToString($Invariant)
}

function Json-Text([string]$text) {
    return '"' + ($text -replace '\\', '\\' -replace '"', '\"') + '"'
}

New-Item -ItemType Directory -Force $ZipDir | Out-Null
$rows = New-Object System.Collections.Generic.List[object]
$sources = New-Object System.Collections.Generic.List[object]
foreach ($fall in $FallYears) {
    $collection = "{0}-{1:D2}" -f $fall, (($fall + 1) % 100)
    $name = "IPEDS_${collection}_Final.zip"
    $url = "https://nces.ed.gov/ipeds/tablefiles/zipfiles/$name"
    $zip = Join-Path $ZipDir $name

    # 1. The zip
    if (-not (Test-Path $zip)) {
        Write-Output "$fall`: downloading $url"
        $part = "$zip.part"
        Invoke-WebRequest $url -OutFile $part -UserAgent "collegesafetydata-etl" -UseBasicParsing
        Move-Item $part $zip -Force
    }
    # 2. Size and SHA-256, against the sources file
    $bytes = (Get-Item $zip).Length
    $sha = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    $was = $recorded[$fall]
    if ($was -and ([long]$was.bytes -ne $bytes -or $was.sha256 -ne $sha) -and -not $Record) {
        throw "$name ($bytes bytes, SHA-256 $sha) differs from the zip recorded in $SourcesPath ($($was.bytes) bytes, SHA-256 $($was.sha256)). NCES may have re-issued it. Check what changed, then run again with -Record to use and record it."
    }
    if (-not $was -and -not $Record) {
        throw "$SourcesPath has no entry for $name. Run with -Record to record it."
    }

    # 3. The Access database, extracted once
    $dir = Join-Path $ZipDir "db_$fall"
    $db = if (Test-Path $dir) { Get-ChildItem $dir -Recurse -Filter *.accdb | Select-Object -First 1 } else { $null }
    if (-not $db) {
        Write-Output "$fall`: extracting $name"
        $tmp = "$dir.part"
        if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
        Expand-Archive $zip -DestinationPath $tmp
        if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
        Move-Item $tmp $dir
        $db = Get-ChildItem $dir -Recurse -Filter *.accdb | Select-Object -First 1
        if (-not $db) { throw "$name holds no .accdb database. Look at the zip; NCES may have changed its format." }
    }

    # 4. DRVEF<fall>: UNITID, FTE, PCTDEEXC
    $table = "DRVEF$fall"
    $conn = New-Object System.Data.Odbc.OdbcConnection("Driver={$driver};Dbq=$($db.FullName);ReadOnly=1;")
    $conn.Open()
    try {
        $names = @($conn.GetSchema("Tables") | Where-Object { $_.TABLE_TYPE -eq "TABLE" } | ForEach-Object { $_.TABLE_NAME })
        if ($names -notcontains $table) {
            throw "$($db.Name) has no table $table (tables like it: $(($names -match 'DRVEF') -join ', ')). Look at the database; NCES may have renamed it."
        }
        $cmd = $conn.CreateCommand()
        $cmd.CommandText = "SELECT UNITID, FTE, PCTDEEXC FROM [$table]"
        try { $reader = $cmd.ExecuteReader() } catch {
            throw "Reading UNITID, FTE and PCTDEEXC from $table in $($db.Name) failed ($($_.Exception.Message)). Look at the table's columns; NCES may have renamed one."
        }
        $count = 0
        $seen = @{}
        while ($reader.Read()) {
            $unitid = Format-Cell $reader.GetValue(0)
            if ($unitid -eq "") { throw "$table in $($db.Name) has a row without a UNITID." }
            if ($seen.ContainsKey($unitid)) { throw "$table in $($db.Name) lists UNITID $unitid twice." }
            $seen[$unitid] = $true
            $rows.Add([pscustomobject]@{ year = $fall; unitid = [long]$unitid
                                         fte = (Format-Cell $reader.GetValue(1)); pct = (Format-Cell $reader.GetValue(2)) })
            $count++
        }
        $reader.Close()
    } finally { $conn.Close() }
    if ($count -eq 0) { throw "$table in $($db.Name) has no rows." }
    $sources.Add([ordered]@{ fall_year = $fall; url = $url; zip = $name; bytes = $bytes; sha256 = $sha
                             database = $db.Name; table = $table; rows = $count })
    Write-Output ("{0}: {1:N0} institutions from {2} {3}" -f $fall, $count, $db.Name, $table)
}

# The reference CSV: one row per fall year and institution, sorted
New-Item -ItemType Directory -Force $ReferenceDir | Out-Null
$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("year,unitid,fte,pctdeexc")
foreach ($r in ($rows | Sort-Object year, unitid)) { $lines.Add("$($r.year),$($r.unitid),$($r.fte),$($r.pct)") }
[IO.File]::WriteAllText($CsvPath, (($lines -join "`n") + "`n"), $Utf8)

# The sources file, written by hand so its bytes do not depend on the PowerShell version
$entries = foreach ($s in $sources) {
    "  {`n" + (@(
        "    `"fall_year`": $($s.fall_year)",
        "    `"url`": $(Json-Text $s.url)",
        "    `"zip`": $(Json-Text $s.zip)",
        "    `"bytes`": $($s.bytes)",
        "    `"sha256`": $(Json-Text $s.sha256)",
        "    `"database`": $(Json-Text $s.database)",
        "    `"table`": $(Json-Text $s.table)",
        "    `"rows`": $($s.rows)"
    ) -join ",`n") + "`n  }"
}
[IO.File]::WriteAllText($SourcesPath, "[`n" + ($entries -join ",`n") + "`n]`n", $Utf8)
Write-Output "Wrote $CsvPath ($($rows.Count) rows) and $SourcesPath"
