# Instalador do QUANT para Windows. Use pelo instalar.cmd (dois cliques), que ja
# contorna o bloqueio de scripts do PowerShell.
#
#   instalar.cmd                    # instala tudo, pergunta a chave e se quer agendar
#   instalar.cmd -SemPerguntas      # sem perguntas (nao agenda; .env fica para preencher)
#
# O que faz (pode rodar de novo quantas vezes quiser):
#   1. Python 3.11+  - usa o que ja existir; senao instala o 3.12 pelo winget
#   2. Node.js 18+   - idem, Node LTS pelo winget
#   3. .venv e dependencias Python (requirements.txt)
#   4. dependencias do site (npm install)
#   5. .env a partir do .env.example (pergunta a chave do LLM)
#   6. roda os testes para conferir a instalacao
#   7. oferece ativar a coleta automatica (Agendador de Tarefas)
param([switch]$SemPerguntas)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

function Passo($texto) { Write-Host ""; Write-Host "==> $texto" -ForegroundColor Yellow }
function Ok($texto) { Write-Host "    $texto" -ForegroundColor Green }
function Falha($texto) { Write-Host ""; Write-Host "ERRO: $texto" -ForegroundColor Red; exit 1 }

function Atualizar-Path {
  # Programas recem-instalados pelo winget so aparecem no PATH de terminais novos.
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

function Versao-Python($exe, $extras) {
  try {
    $v = & $exe @extras -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if ($LASTEXITCODE -eq 0 -and $v) { return [version]($v | Select-Object -Last 1) }
  } catch { }
  return $null
}

function Achar-Python {
  $candidatos = @()
  if (Get-Command py -ErrorAction SilentlyContinue) {
    $candidatos += [pscustomobject]@{ Exe = "py"; Extras = @("-3.12") }
    $candidatos += [pscustomobject]@{ Exe = "py"; Extras = @("-3") }
  }
  foreach ($nome in "python", "python3") {
    $cmd = Get-Command $nome -ErrorAction SilentlyContinue
    # O "python" da pasta WindowsApps e so um atalho para a Microsoft Store.
    if ($cmd -and $cmd.Source -notlike "*WindowsApps*") { $candidatos += [pscustomobject]@{ Exe = $cmd.Source; Extras = @() } }
  }
  $locais = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe", "$env:ProgramFiles\Python3*\python.exe" -ErrorAction SilentlyContinue
  foreach ($l in $locais) { $candidatos += [pscustomobject]@{ Exe = $l.FullName; Extras = @() } }
  foreach ($c in $candidatos) {
    $v = Versao-Python $c.Exe $c.Extras
    if ($v -and $v -ge [version]"3.11") { return $c }
  }
  return $null
}

function Tem-Winget { return [bool](Get-Command winget -ErrorAction SilentlyContinue) }

# ------------------------------------------------------------------ 1. Python
Passo "1/7 Python 3.11 ou mais novo"
$py = Achar-Python
if (-not $py) {
  if (-not (Tem-Winget)) { Falha "Python nao encontrado. Instale o Python 3.12 em https://www.python.org/downloads/ (marque 'Add python.exe to PATH') e rode o instalador de novo." }
  Write-Host "    Instalando o Python 3.12 (winget)..."
  winget install --id Python.Python.3.12 -e --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
  Atualizar-Path
  $py = Achar-Python
  if (-not $py) { Falha "O Python foi instalado, mas nao foi encontrado. Feche esta janela e rode o instalador de novo." }
}
Ok ("Python " + (Versao-Python $py.Exe $py.Extras) + " (" + $py.Exe + " " + ($py.Extras -join " ") + ")")

# ------------------------------------------------------------------ 2. Node
Passo "2/7 Node.js 18 ou mais novo"
function Versao-Node {
  $node = Get-Command node -ErrorAction SilentlyContinue
  if (-not $node) { return $null }
  try { return [version]((& $node.Source --version).TrimStart("v")) } catch { return $null }
}
$vNode = Versao-Node
if (-not $vNode -or $vNode -lt [version]"18.0") {
  if (-not (Tem-Winget)) { Falha "Node.js 18+ nao encontrado. Instale a versao LTS em https://nodejs.org/ e rode o instalador de novo." }
  Write-Host "    Instalando o Node.js LTS (winget)..."
  winget install --id OpenJS.NodeJS.LTS -e --silent --accept-package-agreements --accept-source-agreements | Out-Host
  Atualizar-Path
  $vNode = Versao-Node
  if (-not $vNode) { Falha "O Node.js foi instalado, mas nao foi encontrado. Feche esta janela e rode o instalador de novo." }
}
Ok "Node.js $vNode"
$npm = (Get-Command npm.cmd -ErrorAction Stop).Source  # npm.cmd: nao esbarra na politica de scripts

# ------------------------------------------------------------------ 3. .venv
Passo "3/7 Ambiente Python (.venv) e dependencias"
# O Windows limita caminhos a 260 caracteres, e o SDK da Anthropic tem arquivos de
# ~157 caracteres dentro da .venv: com a pasta do projeto num caminho longo (ex.:
# ...\OneDrive\Area de Trabalho\Faculdade\...), o pip falha no meio da instalacao.
$chaveFs = "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem"
function Caminhos-Longos { return (Get-ItemProperty $chaveFs -Name LongPathsEnabled -ErrorAction SilentlyContinue).LongPathsEnabled -eq 1 }
$limitePasta = 90
if (-not (Caminhos-Longos) -and $raiz.Length -gt $limitePasta) {
  Write-Host "    A pasta do projeto tem $($raiz.Length) caracteres:" -ForegroundColor Yellow
  Write-Host "      $raiz"
  Write-Host "    O Windows limita caminhos a 260 caracteres e algumas dependencias tem nomes muito longos."
  Write-Host "    Solucoes: (1) ativar caminhos longos no Windows (uma vez, pede administrador) ou"
  Write-Host "              (2) mover a pasta para um caminho curto, como C:\QUANT, e rodar o instalador de novo."
  if ($SemPerguntas) { Falha "pasta do projeto em caminho longo demais (mais de $limitePasta caracteres)." }
  $r = Read-Host "    Ativar caminhos longos no Windows agora? [S/n]"
  if ($r -match "^[nN]") { Falha "mova a pasta para um caminho curto (ex.: C:\QUANT) e rode o instalador de novo." }
  Start-Process powershell -Verb RunAs -Wait -ArgumentList "-NoProfile -Command `"New-ItemProperty -Path '$chaveFs' -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force | Out-Null`""
  if (-not (Caminhos-Longos)) { Falha "nao foi possivel ativar os caminhos longos. Mova a pasta para um caminho curto (ex.: C:\QUANT)." }
  Ok "caminhos longos ativados no Windows"
}
$venvPython = Join-Path $raiz ".venv\Scripts\python.exe"
if ((Test-Path $venvPython) -and -not (Versao-Python $venvPython @())) {
  Write-Host "    .venv quebrada (o Python dela sumiu): recriando..."
  Remove-Item -Recurse -Force (Join-Path $raiz ".venv")
}
if (-not (Test-Path $venvPython)) { & $py.Exe @($py.Extras) -m venv .venv; if ($LASTEXITCODE) { Falha "nao foi possivel criar a .venv" } }
& $venvPython -m pip install --disable-pip-version-check -q --upgrade pip
& $venvPython -m pip install --disable-pip-version-check -q -r requirements.txt
if ($LASTEXITCODE) { Falha "pip install falhou (veja a mensagem acima; sem internet?)" }
Ok "dependencias Python instaladas"

# ------------------------------------------------------------------ 4. npm
Passo "4/7 Dependencias do site (npm install)"
& $npm install --no-fund --no-audit | Out-Host
if ($LASTEXITCODE) { Falha "npm install falhou (veja a mensagem acima; sem internet?)" }
Ok "dependencias do site instaladas"

# ------------------------------------------------------------------ 5. .env
Passo "5/7 Configuracao (.env)"
$env_ = Join-Path $raiz ".env"
if (-not (Test-Path $env_)) { Copy-Item (Join-Path $raiz ".env.example") $env_; Ok ".env criado a partir do .env.example" } else { Ok ".env ja existe (mantido)" }
$temChave = Select-String -Path $env_ -Pattern "^LLM_API_KEY=\S" -Quiet
if (-not $temChave -and -not $SemPerguntas) {
  Write-Host "    Sem a chave do LLM o QUANT coleta noticias, mas nao analisa."
  $chave = Read-Host "    Cole a chave da API (OpenAI, comeca com sk-) ou aperte Enter para pular"
  if ($chave.Trim()) {
    $linhas = Get-Content $env_ -Encoding UTF8 | ForEach-Object { if ($_ -match "^LLM_API_KEY=") { "LLM_API_KEY=$($chave.Trim())" } else { $_ } }
    # UTF-8 sem BOM (o Set-Content do PowerShell 5.1 poria um BOM no inicio).
    [IO.File]::WriteAllLines($env_, [string[]]$linhas, (New-Object Text.UTF8Encoding $false))
    Ok "chave gravada no .env (fica so neste computador; o .env nao vai para o git)"
  }
} elseif ($temChave) { Ok "chave do LLM configurada" }
if (-not (Select-String -Path $env_ -Pattern "^LLM_API_KEY=\S" -Quiet)) {
  Write-Host "    Lembrete: para a IA funcionar, preencha LLM_API_KEY no arquivo .env." -ForegroundColor Yellow
}

# ------------------------------------------------------------------ 6. testes
Passo "6/7 Conferindo a instalacao (testes automaticos, sem internet e sem custo)"
& $venvPython -m pytest -q -p no:cacheprovider | Select-Object -Last 1 | Out-Host
if ($LASTEXITCODE) { Write-Host "    Algum teste falhou: a instalacao pode ter problema. Veja: .venv\Scripts\python -m pytest" -ForegroundColor Yellow } else { Ok "tudo certo" }

# ------------------------------------------------------------------ 7. agendamento
Passo "7/7 Coleta automatica"
$agendado = Get-ScheduledTask -TaskName "QUANT - coleta automatica" -ErrorAction SilentlyContinue
$pastaAgendada = if ($agendado) { $agendado.Actions[0].WorkingDirectory } else { $null }
if ($agendado -and $pastaAgendada -eq $raiz) {
  Ok "ja esta agendada para esta pasta"
} elseif ($agendado) {
  # Outra copia do projeto neste PC: o agendamento e um so (vale para uma pasta).
  Write-Host "    A coleta automatica deste computador aponta para outra pasta: $pastaAgendada" -ForegroundColor Yellow
  Write-Host "    Para passar a usar esta pasta, rode agendar.cmd daqui (o agendamento e um so por computador)."
} elseif (-not $SemPerguntas) {
  $resposta = Read-Host "    Ativar a coleta automatica a cada 30 minutos (enquanto o PC estiver ligado)? [S/n]"
  if ($resposta -notmatch "^[nN]") {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "agendar-windows.ps1")
  } else { Write-Host "    Para ativar depois: agendar.cmd" }
} else { Write-Host "    Para ativar: agendar.cmd" }

Write-Host ""
Write-Host "Pronto! Para abrir o QUANT, de dois cliques em QUANT.cmd (abre o navegador em http://127.0.0.1:5173)." -ForegroundColor Green
