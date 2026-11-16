# Volym – personlig träningslogg

En mobilanpassad webbapp med PIN, SQLite-databas, träningskalender, loggning per set, kroppsvikt, grafer och 12-veckorsprogram.

## Starta

1. Installera Python 3.10+.
2. `pip install -r requirements.txt`
3. Sätt miljövariablerna `APP_PIN` (din privata PIN, gärna 6+ siffror) och `SECRET_KEY` (minst 32 slumpmässiga tecken). Exempel på Mac/Linux:
   `export APP_PIN='din-hemliga-kod'; export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"`
4. `python app.py`
5. Öppna http://127.0.0.1:5000

Data sparas i `volym.sqlite3` och finns kvar efter omstart. Säkerhetskopiera denna fil. För användning på flera enheter behöver du driftsätta appen på en server med beständig disk och HTTPS. **Exponera inte den inbyggda Flask-servern direkt på internet.** För serverdrift: `waitress-serve --listen=127.0.0.1:8080 app:app` bakom en HTTPS reverse proxy, och sätt `COOKIE_SECURE=1`. PIN är en förenklad autentisering, inte likvärdig med ett fullständigt kontosystem.

Ingen PIN lagras i frontend eller källkod. Miljövariabler behövs innan start.
