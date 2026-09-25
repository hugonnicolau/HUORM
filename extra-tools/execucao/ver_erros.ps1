# Estado da rede na corrida nacional.
#
#     .\ver_erros.ps1
#
# Conta as falhas de ligacao nos logs dos processos e mostra as ultimas.
# Serve para comparar antes e depois de mexer na rede (VPN, router, Cloudflare).

param([string]$Saida = "out_nacional")

$env:PYTHONUTF8 = "1"

$logs = Get-ChildItem "log_nac_*.txt" -ErrorAction SilentlyContinue
if (-not $logs) {
    Write-Host "Nao ha ficheiros log_nac_*.txt nesta pasta." -ForegroundColor Yellow
    exit
}

$falhas = @(Select-String -Path $logs -Pattern "falha de liga" -Encoding utf8)
$feitos = @(Get-ChildItem $Saida -Directory -ErrorAction SilentlyContinue).Count
$vivos  = @(Get-Process python -ErrorAction SilentlyContinue).Count

Write-Host ""
Write-Host "documentos concluidos   : $feitos de 5623"
Write-Host "processos python vivos  : $vivos"
Write-Host "falhas de ligacao (total): $($falhas.Count)"
Write-Host ""

if ($falhas.Count -gt 0) {
    $ultima = ($logs | Sort-Object LastWriteTime -Descending)[0].LastWriteTime
    Write-Host "ultima escrita num log  : $ultima"
    Write-Host ""
    Write-Host "ultimas 5 falhas:"
    $falhas | Select-Object -Last 5 | ForEach-Object {
        Write-Host ("   " + $_.Filename + ": " + $_.Line.Trim())
    }
    Write-Host ""
}

Write-Host "REFERENCIA (21-09, 09:10 as 13:40, com o Cloudflare ligado):"
Write-Host "   22 falhas em ~4,5 horas com 10 processos, ou seja cerca de 5 por hora."
Write-Host ""
Write-Host "Corre isto 15 a 20 minutos depois de mexeres na rede."
Write-Host "Se o numero subir poucas unidades, esta normal - a pipeline repete sozinha."
Write-Host "Se subir dezenas na mesma janela, a rede ficou pior: volta atras."
Write-Host ""
