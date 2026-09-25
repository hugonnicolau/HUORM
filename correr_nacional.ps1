# Corrida nacional no Windows. Equivalente ao correr_nacional.sh do macOS.
#
# Correr a partir da pasta FINAL:
#     .\correr_nacional.ps1
#     .\correr_nacional.ps1 -Processos 10     (plano Max)
#
# Pode ser interrompida. O --retomar salta o que já tem Document_Unique_PGx.json.

param(
    [int]$Processos = 3,
    [string]$Modelo = "glm-5.3-flash",
    [string]$Saida  = "out_nacional"
)

$ErrorActionPreference = "Stop"

# Sem isto o Python no Windows escreve a saida em cp1252. O pipeline imprime
# emojis (✅ ⚠️ ❌ 🔍) e nomes de medicamentos com acentos, e ao redirigir para
# ficheiro rebenta com UnicodeEncodeError — a meio da corrida, nao no arranque.
$env:PYTHONUTF8 = "1"

if (-not (Test-Path "RCMs_a_processar")) { Write-Host "falta RCMs_a_processar\"; exit 1 }
if (-not (Test-Path "markdown"))         { Write-Host "falta markdown\";         exit 1 }
if (-not (Test-Path "RCMprocessor\data\umls\MRCONSO.RRF")) {
    Write-Host "FALTA o MRCONSO em RCMprocessor\data\umls\MRCONSO.RRF"; exit 1
}

$nPdf = (Get-ChildItem "RCMs_a_processar\*.pdf").Count
$nMd  = (Get-ChildItem "markdown\*.md").Count
Write-Host "PDFs      : $nPdf"
Write-Host "markdown  : $nMd"
if ($nPdf -ne $nMd) {
    Write-Host ""
    Write-Host "AVISO: os numeros nao batem. Os sem markdown serao convertidos pelo"
    Write-Host "docling durante a corrida, o que a torna muito mais lenta."
    Write-Host ""
}

# ---------------------------------------------------------------- lotes
#
# Num ficheiro proprio, e nao num here-string. O PowerShell escreve um BOM
# (U+FEFF) a cabeca do texto que manda para o python, e o Python recusa-o.
# Quando isso aconteceu, a 21-09, os lotes nao foram regenerados, o script
# seguiu em frente e os processos arrancaram com lotes de uma corrida
# anterior — tres lotes de oito, ou seja 37% do corpus, sem ninguem dar por
# isso. O `exit` a seguir garante que isso nao se repete.
python fazer_lotes.py $Processos
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "A geracao dos lotes falhou. Nao arranco com lotes antigos." -ForegroundColor Red
    exit 1
}

$nLotes = (Get-ChildItem "lote_nac_*.txt").Count
if ($nLotes -ne $Processos) {
    Write-Host ""
    Write-Host "Ha $nLotes lotes para $Processos processos. Nao arranco." -ForegroundColor Red
    exit 1
}

$nLista = 0
Get-ChildItem "lote_nac_*.txt" | ForEach-Object {
    $nLista += (Get-Content $_.FullName | Where-Object { $_.Trim() -ne "" }).Count
}
if ($nLista -ne $nPdf) {
    Write-Host ""
    Write-Host "Os lotes somam $nLista documentos mas ha $nPdf PDFs. Nao arranco." -ForegroundColor Red
    exit 1
}
Write-Host "lotes verificados : $nLista documentos em $nLotes lotes"

Write-Host ""
Write-Host "=== arranque: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')   com $Processos processos ==="
Write-Host ""

for ($i = 0; $i -lt $Processos; $i++) {
    $n = "{0:D2}" -f $i
    $args = @(
        "-m", "RCMprocessor.batch_processor",
        "RCMs_a_processar", $Saida,
        "--model", $Modelo,
        "--markdown-dir", "markdown",
        "--file-list", "lote_nac_$n.txt",
        "--retomar"
    )
    $p = Start-Process -FilePath "python" -ArgumentList $args `
         -RedirectStandardOutput "log_nac_$n.txt" `
         -RedirectStandardError  "log_err_$n.txt" `
         -NoNewWindow -PassThru
    Write-Host "lote $n  pid $($p.Id)"
}

Write-Host ""
Write-Host "Os $Processos processos estao a correr."
Write-Host ""
Write-Host "IMPORTANTE: desliga a suspensao automatica do Windows antes de te ires embora."
Write-Host "  Definicoes > Sistema > Energia > Ecra e suspensao > Nunca"
Write-Host ""
Write-Host "Progresso :  .\ver_progresso.ps1"
Write-Host "Parar tudo:  Get-Process python | Stop-Process"
