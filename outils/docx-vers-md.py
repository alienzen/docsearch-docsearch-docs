#!/usr/bin/env python3
"""Convertit les guides DocSearch (.docx) en Markdown lisible.

pandoc ne convient pas ici : il perd les titres (les styles Heading du
document ne sont pas reconnus) et rend en tableaux HTML les blocs de code,
qui sont dans ces documents des tableaux à une seule cellule en Consolas.
Ce convertisseur lit word/document.xml et applique les règles propres à
ces guides :

  Heading1/Heading2            → ##  / ###
  tableau 1 cellule en Consolas → bloc de code ```bash
  tableau 1 cellule commençant  → citation > (encadrés ⚠️ / 💡)
    par un pictogramme
  tableau à N colonnes          → tableau Markdown
  gras                          → **…**
  puces / numérotation          → -
"""

import re
import sys
import zipfile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def texte_run(run) -> str:
    return "".join(t.text or "" for t in run.iter(f"{W}t"))


#: Polices à chasse fixe employées par les guides pour le code. Les deux
#: sont nécessaires : les guides de production composent en Consolas, celui
#: de VirtualBox en Courier New.
POLICES_CODE = ("Consolas", "Courier New", "Courier", "Monospace")


def est_code(p) -> bool:
    """Un paragraphe est du code s'il est composé à chasse fixe."""
    for fonts in p.iter(f"{W}rFonts"):
        police = fonts.get(f"{W}ascii") or ""
        if any(police.startswith(c) for c in POLICES_CODE):
            return True
    return False


def paragraphe(p) -> tuple[str, str]:
    """Rend (style, texte) — le style guide la mise en forme Markdown."""
    style = ""
    ppr = p.find(f"{W}pPr")
    if ppr is not None:
        st = ppr.find(f"{W}pStyle")
        if st is not None:
            style = st.get(f"{W}val") or ""
        # Une puce reste une puce, quel que soit le style nommé du
        # paragraphe (ces documents utilisent « ListParagraph »).
        if ppr.find(f"{W}numPr") is not None:
            style = "liste"

    morceaux = []
    for run in p.findall(f"{W}r"):
        t = texte_run(run)
        if not t:
            continue
        rpr = run.find(f"{W}rPr")
        gras = rpr is not None and rpr.find(f"{W}b") is not None
        # Pas de gras à l'intérieur d'un bloc de code : les astérisques y
        # seraient prises au pied de la lettre.
        morceaux.append(f"**{t}**" if gras and not est_code(p) else t)
    texte = "".join(morceaux)
    # L'indentation est signifiante dans un bloc de code (continuations
    # de ligne après « \\ ») : on ne la retire que sur du texte courant.
    return style, texte.rstrip() if est_code(p) else texte.strip()


def cellule_en_lignes(tc) -> list[tuple[str, str]]:
    return [paragraphe(p) for p in tc.findall(f"{W}p")]


def rendre_tableau(tbl) -> str:
    lignes = tbl.findall(f"{W}tr")
    if not lignes:
        return ""
    colonnes = [tr.findall(f"{W}tc") for tr in lignes]
    largeur = max(len(c) for c in colonnes)

    # ── Cas 1 : une seule colonne, quel que soit le nombre de lignes ──
    # Les blocs de code sont tantôt une cellule à plusieurs paragraphes,
    # tantôt une ligne de tableau par ligne de commande, selon le document.
    if largeur == 1:
        cellules = [tcs[0] for tcs in colonnes]
        textes = [t for tc in cellules for _, t in cellule_en_lignes(tc)]
        if any(est_code(p) for tc in cellules for p in tc.findall(f"{W}p")):
            corps = "\n".join(textes).strip("\n")
            return f"```bash\n{corps}\n```\n"
        # Encadré : pictogramme en tête → citation
        premier = textes[0] if textes else ""
        if premier.startswith(("**⚠️", "**💡", "⚠️", "💡", "**ℹ")):
            return "\n".join(f"> {t}" if t else ">" for t in textes) + "\n"
        return "\n\n".join(t for t in textes if t) + "\n"

    # ── Cas 2 : vrai tableau ──
    rendu = []
    for i, tcs in enumerate(colonnes):
        cellules = [" ".join(t for _, t in cellule_en_lignes(tc) if t) or " " for tc in tcs]
        cellules += [" "] * (largeur - len(cellules))
        rendu.append("| " + " | ".join(c.replace("|", "\\|") for c in cellules) + " |")
        if i == 0:
            rendu.append("|" + "---|" * largeur)
    return "\n".join(rendu) + "\n"


def convertir(chemin_docx: str) -> str:
    with zipfile.ZipFile(chemin_docx) as z:
        arbre = ET.fromstring(z.read("word/document.xml"))
    corps = arbre.find(f"{W}body")

    sortie: list[str] = []
    code_en_cours: list[str] = []

    def vider_code():
        if code_en_cours:
            sortie.append("```bash\n" + "\n".join(code_en_cours) + "\n```\n")
            code_en_cours.clear()

    for element in corps:
        if element.tag == f"{W}tbl":
            vider_code()
            sortie.append(rendre_tableau(element))
        elif element.tag == f"{W}p":
            style, texte = paragraphe(element)
            if est_code(element) and texte:
                code_en_cours.append(texte)
                continue
            vider_code()
            if not texte:
                continue
            if style in ("Heading1", "Heading2"):
                # Un titre est déjà mis en valeur par son niveau : le gras
                # qu'il porte dans le document Word y ajouterait des
                # astérisques visibles.
                titre = texte.replace("**", "")
                diese = "##" if style == "Heading1" else "###"
                sortie.append(f"\n{diese} {titre}\n")
            elif style == "Title":
                sortie.append(f"# {texte}\n")
            elif style == "liste":
                sortie.append(f"- {texte}")
            else:
                sortie.append(texte + "\n")
    vider_code()

    md = "\n".join(sortie)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip() + "\n"


if __name__ == "__main__":
    print(convertir(sys.argv[1]), end="")
