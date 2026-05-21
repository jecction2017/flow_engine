# 向 simple_alarms 发送示例 JSON 消息（Kafka 2.7，Windows）
# 用法: .\send_sample_alarms.ps1
# 可选环境变量: $env:KAFKA_BIN = "E:\software\kafka\bin\windows"

$ErrorActionPreference = "Stop"
$KafkaBin = if ($env:KAFKA_BIN) { $env:KAFKA_BIN } else { "E:\software\kafka\bin\windows" }
$Bootstrap = if ($env:KAFKA_BOOTSTRAP) { $env:KAFKA_BOOTSTRAP } else { "localhost:9092" }
$Topic = "simple_alarms"

$Producer = Join-Path $KafkaBin "kafka-console-producer.bat"
if (-not (Test-Path $Producer)) {
    Write-Error "找不到 $Producer ，请设置环境变量 KAFKA_BIN"
}

$messages = @(
    '{"id": "2026040101", "activity_level": "low", "activity_feature": "app_type_01"}',
    '{"id": "2026040102", "activity_level": "high", "activity_feature": "app_type_02"}',
    '{"id": "2026040103", "activity_level": "medium", "activity_feature": "app_type_01"}'
)

Write-Host "发送到 $Topic @ $Bootstrap ..."
foreach ($line in $messages) {
    Write-Host "  -> $line"
    $line | & $Producer --bootstrap-server $Bootstrap --topic $Topic 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "发送可能失败 exit=$LASTEXITCODE （部分 Kafka 版本 producer 需交互式输入）"
    }
}

Write-Host ""
Write-Host "若上命令无输出，请改用手动方式:"
Write-Host "  cd $KafkaBin"
Write-Host "  .\kafka-console-producer.bat --bootstrap-server $Bootstrap --topic $Topic"
Write-Host "然后逐行粘贴 JSON。"
