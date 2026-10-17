#!/usr/bin/env python3
"""
Bot Telegram per le novita' Legami.

COSA FA
  1) TU gli scrivi su Telegram un codice (es. EP0090) oppure incolli un link Legami
     con il codice modificato: il bot lo mette "in attesa" e lo controlla di continuo.
     Appena l'immagine del prodotto compare sul server Legami ti scrive con la foto.
  2) Ogni mattina fa anche una ricerca generale di codici nuovi (penne e set).

COMANDI (scrivili al bot):
  EP0090            -> tieni d'occhio questo codice (puoi mandarne piu' di uno)
  un link Legami    -> il bot ne ricava il codice
  /lista            -> codici in attesa
  /togli EP0090     -> smetti di controllare un codice
  /aiuto            -> riepilogo

Per cambiare cosa cerca nella ricerca generale basta modificare "IMPOSTAZIONI".
Uso:  python3 controlla.py            (normale)
      python3 controlla.py --prova    (non invia nulla a Telegram, stampa soltanto)
"""
import json, os, re, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

# ---------------- IMPOSTAZIONI ----------------
# Ricerca generale: (prefisso, da, a, cifre)
INTERVALLI = [("EP", 1, 140, 4), ("EPSET", 1, 40, 4), ("CLB", 1, 99, 4), ("CPP", 1, 99, 4),
              ("HUG", 1, 99, 4), ("PSQ", 1, 99, 4), ("SQP", 1, 99, 4), ("SPK", 1, 99, 4),
              ("STG", 1, 99, 4), ("RBAG", 20, 99, 4)]
# Codici che ci sono GIA' sul sito Collection Time (non vengono segnalati)
SUL_SITO = {
    "EP": "1-86,89,95,96", "EPSET": "1-17", "CLB": "1-25", "CPP": "1-34", "HUG": "1-8",
    "PSQ": "1-9", "SQP": "1-4,6-10", "SPK": "1-13,15,17-21", "STG": "1-3", "RBAG": "0-23",
}


def sul_sito(codice):
    m = re.match(r"^([A-Z]+)(\d+)$", codice)
    if not m or m.group(1) not in SUL_SITO:
        return False
    n = int(m.group(2))
    for parte in SUL_SITO[m.group(1)].split(","):
        a, _, b = parte.partition("-")
        if int(a) <= n <= int(b or a):
            return True
    return False

# Pagine Legami da leggere nella ricerca generale
PAGINE = [
    "cartoleria/scrittura/penne-cancellabili.html?sz=100",
    "halloween.html?sz=100",
    "in-evidenza/novita.html?sz=100",
    "search?q=natale+penne&sz=100",
]
PREFISSI_PAGINE = tuple(SUL_SITO)
# Codici gia' noti (la ricerca generale non li segnala)
NOTI_INIZIALI = ["EP0085", "EP0086", "EP0089", "EP0095", "EPSET0016", "EPSET0017",
                 "TEP0001", "TEP0002", "CPP0032", "CPPSET3", "WIM0001"] + \
                ["HUG000%d" % i for i in range(1, 9)]
# Ora (UTC) in cui fare la ricerca generale (le 6 UTC = 8 in Italia d'estate)
ORA_RICERCA_GENERALE = 6
# ----------------------------------------------

SITO = "https://www.legami.com/it-it/"
IMG = ("https://www.legami.com/dw/image/v2/BDSQ_PRD/on/demandware.static/-/"
       "Sites-legami-master-catalog/default/dw2291204a/images_legami/zoom/%s_1.jpg")
UA = {"User-Agent": "Mozilla/5.0"}
CARTELLA = os.path.dirname(os.path.abspath(__file__))
FILE_STATO = os.path.join(CARTELLA, "stato.json")
PROVA = "--prova" in sys.argv
TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT = str(os.environ.get("TELEGRAM_CHAT_ID", ""))
API = "https://api.telegram.org/bot%s/" % TOKEN


def scarica(url, testa=False):
    req = urllib.request.Request(url, headers=UA, method="HEAD" if testa else "GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status if testa else r.read().decode("utf-8", "ignore")


def immagine_esiste(codice):
    try:
        return scarica(IMG % codice + "?sw=100&sh=100", testa=True) == 200
    except Exception:
        return False


IMG_N = IMG.replace("%s_1.jpg", "%s_%d.jpg")
MAX_FOTO = 30


def varianti_online(codice):
    """Numeri delle foto (_1 ... _10) che esistono online per questo codice."""
    def prova(n):
        try:
            return scarica(IMG_N % (codice, n) + "?sw=100&sh=100", testa=True) == 200
        except Exception:
            return False
    numeri = list(range(1, MAX_FOTO + 1))
    with ThreadPoolExecutor(10) as ex:
        return [n for n, ok in zip(numeri, ex.map(prova, numeri)) if ok]


def invia_foto(codice, titolo):
    """Manda tutte le foto online del codice (_1, _2, ... fino a 10). Ritorna quante."""
    numeri = varianti_online(codice)
    for i, n in enumerate(numeri):
        didascalia = ("%s\n" % titolo if i == 0 else "") + "%s_%d" % (codice, n)
        telegram(didascalia, IMG_N % (codice, n) + "?sw=1008&sh=1008")
    return len(numeri)


def codice_trovato(codice):
    """Ritorna il codice che ha l'immagine online (prova anche senza la V iniziale)."""
    candidati = [codice] + ([codice[1:]] if codice.startswith("V") else [])
    for c in candidati:
        if immagine_esiste(c):
            return c
    return None


# ---------- Telegram ----------
def telegram(testo, foto=None):
    if PROVA:
        print("[PROVA] Telegram:", testo, "| foto:", foto or "-")
        return
    if foto:
        dati = urllib.parse.urlencode({"chat_id": CHAT, "photo": foto, "caption": testo}).encode()
        try:
            urllib.request.urlopen(API + "sendPhoto", dati, timeout=30)
            return
        except Exception as e:
            print("Foto non inviata, mando solo il testo:", e)
    dati = urllib.parse.urlencode({"chat_id": CHAT, "text": testo}).encode()
    urllib.request.urlopen(API + "sendMessage", dati, timeout=30)


def leggi_messaggi(ultimo_id):
    """Messaggi nuovi scritti dall'utente al bot. Ritorna (lista testi, nuovo ultimo_id)."""
    if PROVA:
        return json.loads(os.environ.get("TEST_MESSAGGI", "[]")), ultimo_id
    extra = [x.strip() for x in os.environ.pop("MESSAGGI_EXTRA", "").split(";") if x.strip()]
    url = API + "getUpdates?timeout=0&offset=%d" % (ultimo_id + 1)
    dati = json.loads(scarica(url))
    testi = list(extra)
    for u in dati.get("result", []):
        ultimo_id = max(ultimo_id, u["update_id"])
        m = u.get("message") or {}
        # Sicurezza: ascolto SOLO la tua chat
        if str(m.get("chat", {}).get("id")) == CHAT and m.get("text"):
            testi.append(m["text"])
    return testi, ultimo_id


def estrai_codici(testo):
    """Ricava i codici da un testo o da un link (anche modificato a mano)."""
    trovati = re.findall(r"zoom/([A-Za-z]+\d+)", testo)  # link immagine Legami
    if not trovati:
        trovati = re.findall(r"\b([A-Za-z]{1,8}\d{3,5})\b", testo)
    return [c.upper() for c in dict.fromkeys(trovati)]


AIUTO = ("Scrivimi un codice (es. EP0090) o incolla un link Legami con il codice modificato: "
         "lo controllo di continuo e ti avviso appena l'immagine compare.\n"
         "/lista = codici in attesa\n/togli EP0090 = smetto di controllarlo")


def gestisci_messaggi(stato):
    testi, stato["ultimo_id"] = leggi_messaggi(stato["ultimo_id"])
    for t in testi:
        t = t.strip()
        if t.startswith("/lista"):
            att = list(stato["attesa"])
            telegram("In attesa: " + (", ".join(att) if att else "nessun codice"))
        elif t.startswith("/svuota"):
            stato["attesa"].clear()
            telegram("Fatto: non sto piu' aspettando nessun codice.")
        elif t.startswith("/togli"):
            for c in estrai_codici(t):
                stato["attesa"].pop(c, None)
                telegram("Tolto: " + c)
        elif t.startswith("/start") or t.startswith("/aiuto"):
            telegram(AIUTO)
        else:
            codici = estrai_codici(t)
            if not codici:
                telegram("Non trovo nessun codice. " + AIUTO)
            for c in codici:
                trovato = codice_trovato(c)
                if trovato:
                    n = invia_foto(trovato, "%s e' gia' online." % c)
                    if n == 0:
                        telegram("%s e' online ma non riesco a mandarti le foto." % c)
                    if c not in stato["visti"]:
                        stato["visti"].append(c)
                else:
                    if c not in stato["attesa"]:
                        stato["attesa"][c] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    telegram("%s non e' ancora online. Lo tengo d'occhio e ti avviso appena esce." % c)


def controlla_attesa(stato):
    for codice in list(stato["attesa"]):
        trovato = codice_trovato(codice)
        if trovato:
            if invia_foto(trovato, "TROVATO! %s e' online." % codice) == 0:
                telegram("TROVATO! %s e' online.\nhttps://www.legami.com/it-it/search?q=%s" % (codice, trovato),
                         IMG % trovato + "?sw=1008&sh=1008")
            stato["attesa"].pop(codice)
            if codice not in stato["visti"]:
                stato["visti"].append(codice)


# ---------- Ricerca generale (una volta al giorno) ----------
def codici_immagini():
    cod = ["%s%0*d" % (p, c, n) for p, a, b, c in INTERVALLI for n in range(a, b + 1) if not sul_sito("%s%0*d" % (p, c, n))]
    with ThreadPoolExecutor(10) as ex:
        return {c for c, ok in zip(cod, ex.map(immagine_esiste, cod)) if ok}


def codici_pagine():
    trovati = set()
    for p in PAGINE:
        try:
            html = scarica(SITO + p)
        except Exception as e:
            print("Pagina non leggibile:", p, e)
            continue
        for c in set(re.findall(r"zoom/([A-Z]+[0-9]+)_1\.jpg", html)):
            m = re.match(r"^(%s)(\d+)$" % "|".join(PREFISSI_PAGINE), c)
            if not m:
                continue
            if m.group(1) == "EP" and int(m.group(2)) < 80:   # EP fino al 79: gia' tutte sul sito
                continue
            trovati.add(c)
    return trovati


def ricerca_generale(stato):
    ora = {c for c in codici_immagini() | codici_pagine() if not sul_sito(c)}
    for c in sorted(ora - set(stato["visti"])):
        if invia_foto(c, "Novita' Legami: %s" % c) == 0:
            telegram("Novita' Legami: %s\nhttps://www.legami.com/it-it/search?q=%s" % (c, c),
                     IMG % c + "?sw=1008&sh=1008")
        stato["attesa"].pop(c, None)
    stato["visti"] = sorted(set(stato["visti"]) | ora)


def main():
    if os.path.exists(FILE_STATO):
        stato = json.load(open(FILE_STATO))
        if isinstance(stato, list):   # vecchio formato
            stato = {"visti": stato, "attesa": {}, "ultimo_id": 0}
    else:
        stato = {"visti": list(NOTI_INIZIALI), "attesa": {}, "ultimo_id": 0}
        telegram("Bot Legami attivo. " + AIUTO)

    inizio = time.time()
    durata = int(os.environ.get("DURATA_SECONDI", "0"))

    gestisci_messaggi(stato)
    controlla_attesa(stato)

    adesso = datetime.now(timezone.utc)
    if os.environ.get("RICERCA_GENERALE") == "1" or (adesso.hour == ORA_RICERCA_GENERALE and adesso.minute < 5):
        ricerca_generale(stato)

    ultimo_controllo = time.time()
    while time.time() - inizio < durata:
        time.sleep(5)
        gestisci_messaggi(stato)
        if time.time() - ultimo_controllo > 120:
            controlla_attesa(stato)
            ultimo_controllo = time.time()

    json.dump(stato, open(FILE_STATO, "w"), indent=1)
    print("In attesa:", list(stato["attesa"]))


main()
