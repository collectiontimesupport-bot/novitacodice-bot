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
INTERVALLI = [("EP", 1, 200, 4), ("EPSET", 1, 200, 4), ("CLB", 1, 200, 4), ("CPP", 1, 200, 4),
              ("HUG", 1, 200, 4), ("PSQ", 1, 200, 4), ("SQP", 1, 200, 4), ("SPK", 1, 200, 4),
              ("STG", 1, 200, 4), ("RBAG", 20, 200, 4)]
LIMITE_NUOVE = 50   # fin dove cerco una serie nuova (si cambia con /limite DC 20)
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
         "/lista = codici in attesa\n/togli EP0090 = smetto di controllarlo\n"
         "/serie DC 17 50 = serie nuova DC: sul sito ho i numeri fino al 17, cerca fino al 50\n"
         "/limite DC 20 = cerca la serie DC solo fino al 20")


def imposta_limite(prefisso, limite):
    """Cambia fin dove il bot cerca i codici di una serie."""
    da = 1
    for i, (p, a, b, c) in enumerate(INTERVALLI):
        if p == prefisso:
            da = a
            del INTERVALLI[i]
            break
    INTERVALLI.append((prefisso, da, limite, 4))


def scansiona_serie(prefisso, da=1, a=200):
    """Codici di una serie che esistono online (da PREFISSO0001 a PREFISSO0200)."""
    cod = ["%s%04d" % (prefisso, n) for n in range(da, a + 1)]
    with ThreadPoolExecutor(20) as ex:
        return [c for c, ok in zip(cod, ex.map(immagine_esiste, cod)) if ok]


def registra_serie(stato, codice):
    """Se il prefisso e' nuovo (es. DC0001) cerca da 0001 a 0200 e salva la serie."""
    m = re.match(r"^([A-Z]+)(\d+)$", codice)
    if not m:
        return
    candidati = [m.group(1)] + ([m.group(1)[1:]] if m.group(1).startswith("V") else [])
    if any(p in SUL_SITO for p in candidati):
        return
    for p in candidati:
        trovati = scansiona_serie(p, 1, LIMITE_NUOVE)
        if trovati:
            numeri = sorted(int(c[len(p):]) for c in trovati)
            SUL_SITO[p] = ",".join(str(n) for n in numeri)
            stato["serie"][p] = SUL_SITO[p]
            stato["limiti"][p] = LIMITE_NUOVE
            imposta_limite(p, LIMITE_NUOVE)
            telegram("Nuova serie %s registrata: online ci sono %d codici (%s%04d ... %s%04d). "
                     "Da ora controllo ogni giorno fino a %s%04d e ti avviso dei nuovi.\n"
                     "Per dirmi quanti ne hai sul sito e fin dove cercare: /serie %s %d %d\n"
                     "Solo per cambiare dove cercare: /limite %s 20"
                     % (p, len(numeri), p, numeri[0], p, numeri[-1], p, LIMITE_NUOVE, p, numeri[-1], LIMITE_NUOVE, p))
            return


def gestisci_messaggi(stato):
    testi, stato["ultimo_id"] = leggi_messaggi(stato["ultimo_id"])
    for t in testi:
        t = t.strip()
        if t.startswith("/lista"):
            att = list(stato["attesa"])
            telegram("In attesa: " + (", ".join(att) if att else "nessun codice"))
        elif t.startswith("/serie"):
            parti = t.split()
            m = re.match(r"[A-Za-z]+", parti[1]) if len(parti) > 1 else None
            p = m.group(0).upper() if m else ""
            if p not in stato["serie"]:
                telegram("Serie sconosciuta. Mandami prima un codice della serie, es. %s0001." % (p or "DC"))
                continue
            nums = re.findall(r"\d+", " ".join(parti[1:]))
            n = int(nums[0]) if nums else 0
            limite = int(nums[1]) if len(nums) > 1 else stato["limiti"].get(p, LIMITE_NUOVE)
            SUL_SITO[p] = stato["serie"][p] = "0-%d" % n
            stato["limiti"][p] = limite
            imposta_limite(p, limite)
            nuovi = [c for c in scansiona_serie(p, 1, limite) if int(c[len(p):]) > n and c not in stato["visti"]]
            for c in nuovi:
                invia_foto(c, "Novita' Legami: %s" % c)
                stato["visti"].append(c)
            telegram("Ok: della serie %s hai sul sito fino al %d. Codici nuovi trovati: %d. "
                     "Da ora controllo ogni giorno fino a %s%04d." % (p, n, len(nuovi), p, limite))
        elif t.startswith("/limite"):
            parti = t.split()
            m = re.match(r"[A-Za-z]+", parti[1]) if len(parti) > 1 else None
            p = m.group(0).upper() if m else ""
            nums = re.findall(r"\d+", " ".join(parti[2:]))
            if p not in SUL_SITO or not nums:
                telegram("Scrivi per esempio: /limite DC 20 (la serie deve essere gia' registrata).")
                continue
            stato["limiti"][p] = int(nums[0])
            imposta_limite(p, int(nums[0]))
            telegram("Ok: la serie %s la controllo fino a %s%04d." % (p, p, int(nums[0])))
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
                registra_serie(stato, c)


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
    with ThreadPoolExecutor(20) as ex:
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

    stato.setdefault("serie", {})
    stato.setdefault("limiti", {})
    for p, v in stato["serie"].items():
        SUL_SITO[p] = v
        imposta_limite(p, LIMITE_NUOVE)
    for p, l in stato["limiti"].items():
        imposta_limite(p, l)
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
