param(
    [ValidateSet('cpu', 'cuda')][string]$Device = 'cuda',
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'MAJIMeeting/runtime'),
    [string]$ModelRoot = (Join-Path $env:LOCALAPPDATA 'MAJIMeeting/models/community-1'),
    [switch]$SkipModel
)
$ErrorActionPreference = 'Stop'
$env:PYANNOTE_METRICS_ENABLED = 'false'
$env:OTEL_SDK_DISABLED = 'true'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$python = Join-Path $RuntimeRoot 'Scripts/python.exe'
if (-not (Test-Path $python)) {
    py -3.11 -m venv $RuntimeRoot
    if ($LASTEXITCODE -ne 0) { throw 'Installez Python 3.11 x64 avec le lanceur py, puis relancez ce script.' }
}
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Installation de pip impossible.' }
$index = if ($Device -eq 'cuda') { 'https://download.pytorch.org/whl/cu128' } else { 'https://download.pytorch.org/whl/cpu' }
$variant = if ($Device -eq 'cuda') { 'cu128' } else { 'cpu' }
& $python -m pip install "torch==2.8.0+$variant" "torchaudio==2.8.0+$variant" --index-url $index
if ($LASTEXITCODE -ne 0) { throw 'Installation de PyTorch impossible.' }
& $python -m pip install 'pyannote.audio==4.0.7' 'torchcodec==0.7.0' 'huggingface-hub>=0.28.1,<2'
if ($LASTEXITCODE -ne 0) { throw 'Installation de Community-1 impossible.' }
& $python -c 'import sys, torch; from pyannote.audio import Pipeline; print("Runtime importe, CUDA disponible:", torch.cuda.is_available()); sys.exit("CUDA indisponible : verifiez le pilote NVIDIA ou choisissez CPU." if sys.argv[1] == "cuda" and not torch.cuda.is_available() else 0)' $Device
if ($LASTEXITCODE -ne 0) { throw 'Le runtime ne peut pas charger pyannote.audio.' }
if (-not $SkipModel) {
    Write-Host 'Acceptez les conditions sur https://huggingface.co/pyannote/speaker-diarization-community-1 avant de continuer.'
    $download = @'
import getpass, sys
from huggingface_hub import snapshot_download
snapshot_download('pyannote/speaker-diarization-community-1',
                  token=getpass.getpass('Jeton Hugging Face (lecture, non conserve): '), local_dir=sys.argv[1])
'@
    & $python -c $download $ModelRoot
    if ($LASTEXITCODE -ne 0) { throw 'Telechargement refuse ou interrompu ; verifiez les conditions et votre jeton.' }
    $env:HF_HUB_OFFLINE = '1'
    & $python -c 'import sys; from pyannote.audio import Pipeline; Pipeline.from_pretrained(sys.argv[1]); print("Modele local charge hors ligne")' $ModelRoot
    if ($LASTEXITCODE -ne 0) { throw 'Le modele local ne peut pas etre charge hors ligne.' }
}
Write-Host "Runtime : $python"
Write-Host "Modele : $ModelRoot"
Write-Host 'Choisissez ces chemins dans MAJIMeeting > Distinguer automatiquement les interlocuteurs.'
