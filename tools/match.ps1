# Unattended testbed match: launch through Steam, O (start), P (all AI), Tab (view off our faction),
# F10 (speed x4), run for -Minutes, then close the game normally (prefs.sav is rewritten on exit). -LateMin > 0: press L
# (a scenario's mid-match macro, e.g. the late scenario's hegemony boost) that many minutes after the start.
# Keys go through keybd_event with scan codes after forcing the game window to the foreground:
# computer-use screenshots minimize the fullscreen game, so nothing here needs a screen capture.
param([double]$Minutes = 17, [int]$MenuSec = 14, [int]$LoadSec = 28, [double]$LateMin = 0)
Add-Type @'
using System; using System.Runtime.InteropServices;
public class K {
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
  public static void Tap(byte vk, byte scan) {
    keybd_event(vk, scan, 0x8, UIntPtr.Zero); System.Threading.Thread.Sleep(60);
    keybd_event(vk, scan, 0x8 | 0x2, UIntPtr.Zero);
  }
}
'@
function Log($m) { Write-Output ("[{0}] {1}" -f (Get-Date -Format HH:mm:ss), $m) }
function Game { Get-Process D4X -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1 }
function Focus {
  $p = Game
  if (-not $p) { Log 'D4X not running'; exit 1 }
  $h = $p.MainWindowHandle
  [K]::keybd_event(0x12, 0x38, 0, [UIntPtr]::Zero); [K]::keybd_event(0x12, 0x38, 2, [UIntPtr]::Zero)  # Alt tap lifts the foreground lock
  [K]::ShowWindow($h, 9) | Out-Null; [K]::SetForegroundWindow($h) | Out-Null
  Start-Sleep -Milliseconds 400
  if ([K]::GetForegroundWindow() -ne $h) { Log 'WARN: game window not in front' }
}
function Press($name, $vk, $scan) { Focus; [K]::Tap($vk, $scan); Log "pressed $name" }

if (-not (Game)) {
  Start-Process 'steam://rungameid/1605220'; Log 'launched through Steam'
  $t = 0; while (-not (Game) -and $t -lt 180) { Start-Sleep 2; $t += 2 }
  if (-not (Game)) { Log 'game window never appeared'; exit 1 }
  Log "window up after $t s, waiting $MenuSec s for the main menu"; Start-Sleep $MenuSec
}
Press 'O' 0x4F 0x18
Log "waiting $LoadSec s for the match to load"; Start-Sleep $LoadSec
Press 'P' 0x50 0x19
Start-Sleep 2
Press 'Tab' 0x09 0x0F
Start-Sleep 1
Press 'F10' 0x79 0x44
$start = Get-Date
Log "running $Minutes min"
# the L macro's effect, read from the live game.log (testbed ai-log): the largest hegemony in the bthreat rows after
# the press; -1 = no rows yet (no retry on that: a log that isn't live must not get L pressed twice)
$gameLog = Join-Path (Split-Path (Split-Path $PSScriptRoot)) 'game.log'
function MaxHeg($since) {
  try {
    $fs = [IO.File]::Open($gameLog, 'Open', 'Read', 'ReadWrite')
    $n = [Math]::Min($fs.Length, 3MB); $fs.Seek(-$n, 'End') | Out-Null
    $buf = New-Object byte[] $n; $fs.Read($buf, 0, $n) | Out-Null; $fs.Close()
    $txt = [Text.Encoding]::UTF8.GetString($buf)
  } catch { return -1 }
  $best = -1
  foreach ($m in [regex]::Matches($txt, 'e : bthreat, f : \w+, h : ([0-9.]+),.*?, g : ([0-9.]+)')) {
    if ([double]$m.Groups[2].Value -gt $since) { $best = [Math]::Max($best, [double]$m.Groups[1].Value) }
  }
  return $best
}
function LastG {
  try {
    $fs = [IO.File]::Open($gameLog, 'Open', 'Read', 'ReadWrite')
    $n = [Math]::Min($fs.Length, 200KB); $fs.Seek(-$n, 'End') | Out-Null
    $buf = New-Object byte[] $n; $fs.Read($buf, 0, $n) | Out-Null; $fs.Close()
    $ms = [regex]::Matches([Text.Encoding]::UTF8.GetString($buf), ', g : ([0-9.]+)\}')
    if ($ms.Count -gt 0) { return [double]$ms[$ms.Count - 1].Groups[1].Value }
  } catch {}
  return -1
}
$lateDone = $false; $lateTries = 0; $lateG = -1; $lateAt = $null; $lastSpeed = Get-Date
while (((Get-Date) - $start).TotalMinutes -lt $Minutes) {
  Start-Sleep 15
  if ($LateMin -gt 0 -and -not $lateDone -and ((Get-Date) - $start).TotalMinutes -ge $LateMin) {
    $lateG = LastG; Press 'L' 0x4C 0x26; Start-Sleep 1; Press 'F10' 0x79 0x44; $lateTries++; $lateDone = $true; $lateAt = Get-Date
  }
  # the press can miss (2026-10-24 17:30: nobody passed 14k, no leader all match): 90 s later no faction near the
  # boosted level (>= 25000) in fresh threat rows (90 s: the rows are throttled and 45 s saw none) -> press again, at most 3 presses
  if ($lateAt -and $lateTries -lt 3 -and ((Get-Date) - $lateAt).TotalSeconds -ge 90) {
    $h = MaxHeg $lateG
    if ($h -ge 25000) { Log "late boost seen (max hegemony $h)"; $lateAt = $null }
    elseif ($h -lt 0) { Log 'late boost: no threat rows after the press, not retrying'; $lateAt = $null }
    else { Log "late boost missing (max hegemony $h): pressing L again"; $lateG = LastG; Press 'L' 0x4C 0x26; Start-Sleep 1; Press 'F10' 0x79 0x44; $lateTries++; $lateAt = Get-Date }
  }
  # speed x4 again every minute (idempotent macro): match 33 (2026-10-25 02:18) stayed at x1 after the L press
  # (36 game min in 18 real, the match before 67)
  if (((Get-Date) - $lastSpeed).TotalSeconds -ge 60) { Press 'F10' 0x79 0x44; $lastSpeed = Get-Date }
  if (-not (Game)) { Log ("game gone after {0:n1} min (crash?)" -f ((Get-Date) - $start).TotalMinutes); exit 2 }
}
$p = Game
Log ("ran {0:n1} min, closing" -f ((Get-Date) - $start).TotalMinutes)
$p.CloseMainWindow() | Out-Null
if ($p.WaitForExit(30000)) { Log 'closed normally' } else { Stop-Process -Id $p.Id -Force; Log 'no exit in 30 s: killed' }
