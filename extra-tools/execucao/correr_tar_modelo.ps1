# Cinco execucoes do referencia com um modelo, para medir a concordancia.
#
#   .\correr_tar_modelo.ps1 -Modelo "gpt-oss:120b" -Prefixo "out_gptoss"
#   .\correr_tar_modelo.ps1 -Modelo "<tag-do-deepseek>" -Prefixo "out_ds"
#
# Abre seis janelas; cada uma corre os cinco lotes em fila para o seu
# subconjunto dos 17 documentos. Reutiliza os grep_*.txt gerados pelo
# lotes_referencia.py e o markdown ja convertido, por isso nao ha conversao
# nenhuma a repetir.
#
# Cria out_<prefixo>_rep1 ... rep5. Se alguma ja existir, o batch_processor
# escreve por cima sem avisar — mudar o prefixo, nao apagar a pasta antiga,
# porque pode ser a de outro modelo.

param(
    [Parameter(Mandatory=$true)][string]$Modelo,
    [Parameter(Mandatory=$true)][string]$Prefixo,
    [int]$Execucoes = 5,
    [int]$Janelas = 6
)

if (-not (Test-Path "grep_00.txt")) {
    Write-Host "Faltam os grep_*.txt. Corre primeiro:  python lotes_referencia.py $Janelas"
    exit 1
}

Write-Host "modelo    : $Modelo"
Write-Host "saidas    : ${Prefixo}_rep1 .. ${Prefixo}_rep$Execucoes"
Write-Host "janelas   : $Janelas"
Write-Host ""

0..($Janelas - 1) | ForEach-Object {
    $lote = "grep_{0:d2}.txt" -f $_
    $passos = 1..$Execucoes | ForEach-Object {
        "python -m RCMprocessor.batch_processor TestSet ${Prefixo}_rep$_ " +
        "--model `"$Modelo`" --markdown-dir markdown_referencia --file-list $lote"
    }
    $comando = $passos -join "; "
    Start-Process powershell -ArgumentList '-NoExit', '-Command', $comando
}

Write-Host "Lancadas $Janelas janelas. Quando todas fecharem o trabalho:"
Write-Host ""
Write-Host "  python medir_concordancia.py ${Prefixo}_rep1 ${Prefixo}_rep2 ${Prefixo}_rep3 ${Prefixo}_rep4 ${Prefixo}_rep5"
