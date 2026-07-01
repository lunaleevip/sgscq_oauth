<?php
// Trigger SGSCQ OAuth sync workflows from an external 5-minute cron.
// Configure GITHUB_DISPATCH_TOKEN in the server environment.

$token = getenv('GITHUB_DISPATCH_TOKEN');
if (!$token) {
    http_response_code(500);
    echo "missing GITHUB_DISPATCH_TOKEN\n";
    exit;
}

$repo = getenv('GITHUB_REPO') ?: 'lunaleevip/sgscq_oauth';
$stateFile = getenv('AFDIAN_FULL_SYNC_STATE') ?: sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'sgscq_afdian_full_hour';
$currentHour = gmdate('YmdH');
$lastFullHour = is_readable($stateFile) ? trim(file_get_contents($stateFile)) : '';
$runFull = $lastFullHour !== $currentHour;
$events = $runFull ? ['afdian_full', 'bili_followers'] : ['afdian_incremental', 'bili_followers'];
$ok = true;

foreach ($events as $eventType) {
    $body = json_encode([
        'event_type' => $eventType,
        'client_payload' => [
            'source' => 'external_cron',
            'time' => gmdate('c'),
        ],
    ], JSON_UNESCAPED_UNICODE);

    $ch = curl_init("https://api.github.com/repos/{$repo}/dispatches");
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => [
            'Authorization: Bearer ' . $token,
            'Accept: application/vnd.github+json',
            'Content-Type: application/json',
            'User-Agent: sgscq-oauth-sync-cron',
            'X-GitHub-Api-Version: 2022-11-28',
        ],
        CURLOPT_POSTFIELDS => $body,
        CURLOPT_TIMEOUT => 20,
    ]);

    $response = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $error = curl_error($ch);
    curl_close($ch);

    if ($code !== 204) {
        $ok = false;
        echo "{$eventType}: failed HTTP {$code} {$error} {$response}\n";
    } else {
        echo "{$eventType}: dispatched\n";
        if ($eventType === 'afdian_full') {
            $written = file_put_contents($stateFile, $currentHour . PHP_EOL, LOCK_EX);
            if ($written === false) {
                $ok = false;
                echo "{$eventType}: failed to update state file {$stateFile}\n";
            }
        }
    }
}

http_response_code($ok ? 200 : 500);
