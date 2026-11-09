import json

from bs4 import BeautifulSoup


def extraire_chunks_flight(html_page):
    chunks = []
    soup = BeautifulSoup(html_page, "lxml")
    for script in soup.find_all("script"):
        contenu = script.string or script.get_text() or ""
        prefixe = "self.__next_f.push("
        debut = contenu.find(prefixe)
        fin = contenu.rfind(")")
        if debut < 0 or fin <= debut:
            continue
        try:
            charge = json.loads(contenu[debut + len(prefixe):fin])
        except (json.JSONDecodeError, TypeError):
            continue
        if (
            isinstance(charge, list)
            and len(charge) > 1
            and isinstance(charge[1], str)
        ):
            chunks.append(charge[1])
    return chunks
