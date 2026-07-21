# ResQ

ResQ e' una prima base software per una valigetta smart di primo soccorso basata su Raspberry Pi 5. L'app e' pensata come dispositivo dedicato: avvio automatico, interfaccia a schermo intero su display touch da circa 9", pulsanti grandi, flusso guidato e astrazioni gia' pronte per LED, audio, pulsanti fisici e NFC per refill/manutenzione.

Questa demo non e' un dispositivo medico, non sostituisce formazione, 112 o personale sanitario, e contiene protocolli dimostrativi.

La UI include una barra superiore con bandiere per cambiare lingua in qualsiasi momento, anche durante un protocollo gia' avviato. In questa prima versione sono presenti italiano e inglese, con preferenza salvata nel browser.

## Display target

La UI e' ottimizzata per il monitor touch 9" `1280 x 720` montato fisicamente in verticale. Il pannello resta nativamente landscape: il kiosk Chromium usa quindi una finestra `1280 x 720` e l'app ruota internamente un canvas portrait `720 x 1280` di 90 gradi.

Questi valori sono in `config/settings.json` nella sezione `display`. L'HTML usa la classe `display-rotate-90` sul `body`; se il montaggio fisico richiede il verso opposto, cambia la classe in `display-rotate-270`.

Con questa configurazione non serve che il sistema operativo esponga una viewport portrait: il browser vede `1280 x 720`, mentre l'interfaccia viene disegnata ruotata per risultare dritta quando il monitor viene installato verticale.

## Scelta tecnica

Ho scelto una web app locale con backend Python standard library e frontend HTML/CSS/JS semplice. La scelta evita framework pesanti e dipendenze runtime, funziona bene su PC/Mac durante lo sviluppo, e sul Raspberry puo' partire in kiosk mode con Chromium a schermo intero. La logica resta modulare: backend, protocolli, stato, hardware simulato e UI sono separati.

## Avvio locale su PC/Mac

```bash
python3 main.py --host 127.0.0.1 --port 8080 --open-browser
```

Poi apri:

```text
http://127.0.0.1:8080
```

Per una prova senza apertura automatica del browser:

```bash
python3 main.py
```

## Struttura

```text
.
├── main.py
├── requirements.txt
├── config/settings.json
├── protocols/
│   ├── unconscious.json
│   ├── bleeding.json
│   ├── burn.json
│   └── trauma.json
├── resq_core/
│   ├── app.py
│   ├── emergency_flow.py
│   ├── logger.py
│   ├── protocol_loader.py
│   └── state_manager.py
├── hardware/
│   ├── audio.py
│   ├── buttons.py
│   ├── display.py
│   ├── leds.py
│   └── nfc.py
├── templates/index.html
├── static/
│   ├── app.js
│   └── styles.css
├── logs/
├── system/resq.service
├── install.sh
└── update.sh
```

## Protocolli

I protocolli sono file JSON esterni in `protocols/`. Ogni protocollo definisce:

- `id`, `title`, `disclaimer`;
- `first_step`;
- una lista di `steps`;
- step di tipo `instruction`, `question`, `item`, `end`.

Esempio minimo:

```json
{
  "id": "example",
  "title": "Protocollo esempio",
  "first_step": "start",
  "steps": [
    {
      "id": "start",
      "type": "question",
      "instruction": "Osserva la situazione.",
      "question": "La persona risponde?",
      "answers": {
        "yes": "end",
        "no": "end"
      }
    },
    {
      "id": "end",
      "type": "end",
      "instruction": "Fine protocollo dimostrativo.",
      "summary": "Protocollo completato."
    }
  ]
}
```

Per aggiungere un nuovo protocollo, crea un nuovo file `.json` nella cartella `protocols/`, assegna un `id` univoco e riavvia l'app.

## Hardware simulato

Le classi in `hardware/` sono gia' isolate:

- `ButtonController`
- `LEDController`
- `NFCReader`
- `AudioGuide`
- `DisplayManager`

Oggi loggano eventi simulati, ad esempio accensione LED, refill NFC in manutenzione e guida audio. In futuro puoi sostituire il contenuto di questi metodi con librerie GPIO, I2C/SPI, lettori NFC reali e output audio del Raspberry senza cambiare la UI.

L'NFC non viene usato durante un intervento. Nel percorso d'emergenza l'utente deve solo prendere il presidio indicato dal vano illuminato e continuare. Il lettore NFC e' previsto solo per manutenzione/refill, quando vengono reinseriti o verificati i componenti nella valigetta.

I pulsanti fisici sono simulabili anche da tastiera:

- `S` o `Y`: si';
- `N`: no;
- `Backspace` o `Esc`: indietro;
- `R`: ripeti audio;
- `H` o spazio: home/emergenza.

## Log

Gli eventi vengono registrati in:

```text
logs/resq.log
```

Sono tracciati avvio app, avvio protocolli, risposte utente, presidi richiesti, LED simulati, eventi refill NFC, completamento protocollo ed errori.

## Installazione su Raspberry Pi

Sul Raspberry, clona la repository e lancia:

```bash
chmod +x install.sh update.sh
sudo ./install.sh
```

Lo script:

- installa pacchetti apt essenziali;
- crea `/opt/resq`;
- crea `.venv`;
- installa `requirements.txt`;
- installa `system/resq.service`;
- abilita il servizio systemd.

Il servizio usa `WorkingDirectory=/opt/resq` e avvia l'app con kiosk mode. Non presume che l'utente Linux si chiami `pi`: `install.sh` prova a usare l'utente che ha invocato `sudo`. Se necessario, modifica `User=` in `/etc/systemd/system/resq.service`.

Comandi utili:

```bash
sudo systemctl start resq.service
sudo systemctl stop resq.service
sudo systemctl restart resq.service
sudo systemctl status resq.service
journalctl -u resq.service -f
```

## Aggiornamento da Git

Dentro `/opt/resq`:

```bash
sudo ./update.sh
```

Lo script esegue `git pull --ff-only`, aggiorna le dipendenze e riavvia `resq.service`.

## Fullscreen e kiosk

`main.py --kiosk` prova ad aprire Chromium in modalita' kiosk all'indirizzo locale dell'app. Su Raspberry Pi OS puo' essere necessario installare Chromium e avere una sessione grafica attiva con autologin. In caso di configurazioni Wayland/X11 particolari, lascia il backend come servizio systemd e avvia Chromium kiosk dalla configurazione desktop dell'utente.

## Limiti della demo

- I protocolli sono dimostrativi e volutamente non dettagliati.
- Nessun hardware reale e' ancora collegato.
- Lo stato e' in memoria e si resetta al riavvio.
- Non c'e' autenticazione: l'app e' pensata per uso locale sul dispositivo.
- Non c'e' database: per ora bastano log su file e protocolli esterni.
