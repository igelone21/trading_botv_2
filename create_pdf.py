from fpdf import FPDF

class PDF(FPDF):
    def header(self):
        self.set_fill_color(30, 30, 30)
        self.rect(0, 0, 210, 20, 'F')
        self.set_font('Helvetica', 'B', 14)
        self.set_text_color(255, 255, 255)
        self.cell(0, 20, 'Linux Cheatsheet - IG Trading Bot VPS', align='C', ln=True)
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f'Seite {self.page_no()}', align='C')

    def section_title(self, num, title):
        self.ln(4)
        self.set_fill_color(50, 50, 120)
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 11)
        self.cell(0, 8, f'  {num}  {title}', fill=True, ln=True)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def cmd_row(self, cmd, desc, shade=False):
        if shade:
            self.set_fill_color(240, 240, 255)
        else:
            self.set_fill_color(255, 255, 255)
        self.set_font('Courier', 'B', 9)
        self.set_text_color(20, 20, 150)
        self.cell(90, 7, f'  {cmd}', fill=True, border='LTB')
        self.set_font('Helvetica', '', 9)
        self.set_text_color(40, 40, 40)
        self.cell(0, 7, f'  {desc}', fill=True, border='RTB', ln=True)

    def info_box(self, text):
        self.set_fill_color(255, 248, 220)
        self.set_draw_color(200, 160, 0)
        self.set_font('Helvetica', 'I', 9)
        self.set_text_color(100, 70, 0)
        self.multi_cell(0, 6, f'  {text}', fill=True, border=1)
        self.set_text_color(0, 0, 0)
        self.set_draw_color(0, 0, 0)
        self.ln(1)

pdf = PDF()
pdf.set_auto_page_break(auto=True, margin=18)
pdf.add_page()

# Pfade Box
pdf.set_font('Helvetica', 'B', 10)
pdf.set_fill_color(220, 235, 255)
pdf.cell(0, 7, '  Wichtige Pfade', fill=True, ln=True)
pdf.set_font('Courier', '', 9)
pdf.set_text_color(20, 20, 150)
paths = [
    ('Bot-Verzeichnis', '/home/user/ig-trading-bot-v2/'),
    ('Hauptskript',     '/home/user/ig-trading-bot-v2/bot.py'),
    ('Log-Datei',       '/home/user/ig-trading-bot-v2/logs/trading.log'),
    ('Config',          '/home/user/ig-trading-bot-v2/config.py'),
    ('Service',         'ig-trading-bot  (systemd)'),
]
for label, path in paths:
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(45, 6, f'  {label}:', ln=False)
    pdf.set_font('Courier', '', 9)
    pdf.set_text_color(20, 20, 150)
    pdf.cell(0, 6, path, ln=True)
pdf.set_text_color(0, 0, 0)
pdf.ln(3)

# ── 1 Navigation ──────────────────────────────────────────────
pdf.section_title('1', 'Navigation - cd, ls, pwd')
cmds = [
    ('cd /home/user/ig-trading-bot-v2', 'In Bot-Verzeichnis wechseln'),
    ('cd ~', 'Zum Home-Verzeichnis'),
    ('pwd', 'Aktuelles Verzeichnis anzeigen'),
    ('ls -la', 'Alle Dateien (auch versteckte) auflisten'),
    ('ls -lh logs/', 'Log-Ordner anzeigen (menschenlesbare Größen)'),
]
for i, (c, d) in enumerate(cmds):
    pdf.cmd_row(c, d, i % 2 == 0)

# ── 2 Dateien anzeigen ────────────────────────────────────────
pdf.section_title('2', 'Dateien anzeigen - cat, tail -f, grep')
cmds = [
    ('cat config.py', 'Datei vollständig ausgeben'),
    ('tail -f logs/trading.log', 'Log live verfolgen (Strg+C zum Beenden)'),
    ('tail -n 50 logs/trading.log', 'Letzte 50 Zeilen anzeigen'),
    ('grep "ERROR" logs/trading.log', 'Nur Fehler-Zeilen filtern'),
    ('grep -i "trade" logs/trading.log', 'Trade-Zeilen (Groß-/Kleinschreibung egal)'),
    ('grep "ERROR" logs/trading.log | tail -20', 'Letzte 20 Fehler'),
]
for i, (c, d) in enumerate(cmds):
    pdf.cmd_row(c, d, i % 2 == 0)

# ── 3 nano Editor ─────────────────────────────────────────────
pdf.section_title('3', 'nano Editor - Tastenkombinationen')
pdf.set_font('Helvetica', '', 9)
pdf.cell(0, 6, '  Datei öffnen:  nano config.py', ln=True)
pdf.ln(1)
keys = [
    ('Strg + O -> Enter', 'Speichern'),
    ('Strg + X', 'Beenden (fragt ob speichern)'),
    ('Strg + W', 'Suchen im Text'),
    ('Strg + K', 'Zeile ausschneiden'),
    ('Strg + U', 'Zeile einfügen'),
    ('Strg + G', 'Hilfe anzeigen'),
]
for i, (k, d) in enumerate(keys):
    pdf.cmd_row(k, d, i % 2 == 0)

# ── 4 Bot-Steuerung ───────────────────────────────────────────
pdf.section_title('4', 'Bot-Steuerung - systemctl')
cmds = [
    ('systemctl start ig-trading-bot', 'Bot starten'),
    ('systemctl stop ig-trading-bot', 'Bot stoppen'),
    ('systemctl restart ig-trading-bot', 'Bot neu starten'),
    ('systemctl status ig-trading-bot', 'Status anzeigen'),
    ('systemctl enable ig-trading-bot', 'Autostart beim Booten aktivieren'),
    ('systemctl disable ig-trading-bot', 'Autostart deaktivieren'),
    ('journalctl -u ig-trading-bot -f', 'Service-Logs live verfolgen'),
]
for i, (c, d) in enumerate(cmds):
    pdf.cmd_row(c, d, i % 2 == 0)
pdf.ln(1)
pdf.info_box('Tipp: Nach Änderungen an bot.py immer "systemctl restart ig-trading-bot" ausführen!')

# ── 5 Log-Datei ───────────────────────────────────────────────
pdf.section_title('5', 'Log-Datei - Live-Log, Fehler filtern')
cmds = [
    ('tail -f logs/trading.log', 'Live-Log verfolgen'),
    ('tail -f logs/trading.log | grep ERROR', 'Nur Fehler live'),
    ('grep "ERROR\\|WARNING" logs/trading.log', 'Fehler + Warnungen'),
    ('grep "$(date +%Y-%m-%d)" logs/trading.log', 'Nur heutige Einträge'),
    ('wc -l logs/trading.log', 'Anzahl Log-Zeilen'),
    ('> logs/trading.log', 'Log-Datei leeren (Vorsicht!)'),
]
for i, (c, d) in enumerate(cmds):
    pdf.cmd_row(c, d, i % 2 == 0)

# ── 6 Git ─────────────────────────────────────────────────────
pdf.section_title('6', 'Git - pull, status, log')
cmds = [
    ('git pull origin main', 'Neueste Version vom Server holen'),
    ('git status', 'Geänderte Dateien anzeigen'),
    ('git log --oneline -10', 'Letzte 10 Commits anzeigen'),
    ('git diff config.py', 'Änderungen in einer Datei anzeigen'),
    ('git stash', 'Lokale Änderungen temporär sichern'),
    ('git stash pop', 'Gesicherte Änderungen wiederherstellen'),
]
for i, (c, d) in enumerate(cmds):
    pdf.cmd_row(c, d, i % 2 == 0)

# ── 7 Backtest ────────────────────────────────────────────────
pdf.section_title('7', 'Backtest - python3 backtest.py --optimize')
cmds = [
    ('python3 backtest.py', 'Standard-Backtest ausführen'),
    ('python3 backtest.py --optimize', 'Strategie optimieren'),
    ('python3 backtest.py --days 30', 'Backtest der letzten 30 Tage'),
    ('python3 test_api.py', 'API-Verbindung testen'),
    ('python3 -c "import bot; print(\'OK\')"', 'Bot-Import testen'),
]
for i, (c, d) in enumerate(cmds):
    pdf.cmd_row(c, d, i % 2 == 0)

# ── 8 System ──────────────────────────────────────────────────
pdf.section_title('8', 'System - htop, df, ps')
cmds = [
    ('htop', 'Interaktiver Prozess-Monitor (q zum Beenden)'),
    ('ps aux | grep bot.py', 'Bot-Prozess suchen'),
    ('df -h', 'Festplattenplatz anzeigen'),
    ('free -h', 'RAM-Auslastung anzeigen'),
    ('uptime', 'Systemlaufzeit anzeigen'),
    ('who', 'Wer ist eingeloggt'),
    ('uname -r', 'Kernel-Version'),
]
for i, (c, d) in enumerate(cmds):
    pdf.cmd_row(c, d, i % 2 == 0)

# ── Schnellreferenz-Box ───────────────────────────────────────
pdf.ln(4)
pdf.set_fill_color(30, 30, 30)
pdf.set_text_color(255, 255, 255)
pdf.set_font('Helvetica', 'B', 10)
pdf.cell(0, 8, '  + Schnellreferenz - Die 5 wichtigsten Befehle', fill=True, ln=True)
pdf.set_text_color(0, 0, 0)
top5 = [
    ('systemctl status ig-trading-bot', 'Läuft der Bot?'),
    ('tail -f logs/trading.log', 'Was passiert gerade?'),
    ('systemctl restart ig-trading-bot', 'Bot neu starten'),
    ('git pull origin main', 'Updates holen'),
    ('grep "ERROR" logs/trading.log | tail', 'Letzte Fehler prüfen'),
]
for i, (c, d) in enumerate(top5):
    pdf.cmd_row(c, d, i % 2 == 0)

pdf.output('/home/user/ig-trading-bot-v2/Linux_Cheatsheet_TradingBot.pdf')
print("PDF erstellt!")
