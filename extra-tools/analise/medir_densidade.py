"""Densidade de palavras portuguesas nos documentos retidos.
Replica _readability() do scanned_pdf_detector.py, com pdftotext -layout,
que foi exactamente como a triagem correu."""
import re, os, json, subprocess, sys
SRC="/sessions/gallant-clever-allen/mnt/ApresentaçãoV2/FINALV2/RCMs_a_processar"
OUT="/tmp/densidade.jsonl"
_COMMON=("de","que","para","não","com","dose","doentes","medicamento","utilização","efeitos")
_PATS=tuple(re.compile(r"\b"+w+r"\b", re.IGNORECASE) for w in _COMMON)
def readability(body):
    if not body: return {"word_density":0.0,"letter_fraction":0.0,"control_fraction":0.0}
    n=len(body)
    w=sum(len(p.findall(body)) for p in _PATS)
    l=sum(ch.isalpha() for ch in body)
    c=sum(1 for ch in body if ord(ch)<32 and ch not in "\n\r\t")
    return {"word_density":round(w/n*1000,2),"letter_fraction":round(l/n,3),
            "control_fraction":round(c/n,3)}
feitos=set()
if os.path.exists(OUT):
    for ln in open(OUT,encoding="utf-8"):
        try: feitos.add(json.loads(ln)["f"])
        except Exception: pass
todo=[f for f in sorted(os.listdir(SRC)) if f.endswith(".pdf") and f not in feitos]
print("por fazer:", len(todo), flush=True)
with open(OUT,"a",encoding="utf-8") as fh:
    for i,f in enumerate(todo,1):
        try:
            r=subprocess.run(["pdftotext","-layout",os.path.join(SRC,f),"-"],
                             capture_output=True, text=True, timeout=120)
            m=readability(re.sub(r"\s+"," ",r.stdout).strip())
        except Exception as e:
            m={"erro":str(e)[:60]}
        fh.write(json.dumps({"f":f,**m},ensure_ascii=False)+"\n")
        if i%300==0: fh.flush(); print(f"  {i}", flush=True)
