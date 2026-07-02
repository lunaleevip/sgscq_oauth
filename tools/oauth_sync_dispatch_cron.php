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
$afdianStateFile = getenv('AFDIAN_FULL_SYNC_STATE') ?: sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'sgscq_afdian_full_hour';
$biliIncrementalStateFile = getenv('BILI_INCREMENTAL_SYNC_STATE') ?: sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'sgscq_bili_incremental_slot';
$biliFullStateFile = getenv('BILI_FULL_SYNC_STATE') ?: sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'sgscq_bili_full_slot';
$douyinIncrementalStateFile = getenv('DOUYIN_INCREMENTAL_SYNC_STATE') ?: sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'sgscq_douyin_incremental_slot';
$douyinFullStateFile = getenv('DOUYIN_FULL_SYNC_STATE') ?: sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'sgscq_douyin_full_slot';
$currentHour = gmdate('YmdH');
$currentSocialIncrementalSlot = gmdate('Ymd') . '-' . intdiv((int) gmdate('G'), 2);
$currentSocialFullSlot = gmdate('Ymd') . '-' . intdiv((int) gmdate('G'), 12);
$lastAfdianFullHour = is_readable($afdianStateFile) ? trim(file_get_contents($afdianStateFile)) : '';
$lastBiliIncrementalSlot = is_readable($biliIncrementalStateFile) ? trim(file_get_contents($biliIncrementalStateFile)) : '';
$lastBiliFullSlot = is_readable($biliFullStateFile) ? trim(file_get_contents($biliFullStateFile)) : '';
$lastDouyinIncrementalSlot = is_readable($douyinIncrementalStateFile) ? trim(file_get_contents($douyinIncrementalStateFile)) : '';
$lastDouyinFullSlot = is_readable($douyinFullStateFile) ? trim(file_get_contents($douyinFullStateFile)) : '';
$runAfdianFull = $lastAfdianFullHour !== $currentHour;
$runBiliFull = $lastBiliFullSlot !== $currentSocialFullSlot;
$runBiliIncremental = !$runBiliFull && $lastBiliIncrementalSlot !== $currentSocialIncrementalSlot;
$runDouyinFull = $lastDouyinFullSlot !== $currentSocialFullSlot;
$runDouyinIncremental = !$runDouyinFull && $lastDouyinIncrementalSlot !== $currentSocialIncrementalSlot;
$events = [
    $runAfdianFull ? 'afdian_full' : 'afdian_incremental',
];
if ($runBiliFull) {
    $events[] = 'bili_followers_full';
} elseif ($runBiliIncremental) {
    $events[] = 'bili_followers';
}
if ($runDouyinFull) {
    $events[] = 'douyin_followers_full';
} elseif ($runDouyinIncremental) {
    $events[] = 'douyin_followers';
}
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
            $written = file_put_contents($afdianStateFile, $currentHour . PHP_EOL, LOCK_EX);
            if ($written === false) {
                $ok = false;
                echo "{$eventType}: failed to update state file {$afdianStateFile}\n";
            }
        }
        if ($eventType === 'bili_followers_full') {
            $written = file_put_contents($biliFullStateFile, $currentSocialFullSlot . PHP_EOL, LOCK_EX);
            if ($written !== false) {
                $written = file_put_contents($biliIncrementalStateFile, $currentSocialIncrementalSlot . PHP_EOL, LOCK_EX);
            }
            if ($written === false) {
                $ok = false;
                echo "{$eventType}: failed to update state files {$biliFullStateFile} / {$biliIncrementalStateFile}\n";
            }
        }
        if ($eventType === 'bili_followers') {
            $written = file_put_contents($biliIncrementalStateFile, $currentSocialIncrementalSlot . PHP_EOL, LOCK_EX);
            if ($written === false) {
                $ok = false;
                echo "{$eventType}: failed to update state file {$biliIncrementalStateFile}\n";
            }
        }
        if ($eventType === 'douyin_followers_full') {
            $written = file_put_contents($douyinFullStateFile, $currentSocialFullSlot . PHP_EOL, LOCK_EX);
            if ($written !== false) {
                $written = file_put_contents($douyinIncrementalStateFile, $currentSocialIncrementalSlot . PHP_EOL, LOCK_EX);
            }
            if ($written === false) {
                $ok = false;
                echo "{$eventType}: failed to update state files {$douyinFullStateFile} / {$douyinIncrementalStateFile}\n";
            }
        }
        if ($eventType === 'douyin_followers') {
            $written = file_put_contents($douyinIncrementalStateFile, $currentSocialIncrementalSlot . PHP_EOL, LOCK_EX);
            if ($written === false) {
                $ok = false;
                echo "{$eventType}: failed to update state file {$douyinIncrementalStateFile}\n";
            }
        }
    }
}

http_response_code($ok ? 200 : 500);
