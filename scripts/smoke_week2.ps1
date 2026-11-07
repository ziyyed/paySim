[CmdletBinding()]
param(
    [string]$ComposeFile = (Join-Path $PSScriptRoot '..\environment\docker-compose.yml'),
    [string]$ResultsFile = (Join-Path $PSScriptRoot '..\results\week2-smoke-results.json')
)

$ErrorActionPreference = 'Stop'
$ComposeFile = (Resolve-Path -LiteralPath $ComposeFile).Path
$namenode = 'p02-namenode'
$kafka = 'p02-kafka'
$runId = [Guid]::NewGuid().ToString('N')
$topic = "week2-smoke-$runId"
$hdfsPath = "/p02/week2-smoke/$runId.txt"
$containerTmpPath = "/tmp/week2-smoke-$runId.txt"
$localTmpPath = Join-Path ([System.IO.Path]::GetTempPath()) "week2-smoke-$runId.txt"
$payload = "week2-hdfs-smoke:$runId"
$utf8 = [System.Text.UTF8Encoding]::new($false)

function Invoke-DockerChecked {
    param([string[]]$Arguments)
    $result = & docker @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed ($LASTEXITCODE): docker $($Arguments -join ' ') :: $($result -join '|')"
    }
    return ,@($result | ForEach-Object { $_.ToString() })
}

try {
    [System.IO.File]::WriteAllText($localTmpPath, $payload, $utf8)

    # Wait for DataNode registration so HDFS has left startup safe mode.
    $safeModeReady = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $safeModeLines = Invoke-DockerChecked @('exec', $namenode, 'hdfs', 'dfsadmin', '-safemode', 'get')
        if (($safeModeLines -join ' ') -match 'Safe mode is OFF') {
            $safeModeReady = $true
            break
        }
        Start-Sleep -Seconds 2
    }
    if (-not $safeModeReady) {
        throw 'HDFS did not leave startup safe mode within 60 seconds.'
    }

    # HDFS: copy the exact bytes into the namenode container, upload, then read back.
    Invoke-DockerChecked @('exec', $namenode, 'hdfs', 'dfs', '-mkdir', '-p', '/p02/week2-smoke') | Out-Null
    Invoke-DockerChecked @('cp', $localTmpPath, ('{0}:{1}' -f $namenode, $containerTmpPath)) | Out-Null
    Invoke-DockerChecked @('exec', $namenode, 'hdfs', 'dfs', '-put', '-f', $containerTmpPath, $hdfsPath) | Out-Null
    $hdfsLines = Invoke-DockerChecked @('exec', $namenode, 'hdfs', 'dfs', '-cat', $hdfsPath)
    $hdfsPayloadLines = @($hdfsLines | Where-Object { $_ -notmatch '^\d{4}-\d{2}-\d{2} .* (INFO|WARN|ERROR) ' })
    $hdfsReadback = $hdfsPayloadLines -join ''
    if ($hdfsReadback -cne $payload) {
        throw 'HDFS read-back differed from the uploaded test payload.'
    }
    $expectedHdfsHash = (Get-FileHash -LiteralPath $localTmpPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $actualHdfsHash = [Convert]::ToHexString(
        [System.Security.Cryptography.SHA256]::HashData($utf8.GetBytes($hdfsReadback))
    ).ToLowerInvariant()

    # Kafka: create a fresh topic, publish a basic event without any fraud label,
    # then consume the first message from that topic and compare its exact JSON.
    Invoke-DockerChecked @(
        'exec', $kafka, 'kafka-topics', '--bootstrap-server', 'kafka:29092',
        '--create', '--if-not-exists', '--topic', $topic,
        '--partitions', '1', '--replication-factor', '1'
    ) | Out-Null
    $eventObject = [ordered]@{
        event_id = "week2-smoke-$runId"
        step = 1
        type = 'PAYMENT'
        amount = 12.5
        nameOrig = 'C_TEST_01'
        nameDest = 'M_TEST_01'
    }
    $eventJson = $eventObject | ConvertTo-Json -Compress
    $producerArgs = @('exec', '-i', $kafka, 'kafka-console-producer', '--bootstrap-server', 'kafka:29092', '--topic', $topic)
    $producerResult = $eventJson | & docker @producerArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Kafka producer failed ($LASTEXITCODE): $($producerResult -join '|')"
    }
    $consumerLines = Invoke-DockerChecked @(
        'exec', $kafka, 'kafka-console-consumer',
        '--bootstrap-server', 'kafka:29092',
        '--topic', $topic,
        '--from-beginning',
        '--max-messages', '1',
        '--timeout-ms', '15000'
    )
    $receivedJsonLines = @($consumerLines | Where-Object { $_.ToString().TrimStart().StartsWith('{') })
    if ($receivedJsonLines.Count -ne 1) {
        throw 'Kafka consumer did not return exactly one JSON event.'
    }
    $receivedEvent = $receivedJsonLines[0].ToString().Trim()
    if ($receivedEvent -cne $eventJson) {
        throw "Kafka consumer did not return the exact event published to $topic."
    }
    $parsedEvent = $receivedEvent | ConvertFrom-Json
    if ($parsedEvent.PSObject.Properties.Name -contains 'isFraud') {
        throw 'The Week 2 smoke event must remain unlabeled.'
    }

    $result = [ordered]@{
        smoke_schema_version = 1
        run_id = $runId
        executed_at_utc = [DateTime]::UtcNow.ToString('o')
        hdfs = [ordered]@{
            status = 'passed'
            path = $hdfsPath
            readback_matches = $true
            uploaded_sha256 = $expectedHdfsHash
            readback_sha256 = $actualHdfsHash
        }
        kafka = [ordered]@{
            status = 'passed'
            topic = $topic
            event_received = $true
            event_has_fraud_label = $false
            event = $parsedEvent
        }
    }

    $ResultsFile = [System.IO.Path]::GetFullPath($ResultsFile)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ResultsFile) | Out-Null
    $json = $result | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($ResultsFile, $json + [Environment]::NewLine, $utf8)
    $json
    Write-Output "Evidence written to $ResultsFile"
}
finally {
    if (Test-Path -LiteralPath $localTmpPath) {
        Remove-Item -LiteralPath $localTmpPath -Force
    }
}