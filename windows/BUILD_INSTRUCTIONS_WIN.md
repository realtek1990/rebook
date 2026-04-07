# Instrukcja kompilacji: ReBook na Windows 🪟

Zbudowanie nowoczesnej aplikacji zawierającej logikę AI, okna customtkinter oraz drag&drop wymaga precyzyjnego poinstruowania narzędzia PyInstaller pod kątem ukrytych zależności i pakietów danych. System automatycznego śledzenia importów przez PyInstaller zazwyczaj "gubi" niewidoczne pakiety, przez co wygenerowany plik `.exe` uruchamia się z błędami.

Poniższa konfiguracja rozwiązuje całkowicie problem zgubionych bibliotek i "mrozi" program poprawnie.

## Top 4 najważniejsze modyfikatory kompilatora

### 1. Zbieranie całych klastrów binariów (GUI + Drag&Drop)
```bash
--collect-all customtkinter
--collect-all tkinterdnd2
```
* **Dlaczego:** `customtkinter` to nie tylko kod Pythona, ale też ukryte wewnątrz modułu schematy `.json` (np. palety kolorów trybu dark mode). `tkinterdnd2` korzysta ze skompilowanych binarnych bibliotek Tcl, dołączając specyficzny dla systemu plik `tkdnd.dll` (odpowiadający za upuszczanie plików). Flaga `--collect-all` zabezpiecza przeniesienie wszystkich tych twardych plików ze środowiska venv do zamkniętego pliku `.exe`.

### 2. Ukryte pakiety danych dla AI (LiteLLM)
```bash
--collect-data litellm
```
* **Dlaczego:** Biblioteka `litellm` ładuje autorskie słowniki mapowania kosztów (np. `model_prices.json`) podczas tzw. runtime'u. Brak tych plików w skompilowanej instancji wywoła w ReBook `FileNotFoundError` na samym starcie podczas inicjacji LLM API.

### 3. Celowe ukryte importy (Hidden Imports)
```bash
--hidden-import litellm
--hidden-import ebooklib
--hidden-import markdown
--hidden-import bs4
--hidden-import fitz
--hidden-import google.genai
```
* **Dlaczego:** Skrypt główny ładuje sub-moduły w sposób często izolowany (np. poprzez procesy). PyInstaller nie "widzi" powiązań parsera używanych przez backend e-booków `(fitz, bs4, ebooklib)`. Flaga gwarantuje twarde dorzucenie tych parserów na listę wewnątrz `.exe`.

### 4. Dołączenie skryptów backendu jako "czyste dane"
```bash
--add-data "corrector.py;."
--add-data "converter.py;."
--add-data "i18n.py;."
```
* **Dlaczego:** Zamiast kazać PyInstallerowi optymalizować i budować cały zintegrowany graf backendu, dołączamy skrypty jako oddzielne komponenty zachowując relatywną płaską strukturę. Ułatwia to środowisku wykonawczemu odpalać je z użyciem systemowego wywołania nowej instancji Pythona.

---

## Pełna komenda do kompilacji (.exe)

Komenda ta jest przystosowana w oryginalny sposób dla powłoki **Wiersza poleceń (cmd.exe)** ze wględu na znacznik `^` (oznaczający nową linię). 

Aby jej poprawnie użyć, otwórz CMD, przejdź do folderu `windows\dist` (upewnij się, że znajdują się tam zduplikowane pliki core backendu, jak `converter.py`!) i rozpocznij build po uprzednim wykonaniu `pip install pyinstaller`.

```cmd
pyinstaller ^
    --onefile ^
    --noconsole ^
    --name ReBook ^
    --icon "..\..\assets\icon.ico" ^
    --add-data "i18n.py;." ^
    --add-data "corrector.py;." ^
    --add-data "converter.py;." ^
    --add-data "image_translator.py;." ^
    --add-data "manual_convert.py;." ^
    --add-data "requirements.txt;." ^
    --collect-all customtkinter ^
    --collect-all tkinterdnd2 ^
    --collect-data litellm ^
    --hidden-import customtkinter ^
    --hidden-import litellm ^
    --hidden-import ebooklib ^
    --hidden-import markdown ^
    --hidden-import bs4 ^
    --hidden-import markdownify ^
    --hidden-import PIL ^
    --hidden-import fitz ^
    --hidden-import image_translator ^
    --hidden-import google.genai ^
    rebook_win.py
```
