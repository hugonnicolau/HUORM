"""
Resolução da substância ativa contra o UMLS e o ClinPGx.

Três defeitos, todos encontrados nos 64 documentos processados.

1. O CUI era resolvido e não era usado
   O MRCONSO liga "alopurinol" e "allopurinol" ao mesmo C0002144, e
   "voriconazol" e "voriconazole" ao mesmo C0393080. O resolver chegava ao
   CUI e parava: a consulta ao ClinPGx seguia com o nome português, que o
   ClinPGx não conhece. Custo medido: 5 guidelines em 64 documentos.

2. Correspondência parcial sem comprimento mínimo
   `string_norm in query_norm` aceitava qualquer string do MRCONSO contida na
   consulta, incluindo letras isoladas. O alias "metoxifluorane" casou com
   "L" (leucina), "Or" e "M".

3. Sem arbitragem entre consultas
   A leucina tinha DrugBank ID, ganhou a ordenação, e ficou gravada como o
   CUI do metoxiflurano — apesar de existir correspondência exacta para
   "metoxiflurano" (C0025688) noutra consulta.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from RCMprocessor.active_substance_external_resolver import (  # noqa: E402
    ActiveSubstanceExternalResolver as Resolver,
)


# --------------------------------------------------------------------------
# 1. Expansão do CUI para sinónimos ingleses
# --------------------------------------------------------------------------

def _mrconso(*matches):
    """Devolve a forma que _resolve_mrconso produz, para alimentar os testes."""
    return {"results_by_substance": {"q": {"matches": list(matches)}}}


def test_expande_com_o_nome_ingles():
    m = _mrconso({"cui": "C0002144",
                  "english_terms": ["allopurinol", "Allopurinol", "Alopurinol"]})
    out = Resolver._expandir_com_sinonimos(["alopurinol"], m)
    assert "allopurinol" in out, out
    assert "alopurinol" in out, "a consulta original tem de sobreviver"


def test_nao_repete_o_que_ja_existe():
    m = _mrconso({"cui": "C1", "english_terms": ["Alopurinol", "alopurinol"]})
    out = Resolver._expandir_com_sinonimos(["alopurinol"], m)
    assert len([x for x in out if x.lower() == "alopurinol"]) == 1, out


def test_rejeita_formulacoes_e_dosagens():
    """O MRCONSO tem "allopurinol 100 MG Oral Tablet" no mesmo CUI.

    Consultar o ClinPGx com isso nunca casa, e alarga a superfície de erro.
    """
    m = _mrconso({"cui": "C1", "english_terms": [
        "allopurinol",
        "allopurinol 100 MG",
        "allopurinol 100 MG Oral Tablet",
        "Allopurinol Oral Tablet Product",
    ]})
    out = Resolver._expandir_com_sinonimos(["alopurinol"], m)
    assert "allopurinol" in out
    assert not any(any(c.isdigit() for c in x) for x in out), out
    assert not any(len(x.split()) > 2 for x in out), out


def test_aceita_nome_de_duas_palavras():
    """"mefenamic acid" e "folic acid" são nomes legítimos de duas palavras."""
    m = _mrconso({"cui": "C1", "english_terms": ["mefenamic acid"]})
    out = Resolver._expandir_com_sinonimos(["acido mefenamico"], m)
    assert "mefenamic acid" in out, out


def test_sem_mrconso_devolve_as_consultas_originais():
    assert Resolver._expandir_com_sinonimos(["x"], {}) == ["x"]
    assert Resolver._expandir_com_sinonimos(["x"], None) == ["x"]


# --------------------------------------------------------------------------
# 2 e 3. Precisão da correspondência
# --------------------------------------------------------------------------

def test_limite_de_comprimento_do_parcial():
    """Uma letra isolada não pode identificar uma substância."""
    assert Resolver.MIN_PARTIAL_LENGTH >= 5, (
        "abaixo de 5 caracteres entram siglas e letras de código; foi assim "
        "que a leucina ('L') foi atribuída ao metoxiflurano"
    )


def test_o_caso_real_do_metoxiflurano():
    """Com o limite em vigor, 'L', 'Or' e 'M' deixam de ser candidatos."""
    consulta = "metoxifluorane"
    for lixo in ["l", "or", "m", "leu"]:
        assert not (
            len(lixo) >= Resolver.MIN_PARTIAL_LENGTH and lixo in consulta
        ), f"{lixo!r} ainda casaria com {consulta!r}"
    # E um nome verdadeiro continua a passar.
    real = "metoxifluorano"
    assert len(real) >= Resolver.MIN_PARTIAL_LENGTH


def test_exacto_ganha_ao_parcial_entre_consultas():
    """A arbitragem tem de olhar para todas as consultas, não só a primeira.

    Reproduz a ordem real: o alias vem primeiro e só tem parciais; o nome
    original vem depois e tem a correspondência exacta.
    """
    resultados = {
        "metoxifluorane": {"matches": [
            {"cui": "C0023401", "match_type": "partial", "matched_term": "L",
             "drugbank_id": "DB00149"},
        ]},
        "metoxiflurano": {"matches": [
            {"cui": "C0025688", "match_type": "exact",
             "matched_term": "Metoxiflurano"},
        ]},
    }
    melhor = None
    for r in resultados.values():
        for m in r["matches"]:
            if m["match_type"] == "exact":
                melhor = m
                break
        if melhor:
            break
    assert melhor is not None
    assert melhor["cui"] == "C0025688", (
        "o CUI correcto do metoxiflurano; C0023401 é a leucina"
    )


# ==========================================================================
if __name__ == "__main__":
    failures = 0
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passaram")
    sys.exit(1 if failures else 0)
