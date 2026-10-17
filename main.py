import sys
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

import requests
from playsound import playsound


# ============================================================
# APP PATHS
# Works from source and from a PyInstaller executable/folder.
# ============================================================

if getattr(sys, "frozen", False):
    # PyInstaller extracts bundled assets here at runtime.
    ASSET_DIR = Path(sys._MEIPASS)
    APP_DIR = Path(sys.executable).resolve().parent
else:
    ASSET_DIR = Path(__file__).resolve().parent
    APP_DIR = ASSET_DIR

AUDIO_FILE = ASSET_DIR / "touchdown.mp3"
ICON_FILE = ASSET_DIR / "app_icon.ico"

# User settings remain persistent in the home directory.
CONFIG_DIR = Path.home() / ".nflscore"
CONFIG_FILE = CONFIG_DIR / "config.json"

REFRESH_INTERVAL = 15000
API_URL = (
    "https://site.api.espn.com/apis/site/v2/"
    "sports/football/nfl/scoreboard"
)


# ============================================================
# NFL TEAMS, COLORS, AND ABBREVIATIONS
# Colors: primary, accent, foreground
# ============================================================

NFL_TEAMS = [
    "Arizona Cardinals", "Atlanta Falcons", "Baltimore Ravens",
    "Buffalo Bills", "Carolina Panthers", "Chicago Bears",
    "Cincinnati Bengals", "Cleveland Browns", "Dallas Cowboys",
    "Denver Broncos", "Detroit Lions", "Green Bay Packers",
    "Houston Texans", "Indianapolis Colts", "Jacksonville Jaguars",
    "Kansas City Chiefs", "Las Vegas Raiders", "Los Angeles Chargers",
    "Los Angeles Rams", "Miami Dolphins", "Minnesota Vikings",
    "New England Patriots", "New Orleans Saints", "New York Giants",
    "New York Jets", "Philadelphia Eagles", "Pittsburgh Steelers",
    "San Francisco 49ers", "Seattle Seahawks", "Tampa Bay Buccaneers",
    "Tennessee Titans", "Washington Commanders",
]

TEAM_COLORS = {
    "Arizona Cardinals": ("#97233F", "#000000", "#FFFFFF"),
    "Atlanta Falcons": ("#A71930", "#000000", "#FFFFFF"),
    "Baltimore Ravens": ("#241773", "#9E7C0C", "#FFFFFF"),
    "Buffalo Bills": ("#00338D", "#C60C30", "#FFFFFF"),
    "Carolina Panthers": ("#0085CA", "#101820", "#FFFFFF"),
    "Chicago Bears": ("#0B162A", "#C83803", "#FFFFFF"),
    "Cincinnati Bengals": ("#FB4F14", "#000000", "#FFFFFF"),
    "Cleveland Browns": ("#311D00", "#FF3C00", "#FFFFFF"),
    "Dallas Cowboys": ("#003594", "#869397", "#FFFFFF"),
    "Denver Broncos": ("#FB4F14", "#002244", "#FFFFFF"),
    "Detroit Lions": ("#0076B6", "#B0B7BC", "#FFFFFF"),
    "Green Bay Packers": ("#203731", "#FFB612", "#FFFFFF"),
    "Houston Texans": ("#03202F", "#A71930", "#FFFFFF"),
    "Indianapolis Colts": ("#002C5F", "#A2AAAD", "#FFFFFF"),
    "Jacksonville Jaguars": ("#006778", "#D7A22A", "#FFFFFF"),
    "Kansas City Chiefs": ("#E31837", "#FFB81C", "#FFFFFF"),
    "Las Vegas Raiders": ("#000000", "#A5ACAF", "#FFFFFF"),
    "Los Angeles Chargers": ("#0080C6", "#FFC20E", "#FFFFFF"),
    "Los Angeles Rams": ("#003594", "#FFA300", "#FFFFFF"),
    "Miami Dolphins": ("#008E97", "#FC4C02", "#FFFFFF"),
    "Minnesota Vikings": ("#4F2683", "#FFC62F", "#FFFFFF"),
    "New England Patriots": ("#002244", "#C60C30", "#FFFFFF"),
    "New Orleans Saints": ("#D3BC8D", "#101820", "#101820"),
    "New York Giants": ("#0B2265", "#A71930", "#FFFFFF"),
    "New York Jets": ("#125740", "#FFFFFF", "#FFFFFF"),
    "Philadelphia Eagles": ("#004C54", "#A5ACAF", "#FFFFFF"),
    "Pittsburgh Steelers": ("#101820", "#FFB612", "#FFFFFF"),
    "San Francisco 49ers": ("#AA0000", "#B3995D", "#FFFFFF"),
    "Seattle Seahawks": ("#002244", "#69BE28", "#FFFFFF"),
    "Tampa Bay Buccaneers": ("#D50A0A", "#34302B", "#FFFFFF"),
    "Tennessee Titans": ("#0C2340", "#4B92DB", "#FFFFFF"),
    "Washington Commanders": ("#5A1414", "#FFB612", "#FFFFFF"),
}

TEAM_ABBREVIATIONS = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF", "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LAR", "Miami Dolphins": "MIA", "Minnesota Vikings": "MIN",
    "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN", "Washington Commanders": "WSH",
}


# ============================================================
# GLOBAL STATE
# ============================================================

selected_team = None
last_team_score = None
last_game_id = None
refresh_job = None

score_text = None
status_text = None
team_abbr_text = None
opponent_abbr_text = None


# ============================================================
# USER SETTINGS
# ============================================================

def load_saved_team():
    """Load saved team, or return None on first launch."""
    try:
        if CONFIG_FILE.is_file():
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            team = data.get("team")
            return team if team in NFL_TEAMS else None
    except (OSError, ValueError, AttributeError, TypeError):
        return None
    return None


def save_team(team):
    """Persist the selected team in the user's home directory."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({"team": team}, indent=2), encoding="utf-8")


def get_abbreviation(team_name):
    """Return 2-3 letter team abbreviation."""
    return TEAM_ABBREVIATIONS.get(team_name, team_name[:3].upper())


# ============================================================
# ESPN SCOREBOARD API
# ============================================================

def get_nfl_game(team_name):
    """Return the selected team's current/recent scheduled game."""
    try:
        response = requests.get(API_URL, timeout=8)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as error:
        print(f"[ERROR] ESPN request failed: {error}")
        return None

    for event in data.get("events", []):
        competitions = event.get("competitions", [])
        if not competitions:
            continue

        competition = competitions[0]
        competitors = competition.get("competitors", [])
        if len(competitors) < 2:
            continue

        selected = next(
            (item for item in competitors
             if item.get("team", {}).get("displayName") == team_name),
            None,
        )
        if selected is None:
            continue

        opponent = next(item for item in competitors if item is not selected)

        try:
            team_score = int(selected.get("score", "0"))
            opponent_score = int(opponent.get("score", "0"))
        except (TypeError, ValueError):
            continue

        selected_abbr = selected.get("team", {}).get("abbreviation") or get_abbreviation(team_name)
        opponent_abbr = opponent.get("team", {}).get("abbreviation") or get_abbreviation(opponent["team"]["displayName"])

        return {
            "selected_team": team_name,
            "opponent_team": opponent["team"]["displayName"],
            "selected_score": team_score,
            "opponent_score": opponent_score,
            "selected_abbr": selected_abbr,
            "opponent_abbr": opponent_abbr,
            "status": competition.get("status", {}).get("type", {}).get(
                "description", ""
            ),
            "event_id": event.get("id"),
        }

    return None


# ============================================================
# TOUCHDOWN AUDIO
# ============================================================

def play_touchdown_audio():
    if not AUDIO_FILE.is_file():
        print(f"[ERROR] Audio file not found: {AUDIO_FILE}")
        return

    def play():
        try:
            playsound(str(AUDIO_FILE))
        except Exception as error:
            print(f"[ERROR] Audio playback failed: {error}")

    threading.Thread(target=play, daemon=True).start()


def is_touchdown(new_score, old_score):
    # Accounts for 6 (TD), 7 (TD + XP), or 8 (TD + 2PT) point jumps
    return (new_score - old_score) in (6, 7, 8)


# ============================================================
# WINDOW AND SCREEN HELPERS
# ============================================================

root = tk.Tk()
root.title("NFL Scorecard")
root.configure(bg="white")

# Set window icon if app_icon.ico is available
if ICON_FILE.is_file():
    try:
        root.iconbitmap(str(ICON_FILE))
    except Exception as e:
        print(f"[ERROR] Could not load window icon: {e}")

root.attributes("-fullscreen", True)
root.bind("<Escape>", lambda _event: root.attributes("-fullscreen", False))


def cancel_refresh():
    global refresh_job
    if refresh_job is not None:
        try:
            root.after_cancel(refresh_job)
        except tk.TclError:
            pass
        refresh_job = None


def show_team_picker():
    """Show team picker, preview team abbreviation/colors, and save choice."""
    global selected_team, last_team_score, last_game_id

    cancel_refresh()
    selected_team = None
    last_team_score = None
    last_game_id = None

    for widget in root.winfo_children():
        widget.destroy()

    default_team = load_saved_team() or "Miami Dolphins"
    primary, accent, foreground = TEAM_COLORS[default_team]
    root.configure(bg=primary)

    panel = tk.Frame(root, bg=primary)
    panel.place(relx=0.5, rely=0.5, anchor="center")

    heading = tk.Label(
        panel, text="NFL SCORECARD", font=("Arial", 17, "bold"),
        bg=primary, fg=accent
    )
    heading.pack(pady=(0, 8))

    title = tk.Label(
        panel, text="Choose Your Team", font=("Arial", 34, "bold"),
        bg=primary, fg=foreground
    )
    title.pack(pady=(0, 8))

    subtitle = tk.Label(
        panel, text="Personalize your scoreboard.", font=("Arial", 14),
        bg=primary, fg=foreground
    )
    subtitle.pack(pady=(0, 18))

    # Text Badge Preview
    preview_frame = tk.Frame(panel, bg=accent, padx=25, pady=10)
    preview_frame.pack(pady=10)

    preview_label = tk.Label(
        preview_frame, text=get_abbreviation(default_team),
        font=("Arial", 36, "bold"), bg=accent, fg=primary
    )
    preview_label.pack()

    team_choice = ttk.Combobox(
        panel, values=NFL_TEAMS, state="readonly",
        font=("Arial", 16), width=27
    )
    team_choice.pack(pady=15)
    team_choice.set(default_team)

    def update_preview(_event=None):
        team = team_choice.get()
        if team not in TEAM_COLORS:
            return

        primary_color, accent_color, foreground_color = TEAM_COLORS[team]
        root.configure(bg=primary_color)
        panel.configure(bg=primary_color)

        for widget in (heading, title, subtitle):
            widget.configure(bg=primary_color)

        heading.configure(fg=accent_color)
        title.configure(fg=foreground_color)
        subtitle.configure(fg=foreground_color)

        preview_frame.configure(bg=accent_color)
        preview_label.configure(
            text=get_abbreviation(team),
            bg=accent_color,
            fg=primary_color
        )

        start_button.configure(
            bg=accent_color,
            fg=foreground_color,
            activebackground=foreground_color,
            activeforeground=primary_color,
        )

    def start_scoreboard():
        global selected_team, last_team_score, last_game_id

        team = team_choice.get()
        if team not in NFL_TEAMS:
            return

        try:
            save_team(team)
        except OSError as error:
            messagebox.showerror(
                "Could not save team",
                f"Your selection could not be saved:\n{error}"
            )
            return

        selected_team = team
        last_team_score = None
        last_game_id = None
        show_scoreboard()

    start_button = tk.Button(
        panel, text="START SCOREBOARD", command=start_scoreboard,
        font=("Arial", 16, "bold"), relief="flat",
        padx=22, pady=12, cursor="hand2"
    )
    start_button.pack(pady=20)

    team_choice.bind("<<ComboboxSelected>>", update_preview)
    update_preview()


# ============================================================
# SCOREBOARD REFRESH
# ============================================================

def update_score():
    global refresh_job

    refresh_job = None
    if not selected_team or not root.winfo_exists():
        return

    team_at_request = selected_team

    def worker():
        game = get_nfl_game(team_at_request)

        def apply_result():
            global last_team_score, last_game_id, refresh_job

            if not root.winfo_exists() or selected_team != team_at_request:
                return

            if game:
                team_score = game["selected_score"]
                opponent_score = game["opponent_score"]
                event_id = game["event_id"]

                score_text.set(f"{team_score}  -  {opponent_score}")
                status_text.set(
                    f"{game['selected_team']} vs {game['opponent_team']}"
                    f"    |    {game['status']}"
                )

                team_abbr_text.set(game["selected_abbr"])
                opponent_abbr_text.set(game["opponent_abbr"])

                if event_id != last_game_id:
                    last_game_id = event_id
                    last_team_score = team_score
                else:
                    if last_team_score is not None and is_touchdown(
                        team_score, last_team_score
                    ):
                        play_touchdown_audio()
                    last_team_score = team_score
            else:
                score_text.set("--  -  --")
                status_text.set(
                    f"No current game found for {selected_team}"
                )
                team_abbr_text.set(get_abbreviation(selected_team))
                opponent_abbr_text.set("N/A")

            refresh_job = root.after(REFRESH_INTERVAL, update_score)

        try:
            root.after(0, apply_result)
        except tk.TclError:
            pass

    threading.Thread(target=worker, daemon=True).start()


def show_scoreboard():
    """Build the score view with selected team's colors."""
    global score_text, status_text
    global team_abbr_text, opponent_abbr_text
    global last_team_score, last_game_id

    cancel_refresh()
    last_team_score = None
    last_game_id = None

    for widget in root.winfo_children():
        widget.destroy()

    primary, accent, foreground = TEAM_COLORS[selected_team]
    root.configure(bg=primary)

    tk.Label(
        root, text=f"{selected_team.upper()} SCORECARD",
        font=("Arial", 25, "bold"), fg=foreground, bg=primary
    ).place(relx=0.5, rely=0.13, anchor="center")

    score_frame = tk.Frame(root, bg=primary)
    score_frame.place(relx=0.5, rely=0.43, anchor="center")

    # Team Abbreviation Badge
    team_frame = tk.Frame(score_frame, bg=accent, padx=20, pady=10)
    team_frame.pack(side="left", padx=24)

    team_abbr_text = tk.StringVar(value=get_abbreviation(selected_team))
    tk.Label(
        team_frame, textvariable=team_abbr_text,
        font=("Arial", 38, "bold"), fg=primary, bg=accent
    ).pack()

    # Score Text
    score_text = tk.StringVar(value="--  -  --")
    tk.Label(
        score_frame, textvariable=score_text,
        font=("Arial", 66, "bold"), fg=foreground, bg=primary
    ).pack(side="left", padx=16)

    # Opponent Abbreviation Badge
    opponent_frame = tk.Frame(score_frame, bg=accent, padx=20, pady=10)
    opponent_frame.pack(side="left", padx=24)

    opponent_abbr_text = tk.StringVar(value="---")
    tk.Label(
        opponent_frame, textvariable=opponent_abbr_text,
        font=("Arial", 38, "bold"), fg=primary, bg=accent
    ).pack()

    status_text = tk.StringVar(value="Connecting to ESPN...")
    tk.Label(
        root, textvariable=status_text, font=("Arial", 18),
        fg=foreground, bg=primary, wraplength=1000
    ).place(relx=0.5, rely=0.64, anchor="center")

    tk.Frame(root, bg=accent, height=7).place(
        relx=0.15, rely=0.73, relwidth=0.7
    )

    def change_team():
        show_team_picker()

    tk.Button(
        root, text="CHANGE TEAM", command=change_team,
        font=("Arial", 13, "bold"), bg=accent, fg=foreground,
        activebackground=foreground, activeforeground=primary,
        relief="flat", padx=18, pady=9, cursor="hand2"
    ).place(relx=0.97, rely=0.035, anchor="ne")

    tk.Label(
        root, text="Scores provided by ESPN", font=("Arial", 10),
        bg=primary, fg=foreground
    ).place(relx=0.5, rely=0.94, anchor="center")

    update_score()


# ============================================================
# START APPLICATION
# ============================================================

selected_team = load_saved_team()

if selected_team:
    show_scoreboard()
else:
    show_team_picker()

root.mainloop()