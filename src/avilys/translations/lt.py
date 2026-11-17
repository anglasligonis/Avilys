"""Lietuvių kalba (Lithuanian).

STRINGS maps the English text in the code to Lithuanian. A list holds the
three plural forms, in this order:
    1, 21, 31…        ("1 torentas")
    2–9, 22–29…       ("2 torentai")
    0, 10–20, 30…     ("10 torentų")
tests/test_i18n.py fails if the code gains text that is missing here.

Words used throughout: torentas (torrent), skleidėjas (seed), siuntėjas
(peer), seklys (tracker), dalis (piece), santykis (ratio), prievadas (port).
"""

DECIMAL_POINT = ","


def plural(n: int) -> int:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return 0
    if n % 10 >= 2 and not 10 <= n % 100 < 20:
        return 1
    return 2


STRINGS = {
    # -- engine: errors and the event log ------------------------------------
    "country database updated": "šalių duomenų bazė atnaujinta",
    "country database update failed: {error}": "nepavyko atnaujinti šalių duomenų bazės: {error}",
    "“{name}” is already in your list": "„{name}“ jau yra jūsų sąraše",
    "The disk is full": "Diskas pilnas",
    "Avilys isn't allowed to write to the save folder": "Avilys neturi teisės rašyti į išsaugojimo aplanką",
    "Files are missing": "Trūksta failų",
    "Couldn't write to the save folder": "Nepavyko rašyti į išsaugojimo aplanką",
    "Error {code}": "Klaida {code}",
    "not a magnet link or a .torrent file: {source}": "tai nėra magnet nuoroda ar .torrent failas: {source}",
    "{name} isn't a valid .torrent file ({error})": "{name} nėra tinkamas .torrent failas ({error})",
    "blocklist: {n} ranges blocked": [
        "blokavimo sąrašas: užblokuotas {n} rėžis",
        "blokavimo sąrašas: užblokuoti {n} rėžiai",
        "blokavimo sąrašas: užblokuota {n} rėžių",
    ],
    "not a tracker address: {url}": "tai nėra seklio adresas: {url}",
    "not a valid magnet link ({error})": "netinkama magnet nuoroda ({error})",
    "slow mode on": "lėtasis režimas įjungtas",
    "slow mode off": "lėtasis režimas išjungtas",
    "add failed: {error}": "nepavyko pridėti: {error}",
    "ratio {ratio} reached, stopped: {name}": "pasiektas santykis {ratio}, sustabdyta: {name}",
    "couldn't move files: {error}": "nepavyko perkelti failų: {error}",
    "blocklist: {error}": "blokavimo sąrašas: {error}",
    "skipping corrupt resume file {name}: {error}": "praleidžiamas sugadintas tęsimo failas {name}: {error}",
    "ignored {what}: {error}": "nepaisoma {what}: {error}",
    "metadata received: {name}": "gauti metaduomenys: {name}",
    "finished, now seeding: {name}": "baigta, dabar skleidžiama: {name}",
    "seeded for {hours} h, stopped: {name}": "skleista {hours} val., sustabdyta: {name}",
    "watch folder: {error}": "stebimas aplankas: {error}",
    "watch folder: can't rename {name}: {error}": "stebimas aplankas: nepavyko pervadinti {name}: {error}",
    "resumed {n} torrents": ["tęsiamas {n} torentas", "tęsiami {n} torentai", "tęsiama {n} torentų"],

    # -- durations ---------------------------------------------------------------
    "{h}h {m:02d}m": "{h} val. {m:02d} min.",
    "{m}m {s:02d}s": "{m} min. {s:02d} s",
    "{s}s": "{s} s",
    "{d}d {h}h": "{d} d. {h} val.",
    "{m}m": "{m} min.",

    # -- adding a torrent -------------------------------------------------------
    "Save to folder": "Išsaugojimo aplankas",
    "Browse…": "Naršyti…",
    "Don't show this again (you can turn it back on in Settings)":
        "Daugiau nerodyti (galėsite vėl įjungti nustatymuose)",
    "{size} free": "laisva {size}",
    "free space unknown": "laisva vieta nežinoma",
    "Save to": "Išsaugoti į",
    "Choose files": "Pasirinkite failus",
    "Add torrent": "Pridėti torentą",
    "Magnet link. Avilys gets the file list from other peers once it connects.":
        "Magnet nuoroda. Failų sąrašą Avilys gaus iš kitų siuntėjų, kai tik prisijungs.",
    "Let me choose files when the file list arrives": "Leisti pasirinkti failus, kai bus gautas jų sąrašas",
    "Download": "Atsisiųsti",
    "Add": "Pridėti",
    "Select all": "Žymėti visus",
    "Select none": "Nežymėti nė vieno",
    "File": "Failas",
    "Size": "Dydis",
    "Selected {size}": "Pasirinkta {size}",
    "{n} files": ["{n} failas", "{n} failai", "{n} failų"],
    "(not enough space)": "(nepakanka vietos)",

    # -- default app --------------------------------------------------------------
    "magnet links": "magnet nuorodas",
    ".torrent files": ".torrent failus",
    "Magnet links open in {app}.": "Magnet nuorodas atveria {app}.",
    ".torrent files open in {app}.": ".torrent failus atveria {app}.",
    "Magnet links: no app set.": "Magnet nuorodos: programa nenustatyta.",
    ".torrent files: no app set.": ".torrent failai: programa nenustatyta.",
    "Avilys opens magnet links and .torrent files.": "Avilys atveria magnet nuorodas ir .torrent failus.",
    "Your desktop didn't accept the change for {kinds}.":
        "Jūsų darbalaukio aplinka nepriėmė pakeitimo: Avilys neatvers {kinds}.",
    "Setting the default app isn't supported on this system.":
        "Šioje sistemoje numatytosios programos nustatyti negalima.",
    " and ": " ir ",
    "Avilys now opens {kinds}.": "Dabar Avilys atveria {kinds}.",
    "Windows asks you to confirm this yourself. In the Settings page that opens, choose Avilys for {kinds}.":
        "„Windows“ prašo tai patvirtinti patiems. Atsivėrusiame nustatymų puslapyje pasirinkite Avilys šiems tipams: {kinds}.",
    "Couldn't register Avilys: {error}": "Nepavyko užregistruoti Avilys: {error}",

    # -- speed graph ----------------------------------------------------------------
    "All torrents": "Visi torentai",
    "5 min ago": "prieš 5 min.",
    "now": "dabar",

    # -- torrent states and sidebar filters -----------------------------------
    "Downloading": "Atsiunčiama",
    "Seeding": "Skleidžiama",
    "Finished": "Baigta",
    "Paused": "Pristabdyta",
    "Queued": "Eilėje",
    "Checking": "Tikrinama",
    "Fetching metadata": "Gaunami metaduomenys",
    "Error": "Klaida",
    "All": "Visi",
    "Errors": "Klaidos",

    # -- torrent table ---------------------------------------------------------
    "Name": "Pavadinimas",
    "Progress": "Eiga",
    "Status": "Būsena",
    "Down": "Atsiunt.",
    "Up": "Išsiunt.",
    "Seeds/Peers": "Skleid./Siunt.",
    "Ratio": "Santykis",
    "ETA": "Liko",

    # -- main window -------------------------------------------------------------
    "Encryption: preferred": "Šifravimas: pageidaujamas",
    "Encryption: required": "Šifravimas: privalomas",
    "Encryption: off": "Šifravimas: išjungtas",
    "Port {port}": "Prievadas {port}",
    "Toolbar": "Įrankių juosta",
    "Add .torrent": "Pridėti .torrent",
    "Add magnet": "Pridėti magnet",
    "Resume": "Tęsti",
    "Pause": "Pristabdyti",
    "Remove": "Pašalinti",
    "Settings": "Nustatymai",
    "Quit Avilys": "Užverti Avilį",
    "About Avilys": "Apie Avilį",
    "Filter torrents": "Filtruoti torentus",
    "Slow mode": "Lėtasis režimas",
    "Show Avilys": "Rodyti Avilį",
    "Resume all": "Tęsti visus",
    "Pause all": "Pristabdyti visus",
    "Slow mode is on by schedule: ↓ {down}/s, ↑ {up}/s":
        "Lėtasis režimas įjungtas pagal tvarkaraštį: ↓ {down}/s, ↑ {up}/s",
    "Slow mode is on: ↓ {down}/s, ↑ {up}/s": "Lėtasis režimas įjungtas: ↓ {down}/s, ↑ {up}/s",
    "Slow mode is off: ↓ {down}/s, ↑ {up}/s": "Lėtasis režimas išjungtas: ↓ {down}/s, ↑ {up}/s",
    "Scheduled every day {start}–{end}": "Įsijungia kasdien {start}–{end}",
    "{free} free of {total}": "laisva {free} iš {total}",
    "Open folder": "Atverti aplanką",
    "Move to…": "Perkelti į…",
    "Copy magnet link": "Kopijuoti magnet nuorodą",
    "Download in order": "Siųsti iš eilės",
    "Download from the start of each file, so videos can be previewed sooner.":
        "Kiekvienas failas siunčiamas nuo pradžios, todėl vaizdo įrašus galima peržiūrėti anksčiau.",
    "Speed limits…": "Greičio ribos…",
    "Check files again": "Patikrinti failus iš naujo",
    "Announce now": "Pranešti sekliams dabar",
    "Move to": "Perkelti į",
    "Speed limits": "Greičio ribos",
    "No limit": "Neribojama",
    "Add torrent files": "Pridėti torentų failus",
    "Add magnet links": "Pridėti magnet nuorodas",
    "One magnet link per line:": "Po vieną magnet nuorodą eilutėje:",
    "DHT: {n} nodes": ["DHT: {n} mazgas", "DHT: {n} mazgai", "DHT: {n} mazgų"],
    "DHT off": "DHT išjungtas",
    "Added from the watch folder: {names}": "Pridėta iš stebimo aplanko: {names}",
    "Slow mode stays on until its scheduled time ends.":
        "Lėtasis režimas liks įjungtas, kol baigsis tvarkaraštyje numatytas laikas.",
    "Try again": "Bandyti dar kartą",
    "For the selected torrents. The overall limits still apply.":
        "Pasirinktiems torentams. Bendrosios ribos taip pat galioja.",
    "Couldn't add": "Nepavyko pridėti",
    "Torrent files": "Torentų failai",
    "reachable": "pasiekiamas",
    "Other peers can connect to you.": "Kiti siuntėjai gali prie jūsų prisijungti.",
    "Not known yet whether other peers can connect to you.\nIt shows here once one does.":
        "Dar nežinoma, ar kiti siuntėjai gali prie jūsų prisijungti.\nTai paaiškės, kai kuris nors prisijungs.",
    "No peer has connected to you yet. Downloads still work, but can be slower.\n"
    "If this stays, open port {port} (TCP and UDP) on your router or firewall,\n"
    "or turn on “Open the port on my router” in Settings → Connection.":
        "Prie jūsų dar neprisijungė nė vienas siuntėjas. Atsiuntimai veikia, bet gali būti lėtesni.\n"
        "Jei taip ir lieka, atverkite {port} prievadą (TCP ir UDP) maršrutizatoriuje arba užkardoje\n"
        "arba įjunkite „Atverti prievadą mano maršrutizatoriuje“ (Nustatymai → Ryšys).",
    "µTP only": "Tik µTP",
    "TCP only": "Tik TCP",
    "{n} torrents": ["{n} torentas", "{n} torentai", "{n} torentų"],
    "{n} downloading": "atsiunčiama: {n}",
    "{n} seeding": "skleidžiama: {n}",
    "Torrent stopped": "Torentas sustabdytas",
    "Avilys is still running": "Avilys tebeveikia",
    "Downloads continue in the background. Right-click the tray icon to quit.":
        "Atsiuntimai tęsiami fone. Norėdami užverti programą, spustelėkite dėklo piktogramą dešiniuoju pelės mygtuku.",
    "no incoming connections": "nėra gaunamų prisijungimų",
    "Download complete": "Atsiuntimas baigtas",
    "Your router opened the port for Avilys (UPnP / NAT-PMP).":
        "Maršrutizatorius atvėrė prievadą Aviliui (UPnP / NAT-PMP).",
    "UPnP mapped": "atvertas per UPnP",

    # -- detail tabs ---------------------------------------------------------------
    "(no trackers: peers come from DHT and PEX)": "(seklių nėra: siuntėjai randami per DHT ir PEX)",
    "Skip": "Praleisti",
    "Low": "Žemas",
    "Normal": "Įprastas",
    "High": "Aukštas",
    "Save path": "Išsaugojimo vieta",
    "Downloaded": "Atsiųsta",
    "Uploaded": "Išsiųsta",
    "Availability": "Pasiekiamumas",
    "Pieces": "Dalys",
    "Connections": "Prisijungimai",
    "Added": "Pridėta",
    "Active for": "Aktyvus",
    "Seeding for": "Skleidžiama",
    "Info-hash": "Info maiša",
    "Not contacted yet": "Dar nesikreipta",
    "Don't download": "Nesiųsti",
    "Tracker": "Seklys",
    "Saved": "Išsaugotas",
    "Announcing…": "Pranešama…",
    "Working": "Veikia",
    "Not working ({n} failures)": ["Neveikia ({n} nesėkmė)", "Neveikia ({n} nesėkmės)", "Neveikia ({n} nesėkmių)"],
    "{have} of {total} pieces · {size} each": "Dalių: {have} iš {total} · kiekviena po {size}",
    "Double-click a file to open it": "Dukart spustelėkite failą, kad jį atvertumėte",
    "General": "Bendra",
    "Files": "Failai",
    "Peers": "Siuntėjai",
    "Trackers": "Sekliai",
    "Speed": "Greitis",
    "Magnet link": "Magnet nuoroda",
    "Copy": "Kopijuoti",
    "Peers ({n})": "Siuntėjai ({n})",
    "{size} (all time {total})": "{size} (iš viso {total})",
    "{total} ({n} seeds)": ["{total} ({n} skleidėjas)", "{total} ({n} skleidėjai)", "{total} ({n} skleidėjų)"],
    "Open": "Atverti",
    "Show in folder": "Rodyti aplanke",
    "Add tracker…": "Pridėti seklį…",
    "Add trackers": "Pridėti seklius",
    "Tracker addresses, one per line:": "Seklių adresai, po vieną eilutėje:",
    "Priority": "Pirmenybė",
    "Country": "Šalis",
    "Address": "Adresas",
    "Client": "Programa",
    "Transport": "Protokolas",
    "Encryption": "Šifravimas",
    "Source": "Šaltinis",
    "Has": "Turi",
    "URL": "Adresas",
    "Tier": "Pakopa",
    "Seeds": "Skleidėjai",
    "Message": "Pranešimas",
    "Stopped: {problem}. Fix the problem, then try again.":
        "Sustabdyta: {problem}. Pašalinkite problemą ir bandykite dar kartą.",
    "{folder} (moves to {destination} when finished)": "{folder} (baigus bus perkelta į {destination})",
    "unknown yet": "dar nežinomas",
    "Not downloaded yet": "Dar neatsiųsta",
    "Incoming": "Gaunamas",
    "Remove tracker": "Pašalinti seklį",
    "Remove {n} trackers": ["Pašalinti {n} seklį", "Pašalinti {n} seklius", "Pašalinti {n} seklių"],
    "Waiting for the file list from peers…": "Laukiama failų sąrašo iš siuntėjų…",
    "{copies} copies available in the swarm": "spiečiuje prieinama kopijų: {copies}",
    "“{name}” is set to “Don't download”.": "Failui „{name}“ nustatyta „Nesiųsti“.",
    "“{name}” hasn't been downloaded yet.": "Failas „{name}“ dar neatsiųstas.",
    "Header only": "Tik antraštė",
    "Plaintext": "Nešifruota",
    "Connecting…": "Jungiamasi…",
    "(waiting for metadata)": "(laukiama metaduomenų)",
    "IP Geolocation by DB-IP (db-ip.com)": "IP geografinė vieta: DB-IP (db-ip.com)",

    # -- About ----------------------------------------------------------------------
    'Built on <a href="https://libtorrent.org">libtorrent</a> and '
    '<a href="https://doc.qt.io/qtforpython/">Qt for Python</a>.<br>'
    'IP Geolocation by <a href="https://db-ip.com">DB-IP</a> (CC BY 4.0). '
    'Flags from <a href="https://github.com/lipis/flag-icons">flag-icons</a> (MIT). '
    'Icons from <a href="https://lucide.dev">Lucide</a> (ISC).':
        'Sukurta naudojant <a href="https://libtorrent.org">libtorrent</a> ir '
        '<a href="https://doc.qt.io/qtforpython/">Qt for Python</a>.<br>'
        'IP geografinė vieta: <a href="https://db-ip.com">DB-IP</a> (CC BY 4.0). '
        'Vėliavos iš <a href="https://github.com/lipis/flag-icons">flag-icons</a> (MIT). '
        'Piktogramos iš <a href="https://lucide.dev">Lucide</a> (ISC).',
    "A BitTorrent client. “Avilys” is Lithuanian for beehive.": "BitTorrent klientas, pavadintas bičių avilio garbei.",
    "Poem: {title}, {author}": "Eilėraštis: {title}, {author}",
    "Version {version}": "Versija {version}",

    # -- Settings ---------------------------------------------------------------------
    "Same as system": "Kaip sistemoje",
    "Light": "Šviesus",
    "Dark": "Tamsus",
    "Prefer encrypted (accept both)": "Pirmenybė šifruotiems (priimami abu)",
    "Require encryption": "Reikalauti šifravimo",
    "Never encrypt": "Niekada nešifruoti",
    "Unlimited": "Neribojama",
    "Remove torrents": "Pašalinti torentus",
    "Also delete the downloaded files": "Taip pat ištrinti atsiųstus failus",
    "Clear": "Išvalyti",
    "Add .torrent files that appear in this folder": "Pridėti šiame aplanke atsiradusius .torrent failus",
    "Keep unfinished downloads in a separate folder": "Nebaigtus atsiuntimus laikyti atskirame aplanke",
    "Start Avilys when I sign in, hidden in the tray": "Paleisti Avilį man prisijungus, paslėptą sistemos dėkle",
    "Keep the computer awake while downloading": "Neleisti kompiuteriui užmigti, kol siunčiama",
    "Ask for the save folder and files when adding a torrent":
        "Pridedant torentą klausti išsaugojimo aplanko ir failų",
    "Keep downloading in the tray when the window is closed": "Užvėrus langą toliau siųsti sistemos dėkle",
    "Make Avilys the default": "Padaryti Avilį numatytuoju",
    "Any (all connections)": "Bet kuris (visi ryšiai)",
    "DHT (find peers without trackers)": "DHT (siuntėjų paieška be seklių)",
    "µTP (UDP transport that yields to other traffic)": "µTP (UDP protokolas, užleidžiantis kelią kitam srautui)",
    "Find peers on the local network": "Ieškoti siuntėjų vietiniame tinkle",
    "Open the port on my router (UPnP / NAT-PMP)": "Atverti prievadą mano maršrutizatoriuje (UPnP / NAT-PMP)",
    "Connection": "Ryšys",
    "Slow mode is on": "Lėtasis režimas įjungtas",
    "Turn on slow mode every day": "Įjungti lėtąjį režimą kasdien",
    "Stop seeding at ratio": "Nebeskleisti pasiekus santykį",
    "Stop seeding after": "Nebeskleisti po",
    "Queue && seeding": "Eilė ir skleidimas",
    "No blocklist": "Blokavimo sąrašo nėra",
    "Allow trackers, web seeds and peers on the local network":
        "Leisti seklius, žiniatinklio šaltinius ir dalyvius vietiniame tinkle",
    "Reuse existing files in this folder": "Naudoti šiame aplanke esančius failus",
    "Avilys may overwrite existing files when this is enabled.":
        "Įjungus šią parinktį, Avilys gali perrašyti esamus failus.",
    "Show peer countries": "Rodyti siuntėjų šalis",
    "Anonymous mode": "Anoniminis režimas",
    "Don't tell peers and trackers which program and version I use":
        "Nepranešti siuntėjams ir sekliams, kokią programą ir versiją naudoju",
    "Your IP address stays visible to peers: use a VPN to hide it. "
    "Some private trackers refuse programs they can't identify.":
        "Jūsų IP adresą siuntėjai mato ir toliau: norėdami jį paslėpti, naudokite VPN. "
        "Kai kurie privatūs sekliai nepriima programų, kurių negali atpažinti.",
    "Privacy": "Privatumas",
    "Remove “{name}” from the list?": "Pašalinti „{name}“ iš sąrašo?",
    "Remove {n} torrents from the list?": [
        "Pašalinti {n} torentą iš sąrašo?",
        "Pašalinti {n} torentus iš sąrašo?",
        "Pašalinti {n} torentų iš sąrašo?",
    ],
    "{name} (not connected now)": "{name} (šiuo metu neprijungtas)",
    "from": "nuo",
    "to": "iki",
    "hours": "val.",
    "{n} address ranges blocked.": [
        "Užblokuotas {n} adresų rėžis.",
        "Užblokuoti {n} adresų rėžiai.",
        "Užblokuota {n} adresų rėžių.",
    ],
    "Not available on this system.": "Šioje sistemoje neprieinama.",
    "Default app": "Numatytoji programa",
    "Save new downloads to": "Naujus atsiuntimus saugoti",
    "Unfinished": "Nebaigti",
    "Watch folder": "Stebimas aplankas",
    "Adding": "Pridėjimas",
    "Window": "Langas",
    "Theme": "Apipavidalinimas",
    "Language": "Kalba",
    "Listening port": "Klausymosi prievadas",
    "Network": "Tinklas",
    "Download limit": "Atsiuntimo riba",
    "Upload limit": "Išsiuntimo riba",
    "Slow download limit": "Lėtojo režimo atsiuntimo riba",
    "Slow upload limit": "Lėtojo režimo išsiuntimo riba",
    "Schedule": "Tvarkaraštis",
    "Downloading at once": "Vienu metu atsiunčiama",
    "Seeding at once": "Vienu metu skleidžiama",
    "IP blocklist": "IP blokavimo sąrašas",
    "Countries": "Šalys",
    "Start with the system": "Paleidimas su sistema",
    "Tell me when a new version is out": "Pranešti, kai išleidžiama nauja versija",
    "Check now": "Tikrinti dabar",
    "Updates": "Atnaujinimai",
    "Avilys asks GitHub once a day whether there's a newer release. "
    "It never downloads or installs anything by itself.":
        "Avilys kartą per dieną paklausia GitHub, ar yra naujesnė versija. "
        "Pats nieko neatsisiunčia ir neįdiegia.",
    "Check for updates": "Atnaujinimų paieška",
    "Couldn't check for updates: {error}": "Nepavyko patikrinti atnaujinimų: {error}",
    "update check failed: {error}": "nepavyko patikrinti atnaujinimų: {error}",
    "You have the latest version ({version}).": "Naudojate naujausią versiją ({version}).",
    "Update available": "Yra atnaujinimas",
    "Avilys {version} is available.": "Išleista Avilys {version}.",
    "Avilys {version} is available. You have {current}.": "Išleista Avilys {version}. Jūs naudojate {current}.",
    "Download it from the releases page on GitHub. "
    "Your torrents and settings are kept when you install it.":
        "Atsisiųskite ją iš leidimų puslapio GitHub svetainėje. "
        "Įdiegus jūsų torentai ir nustatymai išliks.",
    "Open download page": "Atverti atsisiuntimo puslapį",
    "Skip this version": "Praleisti šią versiją",
    "Later": "Vėliau",
    "no published release found": "nerasta paskelbtos versijos",
    "Couldn't change this: {error}": "Nepavyko pakeisti: {error}",
    "Save downloads to": "Atsiuntimų aplankas",
    "Folder for unfinished downloads": "Nebaigtų atsiuntimų aplankas",
    "Files move to the save folder when a download completes.":
        "Baigus atsiuntimą failai perkeliami į išsaugojimo aplanką.",
    "Added files are renamed to .torrent.added, so each one is picked up once.":
        "Pridėti failai pervadinami į .torrent.added, todėl kiekvienas paimamas tik kartą.",
    "A new language is used the next time Avilys starts.": "Nauja kalba įsigalios kitą kartą paleidus Avilį.",
    "Pick your VPN here to use only that connection. If it disconnects, transfers stop instead of "
    "continuing over your normal connection.":
        "Pasirinkite čia savo VPN, kad būtų naudojamas tik tas ryšys. Jam nutrūkus siuntimai sustos "
        "ir nebus tęsiami per įprastą ryšį.",
    "Slow mode swaps in lower limits, for example while you work or game. Toggle it from the status bar.":
        "Lėtasis režimas įjungia mažesnes ribas, pavyzdžiui, kol dirbate ar žaidžiate. "
        "Jį perjungsite būsenos juostoje.",
    "Extra torrents wait in the queue and start when a slot frees up.":
        "Kiti torentai laukia eilėje ir pradedami, kai atsilaisvina vieta.",
    "Whichever comes first. With neither, Avilys seeds until you pause or remove a torrent.":
        "Kas įvyks pirmiau. Nepažymėjus nė vieno, Avilys skleis tol, kol torentą pristabdysite arba pašalinsite.",
    "Choose a blocklist": "Pasirinkite blokavimo sąrašą",
    "Uses the free country database from db-ip.com (IP Geolocation by DB-IP), refreshed about once a month.":
        "Naudojama nemokama šalių duomenų bazė iš db-ip.com (IP Geolocation by DB-IP), "
        "atnaujinama maždaug kartą per mėnesį.",
    "IPv6 only": "tik IPv6",
    "Peers in these address ranges are never contacted. P2P, eMule .dat and CIDR lists work, gzipped or not.":
        "Su siuntėjais iš šių adresų rėžių niekada nesijungiama. Tinka P2P, eMule .dat ir CIDR sąrašai, "
        "suglaudinti gzip arba ne.",
    "All files": "Visi failai",
    "Blocklists": "Blokavimo sąrašai",
}

# Qt's own text: standard buttons and the file dialog (Qt ships no Lithuanian).
QT_STRINGS = {
    "OK": "Gerai",
    "&OK": "&Gerai",
    "Cancel": "Atsisakyti",
    "&Cancel": "&Atsisakyti",
    "Close": "Užverti",
    "&Close": "&Užverti",
    "Apply": "Taikyti",
    "Yes": "Taip",
    "&Yes": "&Taip",
    "No": "Ne",
    "&No": "&Ne",
    "Open": "Atverti",
    "&Open": "&Atverti",
    "Save": "Įrašyti",
    "&Save": "Į&rašyti",
    "&Choose": "&Pasirinkti",
    "Look in:": "Ieškoti:",
    "Directory:": "Aplankas:",
    "File &name:": "Failo &pavadinimas:",
    "Files of type:": "Failų tipas:",
    "Find Directory": "Rasti aplanką",
    "Name": "Pavadinimas",
    "Size": "Dydis",
    "Type": "Tipas",
    "Date Modified": "Keitimo data",
    "Back": "Atgal",
    "Forward": "Pirmyn",
    "Parent Directory": "Aukštesnis aplankas",
    "Create New Folder": "Sukurti naują aplanką",
    "List View": "Sąrašas",
    "Detail View": "Išsami informacija",
    "&New Folder": "&Naujas aplankas",
    "New Folder": "Naujas aplankas",
    "&Rename": "Per&vadinti",
    "&Delete": "Iš&trinti",
    "Show &hidden files": "Rodyti &paslėptus failus",
    "Computer": "Kompiuteris",
    "Drive": "Diskas",
    "Folder": "Aplankas",
    "File": "Failas",
    "Undo": "Atšaukti",
    "Redo": "Grąžinti",
    "&Undo": "&Atšaukti",
    "&Redo": "&Grąžinti",
    "Cu&t": "Iški&rpti",
    "&Copy": "&Kopijuoti",
    "&Paste": "Į&dėti",
    "Delete": "Ištrinti",
    "Select All": "Žymėti viską",
}
