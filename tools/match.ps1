# Unattended testbed match: launch through Steam, O (start), P (all AI), Tab (view off our faction),
# F10 (speed x4), run for -Minutes, then close the game normally (prefs.sav is rewritten on exit).
# Keys go through keybd_event with scan codes after forcing the game window to the foreground:
# computer-use screenshots minimize the fullscreen game, so nothing here needs a screen capture.
param([double]$Minutes = 17, [int]$MenuSec = 20, [int]$LoadSec = 37)
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
while (((Get-Date) - $start).TotalMinutes -lt $Minutes) {
  Start-Sleep 15
  if (-not (Game)) { Log ("game gone after {0:n1} min (crash?)" -f ((Get-Date) - $start).TotalMinutes); exit 2 }
}
$p = Game
Log ("ran {0:n1} min, closing" -f ((Get-Date) - $start).TotalMinutes)
$p.CloseMainWindow() | Out-Null
if ($p.WaitForExit(30000)) { Log 'closed normally' } else { Stop-Process -Id $p.Id -Force; Log 'no exit in 30 s: killed' }
