# 验证真实 Kafka 收发；使用独立临时 Topic，不发送业务文档任务。
$composeFile = Join-Path $PSScriptRoot 'compose.yaml'
$runId = [guid]::NewGuid().ToString('N')
$topic = "rag.smoke.$runId"
$message = "rag-kafka-smoke-$runId"

& docker compose -f $composeFile exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:29092 --create --topic $topic --partitions 1 --replication-factor 1
if ($LASTEXITCODE -ne 0) { throw 'Cannot create smoke-test topic. Check Kafka health first.' }

try {
    $message | & docker compose -f $composeFile exec -T kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server kafka:29092 --topic $topic --producer-property acks=all
    if ($LASTEXITCODE -ne 0) { throw 'Kafka producer failed.' }

    $received = & docker compose -f $composeFile exec -T kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server kafka:29092 --topic $topic --from-beginning --max-messages 1 --timeout-ms 30000
    if ($LASTEXITCODE -ne 0) { throw 'Kafka consumer failed or timed out.' }
    if (@($received) -notcontains $message) { throw 'The consumed message did not match the produced message.' }

    Write-Output "PASS: produced and consumed $message"
}
finally {
    & docker compose -f $composeFile exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:29092 --delete --topic $topic
    if ($LASTEXITCODE -ne 0) { Write-Warning "Could not delete temporary topic: $topic" }
}
