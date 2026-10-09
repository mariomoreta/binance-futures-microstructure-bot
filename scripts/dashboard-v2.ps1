param([ValidateSet('start','status','stop','restart')][string]$Action='status')
$ErrorActionPreference='Stop'
$Root='C:\proyectos\binance-futures-dashboard-v2-worktree';$Front=Join-Path $Root 'frontend';$Port=3020;$State=Join-Path $Root '.dashboard-v2-runtime.json';$Log=Join-Path $Root 'dashboard-v2-3020.log'
function Listener { @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue|Select-Object -ExpandProperty OwningProcess -Unique) }
function NodePid([int]$Id){$p=Get-CimInstance Win32_Process -Filter "ProcessId=$Id" -ErrorAction SilentlyContinue;return ($null -ne $p -and $p.Name -eq 'node.exe')}
function StopOwned{
 if(-not(Test-Path $State)){throw 'No managed PID file; refusing to stop arbitrary processes'}
 $record=Get-Content $State -Raw|ConvertFrom-Json
 if($record.port -ne $Port -or $record.workspace -ne $Root){throw 'Registry identity mismatch'}
 $owners=Listener
 if($owners.Count -eq 0){Remove-Item $State;Write-Output 'Already stopped';return}
 if($owners.Count -ne 1 -or [int]$owners[0] -ne [int]$record.pid -or -not(NodePid ([int]$record.pid))){throw 'Port owner mismatch, refusing to stop'}
 Stop-Process -Id ([int]$record.pid) -ErrorAction Stop;Start-Sleep -Milliseconds 600
 if((Listener).Count -gt 0){throw 'Port still occupied after stop'}
 Remove-Item $State;Write-Output "Stopped own Dashboard V2 PID $($record.pid)"
}
switch($Action){
 'status' {$o=Listener;$managed=$false;if((Test-Path $State) -and $o.Count -eq 1){$v=Get-Content $State -Raw|ConvertFrom-Json;$managed=([int]$v.pid -eq [int]$o[0])};Write-Output "V2 http://127.0.0.1:$Port PID=$($o -join ',') managed=$managed"}
 'stop' {StopOwned}
 'start'{
  if((Listener).Count -gt 0){throw 'Canonical port 3020 is occupied; refusing to replace an unknown process'}
  if(-not(Test-Path (Join-Path $Front '.next\BUILD_ID'))){throw 'Build missing: npm run build required'}
  $cmd='cmd.exe /d /c "cd /d '+$Front+' && node .\node_modules\next\dist\bin\next start -p 3020 -H 127.0.0.1 >> '+$Log+' 2>&1"'
  $res=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=$cmd}
  if($res.ReturnValue -ne 0){throw "Launch error $($res.ReturnValue)"}
  $owners=@();for($i=0;$i -lt 35;$i++){Start-Sleep -Milliseconds 250;$owners=Listener;if($owners.Count -gt 0){break}}
  if($owners.Count -ne 1 -or -not(NodePid ([int]$owners[0]))){throw 'No identifiable Node listener after start'}
  @{workspace=$Root;port=$Port;pid=[int]$owners[0]}|ConvertTo-Json|Set-Content $State -Encoding UTF8
  Write-Output "V2 READY http://127.0.0.1:3020 PID=$($owners[0])"
 }
 'restart' {StopOwned;& $PSCommandPath start}
}