$ErrorActionPreference = 'Stop'
$source = (Join-Path $env:GITHUB_WORKSPACE 'vendor-ct2').Replace('\', '/')
$prefix = (Join-Path $env:GITHUB_WORKSPACE 'ct2-install').Replace('\', '/')
$cuda = 'C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.8'
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'MSVC toolchain missing' }
$devcmd = Join-Path $vs 'Common7\Tools\VsDevCmd.bat'
cmd /s /c "`"$devcmd`" -arch=x64 -host_arch=x64 && set" | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') }
}
$env:CUDA_PATH = $cuda
$env:PATH = "$cuda\bin;$env:PATH"
$env:CTRANSLATE2_ROOT = $prefix
$env:CMAKE_BUILD_PARALLEL_LEVEL = '2'
python -m pip install 'cmake>=3.28,<4' ninja 'pybind11==2.13.6' setuptools wheel
if ($LASTEXITCODE -ne 0) { throw 'Build dependencies failed' }
python packaging/flash/prepare_source.py $source
if ($LASTEXITCODE -ne 0) { throw 'Source preparation failed' }
$cmakeArguments = @(
    '-S', $source, '-B', 'ct2-build', '-G', 'Ninja',
    '-DCMAKE_BUILD_TYPE=Release', "-DCMAKE_INSTALL_PREFIX=$prefix",
    '-DCMAKE_POLICY_VERSION_MINIMUM=3.5', '-DBUILD_CLI=OFF',
    '-DWITH_CUDA=ON', '-DWITH_CUDNN=OFF', '-DWITH_MKL=OFF', '-DWITH_DNNL=OFF',
    '-DWITH_RUY=ON', '-DOPENMP_RUNTIME=COMP', '-DWITH_FLASH_ATTN=ON',
    '-DCUDA_DYNAMIC_LOADING=ON', '-DCUDA_USE_STATIC_CUDA_RUNTIME=ON',
    "-DCUDA_TOOLKIT_ROOT_DIR=$cuda", '-DCUDA_ARCH_LIST:STRING=8.6',
    '-DCUDA_NVCC_FLAGS=-Xfatbin=-compress-all;-allow-unsupported-compiler'
)
& cmake @cmakeArguments
if ($LASTEXITCODE -ne 0) { throw 'CMake configuration failed' }
cmake --build ct2-build --target install --parallel 2
if ($LASTEXITCODE -ne 0) { throw 'Native compilation failed' }
$cache = Get-Content ct2-build/CMakeCache.txt -Raw
if ($cache -notmatch 'CUDA_ARCH_LIST:STRING=8[.]6') { throw 'Wrong GPU architecture in cache' }
if ($cache -notmatch 'WITH_FLASH_ATTN:BOOL=ON') { throw 'Flash build flag missing' }
Copy-Item "$prefix/bin/ctranslate2.dll" "$source/python/ctranslate2/"
Copy-Item "$source/README.md" "$source/python/"
python -m pip wheel "$source/python" --no-deps --no-build-isolation --wheel-dir flash-wheel
if ($LASTEXITCODE -ne 0) { throw 'Wheel build failed' }
Copy-Item ct2-build/CMakeCache.txt flash-wheel/
Copy-Item "$source/LICENSE" flash-wheel/CTRANSLATE2-LICENSE.txt
