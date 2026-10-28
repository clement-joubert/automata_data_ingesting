# Quick Guide — SoftMetadata / ALTAG3D (mdacst3D)

## 1. Launching the application

The software is a **single Python file**, with no installation or external dependency (Tkinter ships with Python).

```bash
python SoftMetadata_V0.1.py
```

## 2. The main screen

At the top: a **toolbar** with 6 buttons; below it: **2 tabs**.

| Button | Purpose |
|---|---|
| **New batch** | Clears everything and starts a blank batch (asks for confirmation) |
| **Load XML** | Reopens an existing mdacst3D XML file for editing |
| **Session: Save / Load** | Saves / reloads the **in-progress** entry into a `_session.json` file (resume later where you left off) |
| **Export XML + folders** | Exports the XML **and** creates the measurement folder tree |
| **Export XML only** | Exports the XML file alone |

## 3. Tab "1. Deposit Information"

Describe the **batch** (the measurement campaign) in 4 sections:

1. **General Deposit Information** — Title in the format `YYYYMMDD_BatchName` *(required)*. This title is used as the XML file name **and** as the root folder name on export. Add the deposit description.
2. **Project** — Name, context, objectives, fundings, dates (`YYYY-MM-DD` format).
3. **Deposit Management** — Rights (e.g. `CC BY SA`), version, compatibility, depositor service, responsible entity.
4. **Deposit Actors** — Scientific director and creators (up to the allowed maximum, *+ Add* button).

> 💡 Each actor has 3 fields: type, name, and **identifier (ORCID / ROR / URI)**. The **🔍 ORCID** button searches the public registry and fills in the identifier automatically (`https://orcid.org/0000-…`) — the name is only filled in if it was empty.

## 4. Tab "2. Physical Objects (Samples)"

This is the **table of physical objects** in the batch:

- **+ Add a sample**: opens the object form (pre-filled with the previous object's values to speed things up).
- **Edit** (or double-click), **Duplicate**, **Move Up/Down**, **Delete** act on the selected object.

The object form has 2 tabs:

**Physical Object** — name/code *(required, e.g. `R37_1`)*; mdacst3D type + AAT type (**🔍 AAT** button); materials (**🔍 AAT** appends a term, separated by `;`, e.g. `marble (AAT:300011443)`); description; references and keywords (**🔍 Add an AAT subject**); inventory.

**Events** — two blocks, **Discovery** and **Conservation**, each with an actor (🔍 ORCID), a date (`YYYY-MM-DD`, or literal dating, or PeriodO periods) and a location (**🔍 GeoNames** button: type the place name → pick it from the list; coordinates and FR/EN names are filled in automatically).

Click **Save Sample**: the object joins the table. A *digital object* is created automatically (name = deposit title + object name, licence inherited from the rights field).

## 5. Online lookups (all the 🔍 buttons)

| Button | Service | Used for |
|---|---|---|
| 🔍 GeoNames | places (free account required) | fill in location + coordinates + FR/EN names |
| 🔍 AAT | Getty thesaurus | materials, object type, keywords → `term (AAT:id)` |
| 🔍 ORCID | researcher registry | actors' `https://orcid.org/…` identifier |

In each search window: type one or two words, press **Enter**, wait, then **double-click** the row or click "Utiliser la sélection" (Use selection). Click "Fermer" (Close) if you change your mind.

## 6. Saving and exporting

- **While entering data** → **Session: Save** (`..._session.json` file, reloaded with *Session: Load*). This is the only format that preserves the full state of the interface.
- **When done** → **Export XML + folders**: choose the *parent* folder; the application creates the root folder there (named after the deposit) containing the XML, a `Calibration/` folder and, **for each physical object**, the `HSI / Photogrammetry / Raman / pXRF / Robot / paradata` folders, each with `raw_data / processed_data / paradata`. Nothing is overwritten if the folders already exist (only the XML asks for confirmation).
- **Export XML only**: just the XML file, wherever you put it.

> ⚠️ Internet is required for online lookups; data entry and export work offline.

## 7. Quick troubleshooting

- **Empty search results**: try a single word, in English for AAT (`marble`, `amphora`), or "surname only" for ORCID.
- **Date format rejected**: `YYYY-MM-DD` only (e.g. `2024-09-01`).
- **Reopening an old batch**: *Load XML* re-imports the metadata (objects, events); raw measurement data is not affected.

---
*Workflow in short: create the deposit → add the objects one by one (forms + events) → Session: Save regularly → Export XML + folders at the end of the campaign → drop the measurement files into the matching folders.*