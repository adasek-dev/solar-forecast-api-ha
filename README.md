# Solar Forecast API – Home Assistant Integration

Custom integrace pro Home Assistant pro předpověď solární výroby přes [forecast.xnas.cz](https://forecast.xnas.cz/).

Využívá Open-Meteo (počasí) + pvlib (solární model) + PVGIS (horizont) jako bezplatnou, neomezenou alternativu k forecast.solar.

---

## Funkce

- Předpověď solární výroby na dnes + až 6 dní dopředu
- Až 10 stringů (různé orientace střechy – jih/západ/východ atd.)
- Per-string senzory při více než 1 stringu
- Automatické stínování terénem z PVGIS horizontu
- Automatická kalibrace přes skutečnou denní výrobu
- Předpověď počasí (teplota, oblačnost, vítr)
- Časová okna přebytků pro řízení spotřebičů
- API klíče s per-user rate limitingem
- Kompatibilní formát s forecast.solar

---

## Instalace

### Přes HACS (doporučeno)

1. Otevřete HACS v Home Assistantu
2. Klikněte na tři tečky vpravo nahoře → **Custom repositories**
3. Přidejte URL: `https://github.com/adasek-dev/solar-forecast-api-ha`
4. Kategorie: **Integration**
5. Klikněte **Add**
6. Vyhledejte „Solar Forecast API" a nainstalujte
7. Restartujte Home Assistant

### Ručně

1. Stáhněte poslední release
2. Zkopírujte `custom_components/solar_forecast_api/` do složky `custom_components/` ve vašem HA
3. Restartujte Home Assistant

---

## Konfigurace

1. Jděte na **Settings → Devices & Services → Add Integration**
2. Vyhledejte **Solar Forecast API**
3. Vyplňte:
   - **Název**: např. „Moje FVE"
   - **API klíč**: váš klíč (volitelné – bez klíče funguje jen 1 den, interval 60 min)
   - **Zeměpisná šířka / délka**: vaše poloha (předvyplněna z HA)
   - **Počet stringů**: 1–10
4. Pro každý string vyplňte:
   - **Název stringu**: např. „Jih", „Západ"
   - **Sklon panelů [°]**: 0–90
   - **Azimut [°]**: orientace panelů (viz tabulka níže)
   - **Instalovaný výkon [Wp]**: výkon stringu ve watt-peak
   - **Senzor denní výroby** *(volitelné)*: entita v HA pro kalibraci
   - **Korekční faktor** *(volitelné)*: manuální korekce výkonu (0 = bez korekce)

### Pokročilá nastavení (s API klíčem)

| Parametr | Popis | Výchozí |
|----------|-------|---------|
| Počet dní | Počet dní předpovědi (1–7) | 1 (bez klíče), 4 (s klíčem) |
| Interval aktualizace | Jak často se data stahují (min) | 60 |
| Rozlišení | Hodinové nebo 15minutové hodnoty | 60 min |
| Tlumení (damping) | Tlumení výkonu ráno/večer (0–1) | 0 |
| Bez PVGIS horizontu | Vypnout automatické stínování terénem | Ne |

---

## Azimut – konvence

Integrace používá **forecast.solar** konvenci azimutu:

| Světová strana | Azimut |
|----------------|--------|
| Jih | 0° |
| Západ | 90° |
| Východ | -90° |
| Sever | ±180° |

> **Převod z pvlib/HA konvence** (0 = sever): `azimut_fs = azimut_pvlib - 180`

---

## Senzory

### Celkové senzory (vždy)

| Senzor | Popis | Jednotka |
|--------|-------|----------|
| Estimated power production - now | Aktuální odhadovaný výkon | W |
| Estimated energy production - today | Celková předpověď dnes | kWh |
| Estimated energy production - tomorrow | Celková předpověď zítra | kWh |
| Estimated energy production - remaining today | Zbývající výroba dnes | kWh |
| Estimated energy production - next hour | Předpověď příští hodiny | kWh |
| Highest power - today | Maximální výkon dnes | W |
| Peak time - today | Čas maximálního výkonu dnes | datetime |
| Highest power - tomorrow | Maximální výkon zítra | W |
| Peak time - tomorrow | Čas maximálního výkonu zítra | datetime |
| Estimated energy production - day +2 až +6 | Předpověď dalších dní | kWh |

### Per-string senzory (pouze při 2 a více stringách)

Pro každý string se vytvoří stejná sada senzorů s prefixem názvu stringu, např.:
- `String 1 Estimated energy production - today`
- `String 2 Highest power - today`
- atd.

### Počasí (vyžaduje API klíč s funkcí `weather`)

| Senzor | Popis | Jednotka |
|--------|-------|----------|
| Weather - Temperature | Aktuální teplota | °C |
| Weather - Sky clarity | Jasnost oblohy | % |
| Weather - Condition | Slovní popis počasí | – |
| Weather - Wind speed | Rychlost větru | km/h |
| Weather - Wind direction | Směr větru | – |

### Horizont (vypnuto ve výchozím stavu)

| Senzor | Popis |
|--------|-------|
| Horizon - Max elevation | Maximální elevace horizontu (PVGIS) |

---

## Funkce API klíče

API klíč odemyká rozšířené funkce. Dostupné funkce se automaticky zjistí po zadání klíče:

| Funkce | Popis |
|--------|-------|
| `actual` | Kalibrace přes skutečnou výrobu |
| `calibration` | Ukládání kalibrační historie |
| `weather` | Senzory předpovědi počasí |
| `timewindows` | Časová okna přebytků |

Bez API klíče: 1 den předpovědi, interval 60 minut, bez kalibrace a počasí.

---

## Atributy senzorů

Senzor `Estimated energy production - today` obsahuje atribut `forecast` s hodinovými hodnotami výkonu:

```json
[
  {"datetime": "2026-05-21 06:00:00", "power": 120},
  {"datetime": "2026-05-21 07:00:00", "power": 540},
  ...
]
```

---

## Požadavky

Potřebujete přístup k API na adrese [https://forecast.xnas.cz](https://forecast.xnas.cz/).

---

## Licence

MIT
