# 为 example_11_access_url_feature_pipeline 准备 Elasticsearch 测试数据
# 依赖: 本机 ES 7.x/8.x 已启动，PowerShell 5+
#
# 用法:
#   .\setup.ps1
#   .\setup.ps1 -EsHost "http://127.0.0.1:9200" -Recreate

param(
    [string]$EsHost = "http://127.0.0.1:9200",
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

function Invoke-Es {
    param(
        [ValidateSet("GET", "PUT", "POST", "DELETE")]
        [string]$Method,
        [string]$Path,
        [string]$Body = $null
    )
    $uri = "$EsHost/$Path"
    if ($Body) {
        return Invoke-RestMethod -Method $Method -Uri $uri -ContentType "application/json" -Body $Body
    }
    return Invoke-RestMethod -Method $Method -Uri $uri
}

Write-Host "Checking Elasticsearch at $EsHost ..."
Invoke-Es -Method GET -Path "" | Out-Null

$indices = @{
    "access-log-demo" = @{
        settings = @{ number_of_shards = 1; number_of_replicas = 0 }
        mappings = @{
            properties = @{
                "@timestamp"           = @{ type = "date" }
                subject_account        = @{ type = "keyword" }
                subject_ip             = @{ type = "keyword" }
                url_pattern            = @{ type = "keyword" }
                count                  = @{ type = "long" }
                status_freq_dict       = @{ type = "object"; enabled = $true }
                method_freq_dict       = @{ type = "object"; enabled = $true }
                xff_freq_dict          = @{ type = "object"; enabled = $true }
                is_intranet            = @{ type = "keyword" }
                response_length_max    = @{ type = "double" }
                high_worth_api_type    = @{ type = "keyword" }
                attack_hw_target       = @{ type = "keyword" }
                ai_app_type            = @{ type = "keyword" }
                appid                  = @{ type = "keyword" }
            }
        }
    }
    "t_url_info" = @{
        settings = @{ number_of_shards = 1; number_of_replicas = 0 }
        mappings = @{
            properties = @{
                url_pattern               = @{ type = "keyword" }
                latest_7d_resp_size_avg   = @{ type = "double" }
                latest_7d_count           = @{ type = "double" }
                latest_24h_count          = @{ type = "double" }
                ip_7d_dc                  = @{ type = "double" }
                top_methods               = @{ type = "text" }
                top_status_codes          = @{ type = "text" }
                create_time               = @{ type = "date" }
                app_id                    = @{ type = "keyword" }
            }
        }
    }
    "t_int_ip_info" = @{
        settings = @{ number_of_shards = 1; number_of_replicas = 0 }
        mappings = @{
            properties = @{
                ip            = @{ type = "keyword" }
                network_area  = @{ type = "keyword" }
            }
        }
    }
}

foreach ($name in $indices.Keys) {
    if ($Recreate) {
        try {
            Invoke-Es -Method DELETE -Path $name | Out-Null
            Write-Host "Deleted index: $name"
        } catch {
            Write-Host "Skip delete $name (not exists)"
        }
    }
    $body = ($indices[$name] | ConvertTo-Json -Depth 20 -Compress)
    Invoke-Es -Method PUT -Path $name -Body $body | Out-Null
    Write-Host "Created index: $name"
}

$bulkPath = Join-Path $Root "02_bulk_documents.ndjson"
$bulkUri = "$EsHost/_bulk?refresh=wait_for"
$nowIso = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
$weekAgoIso = (Get-Date).AddDays(-7).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
$bulkBody = (Get-Content -Path $bulkPath -Raw -Encoding UTF8) `
    -replace '"@timestamp":"now"', "`"@timestamp`":`"$nowIso`"" `
    -replace '"create_time":"now-7d"', "`"create_time`":`"$weekAgoIso`""
$bulkTemp = Join-Path $env:TEMP "access_url_es_bulk.ndjson"
[System.IO.File]::WriteAllText($bulkTemp, $bulkBody, (New-Object System.Text.UTF8Encoding $false))
Write-Host "Bulk indexing from $bulkPath (timestamps -> $nowIso) ..."
$bulkResp = curl.exe -s -H "Content-Type: application/x-ndjson" -X POST $bulkUri --data-binary "@$bulkTemp"
if (-not $bulkResp) {
    throw "Bulk request returned empty response; check ES connectivity and curl output."
}
$bulkJson = $bulkResp | ConvertFrom-Json
if ($bulkJson.errors) {
    $failed = @($bulkJson.items | Where-Object {
        $_.index.error -or $_.create.error -or $_.update.error
    })
    Write-Warning "Bulk completed with $($failed.Count) error(s):"
    foreach ($item in $failed | Select-Object -First 5) {
        $err = $item.index.error
        if (-not $err) { $err = $item.create.error }
        Write-Warning ("  {0}: {1}" -f $item.index._id, $err.reason)
    }
    if ($failed.Count -gt 5) {
        Write-Warning "  ... and $($failed.Count - 5) more"
    }
    throw "Bulk indexing failed; re-run with -Recreate after fixing mappings."
}

$countAccess = (Invoke-Es -Method GET -Path "access-log-demo/_count").count
$countUrl = (Invoke-Es -Method GET -Path "t_url_info/_count").count
$countIp = (Invoke-Es -Method GET -Path "t_int_ip_info/_count").count

Write-Host ""
Write-Host "Done."
Write-Host "  access-log-demo docs: $countAccess"
Write-Host "  t_url_info docs:      $countUrl"
Write-Host "  t_int_ip_info docs:   $countIp"
Write-Host ""
Write-Host "Run example_11 with initial_context.es_index = access-log-* (default matches access-log-demo)."
