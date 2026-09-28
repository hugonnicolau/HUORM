#!/usr/bin/env python3
"""Aplica a opcao B ao corpus: tira os 14 representantes cujo registo nao esta
no indice do INFOMED e troca 8 representantes orfaos pelo documento do indice
com o mesmo texto. Nada e apagado: o que sai vai para FINALV2/fora_do_indice/,
e cada movimento fica registado em fora_do_indice/MOVIMENTOS.csv.

Uso, a partir de FINALV2:  python extra-tools/analise/fora_do_indice/aplicar_exclusao.py
Os PDF novos vem de WINDOWS/DOCUMENTS_FINAL/downloads/rcms (texto verificado
igual ao do representante antigo)."""
import csv, os, shutil, sys
AQUI = os.path.dirname(os.path.abspath(__file__))
FINAL = os.path.abspath(os.path.join(AQUI, "..", "..", ".."))
ORIG_PDF = os.path.abspath(os.path.join(FINAL, "..", "WINDOWS", "DOCUMENTS_FINAL", "downloads", "rcms"))
FORA = os.path.join(FINAL, "fora_do_indice")
EXC = [r["ficheiro"][:-4] for r in csv.DictReader(open(os.path.join(AQUI, "exclusao.csv"), encoding="utf-8")) if r["papel"] == "representante"]
TROCA = [(r["representante_antigo"][:-4], r["representante_novo"][:-4]) for r in csv.DictReader(open(os.path.join(AQUI, "representantes_novos.csv"), encoding="utf-8"))]
assert len(EXC) == 14 and len(TROCA) == 8
log = []
def mover(a, b, motivo):
    if not os.path.exists(a):
        if os.path.exists(b): return
        sys.exit(f"falta {a}")
    os.makedirs(os.path.dirname(b), exist_ok=True)
    assert not os.path.exists(b), b
    shutil.move(a, b); log.append((os.path.relpath(a, FINAL), os.path.relpath(b, FINAL), motivo))
for d in EXC:
    mover(f"{FINAL}/out_nacional/{d}", f"{FORA}/out_nacional/{d}", "registo fora do indice")
    mover(f"{FINAL}/RCMs_a_processar/{d}.pdf", f"{FORA}/RCMs_a_processar/{d}.pdf", "registo fora do indice")
    mover(f"{FINAL}/markdown/{d}.md", f"{FORA}/markdown/{d}.md", "registo fora do indice")
for a, b in TROCA:
    mover(f"{FINAL}/out_nacional/{a}", f"{FINAL}/out_nacional/{b}", f"representante trocado (texto igual a {a})")
    mover(f"{FINAL}/RCMs_a_processar/{a}.pdf", f"{FORA}/RCMs_a_processar/{a}.pdf", f"representante substituido por {b}")
    if not os.path.exists(f"{FINAL}/RCMs_a_processar/{b}.pdf"):
        shutil.copy2(f"{ORIG_PDF}/{b}.pdf", f"{FINAL}/RCMs_a_processar/{b}.pdf")
        log.append((os.path.relpath(f"{ORIG_PDF}/{b}.pdf", FINAL), f"RCMs_a_processar/{b}.pdf", f"copiado: substitui {a}"))
    mover(f"{FINAL}/markdown/{a}.md", f"{FINAL}/markdown/{b}.md", f"representante trocado (texto igual a {a})")
novo = not os.path.exists(f"{FORA}/MOVIMENTOS.csv")
with open(f"{FORA}/MOVIMENTOS.csv", "a", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    if novo: w.writerow(["de", "para", "motivo"])
    w.writerows(log)
print(f"{len(log)} movimentos; out_nacional: {sum(1 for x in os.listdir(FINAL + '/out_nacional') if os.path.isdir(FINAL + '/out_nacional/' + x))} pastas;"
      f" RCMs_a_processar: {sum(1 for x in os.listdir(FINAL + '/RCMs_a_processar') if x.endswith('.pdf'))} PDF;"
      f" markdown: {sum(1 for x in os.listdir(FINAL + '/markdown') if x.endswith('.md'))} md")
