"""
Select the RCMs of a given list of active substances from the Infomed corpus.

Why not search by the Portuguese name
-------------------------------------
The Portuguese name in Infomed does not match the name a pharmacogenomics list
uses, and the mismatches are not cosmetic:

    requested            Infomed                     English INN
    Simvastatina         Sinvastatina                simvastatin
    Succinilcolina       Cloreto de suxametónio      suxamethonium
    Ondansetrona         Ondansetrom                 ondansetron
    Tacrolímus           Tacrolímus                  tacrolimus

Searching "succinil" in the Portuguese column returns *Proteínosuccinilato de
ferro* — an iron salt, not a neuromuscular blocker. The same class of error as
"iron" matching "spironolactone".

So the anchor is the English INN carried in the ATC label (`atc_labels`, e.g.
"M03AB01 - suxamethonium"), which comes from the WHO ATC index and is therefore
a chemical identifier rather than free text. The Portuguese name is used only
as a secondary route, and every match records which route found it so the
selection can be audited.

Matching is on whole words. Without that, "codeine" matches
"dihydrocodeine" and the selection quietly acquires a different drug.

Usage
-----
    python -m RCMprocessor.select_by_substance \\
        --dataset INFOMEDDATASET \\
        --destino mluis \\
        --lista compostos.txt        # optional; defaults to PGX_COMPOUNDS

Outputs, written to `<destino>/_selecao/`:

    selecao.csv          one row per RCM copied, with the match route
    por_composto.csv     one row per requested compound, found or not
    nao_encontrados.csv  the compounds with no RCM, for manual follow-up
    relatorio.md         readable summary
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

from .substance_utils import normalize

# --------------------------------------------------------------------------
# The requested compounds, each paired with its English INN.
#
# The INN is what does the work; the Portuguese name is kept so the report
# speaks the same language as the request. Where the two differ the difference
# is the whole point — see the module docstring.
# --------------------------------------------------------------------------
PGX_COMPOUNDS: list[tuple[str, str]] = [
    ("Abacavir", "abacavir"),
    ("Acenocumarol", "acenocoumarol"),
    ("Alopurinol", "allopurinol"),
    ("Amitriptilina", "amitriptyline"),
    ("Aripiprazol", "aripiprazole"),
    ("Atazanavir", "atazanavir"),
    ("Atomoxetina", "atomoxetine"),
    ("Azatioprina", "azathioprine"),
    ("Belinostate", "belinostat"),
    ("Brexpiprazol", "brexpiprazole"),
    ("Capecitabina", "capecitabine"),
    ("Carbamazepina", "carbamazepine"),
    ("Carisoprodol", "carisoprodol"),
    ("Celecoxib", "celecoxib"),
    ("Citalopram", "citalopram"),
    ("Clomipramina", "clomipramine"),
    ("Clopidogrel", "clopidogrel"),
    ("Clorzoxazona", "chlorzoxazone"),
    ("Codeína", "codeine"),
    ("Dapsona", "dapsone"),
    ("Desflurano", "desflurane"),
    ("Dexlansoprazol", "dexlansoprazole"),
    ("Diazepam", "diazepam"),
    ("Dolutegravir", "dolutegravir"),
    ("Doxepina", "doxepin"),
    ("Efavirenz", "efavirenz"),
    ("Enflurano", "enflurane"),
    ("Escitalopram", "escitalopram"),
    ("Esomeprazol", "esomeprazole"),
    ("Fenitoína", "phenytoin"),
    ("Fentanilo", "fentanyl"),
    ("Fluorouracilo", "fluorouracil"),
    ("Flurbiprofeno", "flurbiprofen"),
    ("Fluvoxamina", "fluvoxamine"),
    ("Halotano", "halothane"),
    ("Hidralazina", "hydralazine"),
    ("Ibuprofeno", "ibuprofen"),
    ("Imipramina", "imipramine"),
    ("Irinotecano", "irinotecan"),
    ("Isoflurano", "isoflurane"),
    ("Ivacaftor", "ivacaftor"),
    ("Lornoxicam", "lornoxicam"),
    ("Mefenamato", "mefenamic acid"),
    ("Meloxicam", "meloxicam"),
    ("Mercaptopurina", "mercaptopurine"),
    ("Metoxiflurano", "methoxyflurane"),
    ("Nortriptilina", "nortriptyline"),
    ("Omeprazol", "omeprazole"),
    ("Ondansetrona", "ondansetron"),
    ("Oxcarbazepina", "oxcarbazepine"),
    ("Oxicodona", "oxycodone"),
    ("Pantoprazol", "pantoprazole"),
    ("Paroxetina", "paroxetine"),
    ("Peginterferão alfa-2a", "peginterferon alfa-2a"),
    ("Peginterferão alfa-2b", "peginterferon alfa-2b"),
    ("Piroxicam", "piroxicam"),
    ("Pitolisant", "pitolisant"),
    ("Protriptilina", "protriptyline"),
    ("Rabeprazol", "rabeprazole"),
    ("Rasburicase", "rasburicase"),
    ("Ribavirina", "ribavirin"),
    ("Risperidona", "risperidone"),
    ("Rosuvastatina", "rosuvastatin"),
    ("Sevoflurano", "sevoflurane"),
    ("Simvastatina", "simvastatin"),
    ("Siponimod", "siponimod"),
    ("Succinilcolina", "suxamethonium"),
    ("Tacrolímus", "tacrolimus"),
    ("Tafenoquina", "tafenoquine"),
    ("Tamoxifeno", "tamoxifen"),
    ("Teofilina", "theophylline"),
    ("Tioguanina", "tioguanine"),
    ("Tramadol", "tramadol"),
    ("Tropisetrona", "tropisetron"),
    ("Varfarina", "warfarin"),
    ("Venlafaxina", "venlafaxine"),
    ("Voriconazol", "voriconazole"),
    ("Vortioxetina", "vortioxetine"),
]

# Spelling variants Infomed uses for the same substance. Only variants that
# the INN route cannot reach are listed; each was confirmed against the corpus
# rather than assumed.
VARIANTES_PT: dict[str, tuple[str, ...]] = {
    "Simvastatina": ("sinvastatina",),
    "Ondansetrona": ("ondansetrom",),
    "Tropisetrona": ("tropisetrom",),
    "Succinilcolina": ("suxametonio", "cloreto de suxametonio"),
    "Mefenamato": ("acido mefenamico",),
    "Tioguanina": ("tioguanina", "6-tioguanina"),
    "Fenitoína": ("fenitoina",),
}

# tioguanine is spelled thioguanine in some sources.
VARIANTES_EN: dict[str, tuple[str, ...]] = {
    "Tioguanina": ("thioguanine",),
    "Mefenamato": ("mefenamic",),
}


def _word_regex(termo: str) -> re.Pattern:
    """Whole-word matcher, tolerant of the hyphens INNs carry.

    `alfa-2a` must match `alfa 2a`; `\\b` alone would not, and a bare
    substring search would let "codeine" match "dihydrocodeine".
    """
    partes = [re.escape(p) for p in re.split(r"[\s\-]+", normalize(termo)) if p]
    if not partes:
        return re.compile(r"(?!)")
    return re.compile(r"(?<![a-z0-9])" + r"[\s\-]*".join(partes) + r"(?![a-z0-9])")


class Selector:
    def __init__(self, compostos: list[tuple[str, str]]):
        self.compostos = compostos
        self.padroes: dict[str, list[tuple[str, re.Pattern]]] = {}

        for pt, en in compostos:
            padroes = [("INN", _word_regex(en))]
            padroes += [("INN", _word_regex(v)) for v in VARIANTES_EN.get(pt, ())]
            padroes.append(("PT", _word_regex(pt)))
            padroes += [("PT", _word_regex(v)) for v in VARIANTES_PT.get(pt, ())]
            self.padroes[pt] = padroes

    def match(self, substancia_pt: str, atc_label: str) -> list[tuple[str, str]]:
        """Return [(compound, route)] for every compound this row contains."""
        alvo_pt = normalize(substancia_pt)
        alvo_en = normalize(atc_label)
        encontrados = []

        for pt, _ in self.compostos:
            for rota, padrao in self.padroes[pt]:
                campo = alvo_en if rota == "INN" else alvo_pt
                if padrao.search(campo):
                    encontrados.append((pt, rota))
                    break
        return encontrados


def carregar_lista(caminho: Path) -> list[tuple[str, str]]:
    """Read a compound list: `Portuguese name[<TAB or ;>english inn]`.

    Without an INN the Portuguese name is used for both, which is weaker —
    the report says so.
    """
    compostos = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = re.sub(r"^\s*\d+[.)]?\s+", "", linha.strip())
        if not linha or linha.startswith("#"):
            continue
        partes = re.split(r"\t|;|\|", linha)
        pt = partes[0].strip()
        en = partes[1].strip() if len(partes) > 1 and partes[1].strip() else pt
        compostos.append((pt, en))
    return compostos


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy the RCMs of a list of active substances out of the "
                    "Infomed corpus."
    )
    parser.add_argument("--dataset", required=True,
                        help="INFOMEDDATASET folder (with medicamentos.csv)")
    parser.add_argument("--destino", required=True,
                        help="folder to copy the selected RCMs into")
    parser.add_argument("--lista", default=None,
                        help="compound list file; defaults to PGX_COMPOUNDS")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be copied, copy nothing")
    parser.add_argument("--um-por-composto", action="store_true",
                        help="copy a single representative RCM per compound "
                             "instead of every match")
    parser.add_argument("--impressoes", default=None,
                        help="preflight impressoes.jsonl, used to rank "
                             "candidates by text length and skip unusable ones")
    args = parser.parse_args()

    dataset = Path(args.dataset).resolve()
    csv_path = dataset / "medicamentos.csv"
    if not csv_path.exists():
        sys.exit(f"medicamentos.csv não encontrado em {dataset}")

    rcm_dir = dataset / "downloads" / "rcms"
    if not rcm_dir.is_dir():
        sys.exit(f"Pasta de RCMs não encontrada: {rcm_dir}")

    compostos = (carregar_lista(Path(args.lista)) if args.lista
                 else PGX_COMPOUNDS)
    selector = Selector(compostos)

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))

    # Only verified downloads. An unverified file may be truncated, and a
    # truncated RCM produces a partial analysis that looks complete.
    utilizaveis = [r for r in rows
                   if r.get("has_rcm") == "True"
                   and r.get("rcm_verified") == "True"
                   and r.get("rcm_filename")]

    # rcm_filename repeats: several presentations of one medicine share an RCM.
    por_composto: dict[str, dict[str, dict]] = defaultdict(dict)
    rotas: dict[str, set[str]] = defaultdict(set)

    for r in utilizaveis:
        for composto, rota in selector.match(r["active_substance"],
                                             r.get("atc_labels", "")):
            por_composto[composto][r["rcm_filename"]] = r
            rotas[composto].add(rota)

    # ------------------------------------------------------------------
    # One representative per compound.
    #
    # Generics must carry the same RCM content as the reference product, and
    # the preflight showed 37% of this selection to be byte-identical after
    # normalisation, so one document per substance is a defensible unit.
    #
    # Which one, though, is not arbitrary. The order of preference is:
    #
    #   1. usable            a corrupt or image-only file would make the
    #                        substance look like it has no PGx content
    #   2. mono-substance    a combination RCM describes two drugs, and its
    #                        PGx statements cannot be attributed to one
    #   3. longest text      RCM versions differ; the fullest is the least
    #                        likely to omit a pharmacogenomic mention. For a
    #                        study asking *whether* the RCM mentions PGx,
    #                        picking a truncated version biases towards "no"
    #   4. filename          deterministic tiebreak, so the selection is
    #                        reproducible
    # ------------------------------------------------------------------
    so_ilegiveis: set[str] = set()

    if args.um_por_composto:
        caracteres: dict[str, int] = {}
        inutilizaveis: set[str] = set()
        if args.impressoes:
            import json
            caminho = Path(args.impressoes)
            if not caminho.exists():
                sys.exit(f"impressoes.jsonl não encontrado: {caminho}")
            for linha in caminho.read_text(encoding="utf-8").splitlines():
                if not linha.strip():
                    continue
                d = json.loads(linha)
                caracteres[d["ficheiro"]] = d.get("caracteres", 0)
                if d.get("digitalizacao") or d.get("erro"):
                    inutilizaveis.add(d["ficheiro"])
        else:
            print("⚠️ sem --impressoes: não é possível excluir documentos "
                  "ilegíveis nem ordenar por extensão do texto.\n"
                  "   Corre primeiro o preflight e volta a passar o ficheiro.")

        def chave(item: tuple[str, dict]) -> tuple:
            nome, r = item
            combinacao = "+" in r["active_substance"]
            return (nome in inutilizaveis, combinacao,
                    -caracteres.get(nome, 0), nome)

        reduzido: dict[str, dict[str, dict]] = {}
        for composto, ficheiros in por_composto.items():
            candidatos = sorted(ficheiros.items(), key=chave)
            # Se todos os candidatos forem ilegíveis, é melhor não escolher
            # nenhum: o composto passa aos não encontrados, em vez de entrar
            # na análise com um documento que não se pode ler.
            viaveis = [c for c in candidatos if c[0] not in inutilizaveis]
            if not viaveis:
                so_ilegiveis.add(composto)
                continue
            nome, r = viaveis[0]
            reduzido[composto] = {nome: r}

        if so_ilegiveis:
            print(f"⚠️ {len(so_ilegiveis)} compostos só com documentos "
                  f"ilegíveis: {', '.join(sorted(so_ilegiveis))}")
        por_composto = defaultdict(dict, reduzido)

    destino = Path(args.destino).resolve()
    relatorio_dir = destino / "_selecao"
    if not args.dry_run:
        destino.mkdir(parents=True, exist_ok=True)
        relatorio_dir.mkdir(exist_ok=True)

    linhas_selecao = []
    copiados = ausentes_no_disco = 0

    for composto, ficheiros in sorted(por_composto.items()):
        for nome, r in sorted(ficheiros.items()):
            origem = rcm_dir / nome
            if not origem.exists():
                ausentes_no_disco += 1
                continue
            if not args.dry_run:
                shutil.copy2(origem, destino / nome)
            copiados += 1
            linhas_selecao.append({
                "composto": composto,
                "rota": "+".join(sorted(rotas[composto])),
                "ficheiro": nome,
                "medicamento": r["drug_name"],
                "substancia_infomed": r["active_substance"],
                "atc": r.get("atc_codes", ""),
                "atc_label": r.get("atc_labels", ""),
                "forma": r.get("pharma_form", ""),
                "titular": r.get("mah", ""),
            })

    encontrados = sorted(por_composto)
    nao_encontrados = [pt for pt, _ in compostos if pt not in por_composto]

    # Two very different reasons for a miss, and conflating them would send
    # someone looking in the wrong place:
    #
    #   "sem_rcm_infomed"  the medicine is authorised and listed, but Infomed
    #                      publishes no RCM for it. Typically a centrally
    #                      authorised product whose RCM lives on the EMA site,
    #                      so the document exists and can be fetched there.
    #   "ausente_infomed"  no such substance in the index at all — as a rule,
    #                      not marketed in Portugal. No document to fetch.
    #
    # Checked against every row, not only the ones with a verified RCM.
    diagnostico: dict[str, dict] = {}
    for pt in nao_encontrados:
        en = dict(compostos)[pt]
        padroes = selector.padroes[pt]
        presentes = [
            r for r in rows
            if any(p.search(normalize(r["active_substance"] if rota == "PT"
                                      else r.get("atc_labels", "")))
                   for rota, p in padroes)
        ]
        if pt in so_ilegiveis:
            causa, onde = "rcm_ilegivel", "reobter o PDF (Infomed ou EMA)"
        elif presentes:
            causa, onde = "sem_rcm_infomed", "EMA (autorização centralizada)"
        else:
            causa, onde = ("fora_do_corpus",
                           "repetir pesquisa sem o filtro de comercialização")

        diagnostico[pt] = {
            "composto": pt,
            "inn": en,
            "causa": causa,
            "medicamentos_listados": len(presentes),
            "substancias_infomed": " | ".join(sorted({
                r["active_substance"] for r in presentes})[:4]),
            "onde_procurar": onde,
        }

    sem_rcm = [pt for pt in nao_encontrados
               if diagnostico[pt]["causa"] == "sem_rcm_infomed"]
    ausentes = [pt for pt in nao_encontrados
                if diagnostico[pt]["causa"] == "fora_do_corpus"]
    ilegiveis = [pt for pt in nao_encontrados
                 if diagnostico[pt]["causa"] == "rcm_ilegivel"]

    # ---------------------------------------------------------------- reports
    if not args.dry_run:
        def gravar(nome: str, linhas: list[dict]) -> None:
            if not linhas:
                return
            with (relatorio_dir / nome).open("w", newline="",
                                             encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()))
                w.writeheader()
                w.writerows(linhas)

        gravar("selecao.csv", linhas_selecao)
        gravar("por_composto.csv", [
            {"composto": pt,
             "inn": en,
             "encontrado": "sim" if pt in por_composto else "nao",
             "n_rcm": len(por_composto.get(pt, {})),
             "rota": "+".join(sorted(rotas.get(pt, ()))) or "",
             "substancias_infomed": " | ".join(sorted({
                 r["active_substance"] for r in por_composto.get(pt, {}).values()
             }))}
            for pt, en in compostos
        ])
        gravar("nao_encontrados.csv",
               [diagnostico[pt] for pt in nao_encontrados])

        # Lista de trabalho, em texto simples: para consultar, imprimir ou
        # colar. Separada por causa, porque cada grupo se resolve num sítio
        # diferente — e um deles não se resolve.
        txt = [
            "SUBSTÂNCIAS ATIVAS SEM RCM",
            "",
            f"Pedidas: {len(compostos)}     "
            f"Com RCM: {len(encontrados)}     "
            f"Sem RCM: {len(nao_encontrados)}",
            "",
        ]
        if sem_rcm:
            txt += [
                "=" * 62,
                f"A OBTER NA EMA  ({len(sem_rcm)} substâncias)",
                "=" * 62,
                "",
                "Autorizadas e listadas no Infomed, que não publica o RCM.",
                "Autorização centralizada europeia: o RCM está na EMA.",
                "",
            ]
            for pt in sem_rcm:
                marcas = sorted({
                    r["drug_name"] for r in rows
                    if any(p.search(normalize(
                        r["active_substance"] if rota == "PT"
                        else r.get("atc_labels", "")))
                        for rota, p in selector.padroes[pt])
                })
                txt.append(f"{pt}")
                for m in marcas:
                    txt.append(f"    {m}")
                txt.append("")

        if ilegiveis:
            txt += [
                "=" * 62,
                f"RCM ILEGÍVEL  ({len(ilegiveis)} substâncias)",
                "=" * 62,
                "",
                "O documento existe mas o texto não é extraível (fonte sem",
                "mapa de caracteres). Reobter o PDF.",
                "",
            ]
            txt += [f"{pt}" for pt in ilegiveis]
            txt.append("")

        if ausentes:
            txt += [
                "=" * 62,
                f"FORA DO CORPUS RECOLHIDO  ({len(ausentes)} substâncias)",
                "=" * 62,
                "",
                "Nenhum medicamento com estas substâncias consta do corpus.",
                "",
                "ATENÇÃO ao que isto significa, e ao que não significa.",
                "",
                "O corpus contém apenas medicamentos AUTORIZADOS E",
                "COMERCIALIZADOS: os 9 538 registos são, sem excepção,",
                "'Autorizado' + 'Comercializado'. A recolha não abrange AIM",
                "caducada, revogada ou suspensa, nem medicamentos autorizados",
                "sem comercialização actual.",
                "",
                "Logo, isto NÃO prova que o Infomed não tenha o RCM. Prova",
                "que a substância não tem medicamento comercializado em",
                "Portugal. Estas substâncias são, na maioria, fármacos",
                "antigos — exactamente o perfil que o filtro esconde.",
                "",
                "Para as descartar: repetir a pesquisa no Infomed sem a caixa",
                "'Apenas medicamentos autorizados e comercializados'.",
                "",
            ]
            txt += [f"{pt:<26}({diagnostico[pt]['inn']})" for pt in ausentes]
            txt.append("")

        (relatorio_dir / "faltam.txt").write_text("\n".join(txt) + "\n",
                                                  encoding="utf-8")

        total_rcm = sum(len(v) for v in por_composto.values())
        md = [
            "# Seleção de RCMs por substância ativa",
            "",
            f"- Compostos pedidos: **{len(compostos)}**",
            f"- Com RCM no corpus: **{len(encontrados)}**",
            f"- Sem RCM no corpus: **{len(nao_encontrados)}**",
            f"- RCMs copiados: **{copiados}**"
            + (f" (de {total_rcm} identificados)" if total_rcm != copiados else ""),
            "",
            "A correspondência é ancorada no INN inglês do código ATC, não no "
            "nome português. Coluna `rota` em `selecao.csv`: `INN` quando veio "
            "do código ATC, `PT` quando só o nome português a encontrou.",
            "",
            "## Sem RCM no corpus do Infomed",
            "",
        ]
        if sem_rcm:
            md += [
                f"### Listados no Infomed, sem RCM publicado ({len(sem_rcm)})",
                "",
                "O medicamento está autorizado e consta do índice, mas o "
                "Infomed não publica o RCM. É o padrão dos medicamentos de "
                "autorização centralizada europeia: **o documento existe e "
                "obtém-se no sítio da EMA.**",
                "",
            ]
            md += [f"- {pt} — {diagnostico[pt]['medicamentos_listados']} "
                   f"medicamentos listados" for pt in sem_rcm]
            md.append("")
        if ausentes:
            md += [
                f"### Fora do corpus recolhido ({len(ausentes)})",
                "",
                "O corpus contém **apenas medicamentos autorizados e "
                "comercializados** — os 9 538 registos são, sem excepção, "
                "`Autorizado` + `Comercializado`. Não abrange AIM caducada, "
                "revogada ou suspensa, nem autorizados sem comercialização "
                "actual.",
                "",
                "Estas substâncias não têm medicamento comercializado em "
                "Portugal. Isso **não** prova que o Infomed não tenha o RCM: "
                "para as descartar é preciso repetir a pesquisa sem a caixa "
                "*Apenas medicamentos autorizados e comercializados*.",
                "",
            ]
            md += [f"- {pt} (INN: {diagnostico[pt]['inn']})" for pt in ausentes]
            md.append("")
        if not nao_encontrados:
            md.append("Nenhum.")

        md += ["", "## RCMs por composto", "",
               "| Composto | INN | RCMs | Rota |", "|---|---|---|---|"]
        for pt, en in compostos:
            n = len(por_composto.get(pt, {}))
            md.append(f"| {pt} | {en} | {n if n else '—'} | "
                      f"{'+'.join(sorted(rotas.get(pt, ()))) or '—'} |")

        (relatorio_dir / "relatorio.md").write_text("\n".join(md) + "\n",
                                                    encoding="utf-8")

    # ---------------------------------------------------------------- console
    print("=" * 66)
    print("SELEÇÃO POR SUBSTÂNCIA ATIVA" + ("  (simulação)" if args.dry_run else ""))
    print("=" * 66)
    print(f"  medicamentos com RCM verificado : {len(utilizaveis)}")
    print(f"  compostos pedidos               : {len(compostos)}")
    print(f"  com RCM                         : {len(encontrados)}")
    print(f"  sem RCM                         : {len(nao_encontrados)}")
    print(f"  RCMs {'a copiar' if args.dry_run else 'copiados'}"
          f"{'':<20}: {copiados}")
    if ausentes_no_disco:
        print(f"  ⚠️ no CSV mas ausentes em disco  : {ausentes_no_disco}")

    só_pt = [c for c in encontrados if rotas[c] == {"PT"}]
    if só_pt:
        print(f"\n  Encontrados só pelo nome português ({len(só_pt)}) — "
              f"confirmar:")
        for c in só_pt:
            subs = sorted({r["active_substance"]
                           for r in por_composto[c].values()})
            print(f"      {c:<24} {'; '.join(subs)[:44]}")

    if sem_rcm:
        print(f"\n  Listados no Infomed sem RCM publicado ({len(sem_rcm)}) "
              f"— obter na EMA:")
        for i in range(0, len(sem_rcm), 3):
            print("      " + "".join(f"{x:<24}" for x in sem_rcm[i:i + 3]))

    if ausentes:
        print(f"\n  Fora do corpus recolhido ({len(ausentes)}) — sem "
              f"medicamento comercializado; ver nota em faltam.txt:")
        for i in range(0, len(ausentes), 3):
            print("      " + "".join(f"{x:<24}" for x in ausentes[i:i + 3]))

    if not args.dry_run:
        print(f"\n  {destino}")
        print(f"  {relatorio_dir}/relatorio.md")
        print(f"\n  A seguir: python -m RCMprocessor.preflight {args.destino} …")
    else:
        print("\n  Nada foi copiado. Retira --dry-run para aplicar.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
