# Progresso da corrida nacional.
#     .\ver_progresso.ps1
#
# O trabalho esta no progresso.py. Aqui so se chama, porque meter Python dentro
# de um here-string do PowerShell mete um BOM a cabeca e o Python recusa-o.

param([string]$Saida = "out_nacional", [int]$Janela = 120)

$env:PYTHONUTF8 = "1"

python progresso.py $Saida $Janela

Write-Host ""
$n = @(Get-Process python -ErrorAction SilentlyContinue).Count
Write-Host "processos python vivos: $n"
