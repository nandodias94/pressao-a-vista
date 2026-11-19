
import os
import json
import base64
import requests
from datetime import datetime, timezone

# ==================================================
# PRESSÃO À VISTA
# ==================================================

BASE_URL = "https://api.goal-api.com/v1"

API_KEY = os.getenv("GOAL_API_KEY")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")

STATE_FILE = "pressao_state.json"

MAX_STATS_PER_RUN = 2
MINUTE_MIN = 15
MINUTE_MAX = 85

TIMEOUT = 25

# ==================================================
# SESSÃO
# ==================================================

session = requests.Session()

session.headers.update({
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
})

# ==================================================
# ESTADO
# ==================================================

def load_state():
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        print("AVISO: estado GitHub indisponível.")
        return {"cursor": 0, "alerts": []}

    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_REPOSITORY}/contents/{STATE_FILE}"
    )

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)

        if response.status_code == 404:
            return {"cursor": 0, "alerts": []}

        response.raise_for_status()

        data = response.json()
        content = base64.b64decode(data["content"]).decode("utf-8")

        state = json.loads(content)
        state["_sha"] = data["sha"]

        return state

    except Exception as error:
        print("Erro a carregar estado:", error)
        return {"cursor": 0, "alerts": []}


def save_state(state):
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        print("Estado não guardado: falta GITHUB_TOKEN.")
        return

    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_REPOSITORY}/contents/{STATE_FILE}"
    )

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    clean_state = {
        "cursor": state.get("cursor", 0),
        "alerts": state.get("alerts", [])[-1000:]
    }

    content = base64.b64encode(
        json.dumps(clean_state, ensure_ascii=False).encode("utf-8")
    ).decode("utf-8")

    payload = {
        "message": "Atualizar estado Pressao a Vista",
        "content": content
    }

    if state.get("_sha"):
        payload["sha"] = state["_sha"]

    try:
        response = requests.put(
            url,
            headers=headers,
            json=payload,
            timeout=TIMEOUT
        )

        response.raise_for_status()
        print("Estado guardado no GitHub.")

    except Exception as error:
        print("Erro ao guardar estado:", error)


# ==================================================
# TELEGRAM
# ==================================================

def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Faltam credenciais Telegram.")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": True
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=TIMEOUT
        )

        response.raise_for_status()

        print("ALERTA ENVIADO!")
        return True

    except Exception as error:
        print("Erro Telegram:", error)
        return False


# ==================================================
# JOGOS EM DIRETO
# ==================================================

def get_live_fixtures():
    try:
        response = session.get(
            f"{BASE_URL}/fixtures/live",
            timeout=TIMEOUT
        )

        response.raise_for_status()

        data = response.json()

        if not data.get("success"):
            print("A API não confirmou sucesso.")
            return []

        fixtures = data.get("data", [])

        if not isinstance(fixtures, list):
            return []

        return fixtures

    except Exception as error:
        print("Erro ao consultar jogos:", error)
        return []


# ==================================================
# MINUTO
# ==================================================

def get_minute(value):
    try:
        if isinstance(value, int):
            return value

        text = str(value).replace("'", "").strip()

        digits = ""
        for character in text:
            if character.isdigit():
                digits += character
            else:
                break

        return int(digits) if digits else 0

    except Exception:
        return 0


# ==================================================
# ESTATÍSTICAS
# ==================================================

def number(value):
    try:
        if value is None:
            return 0

        return int(float(str(value).replace("%", "").strip()))

    except Exception:
        return 0


def get_stat_value(statistics, stat_name):
    for item in statistics:
        if not isinstance(item, dict):
            continue

        if str(item.get("type", "")).strip().lower() == stat_name.lower():
            return (
                number(item.get("home")),
                number(item.get("away"))
            )

    return 0, 0


def get_statistics(fixture_id):
    try:
        response = session.get(
            f"{BASE_URL}/fixtures/{fixture_id}/statistics",
            timeout=TIMEOUT
        )

        response.raise_for_status()

        result = response.json()

        if not result.get("success"):
            return None

        match_data = result.get("data", {}).get("match", {})

        statistics = match_data.get("fullTime", [])

        if not isinstance(statistics, list) or not statistics:
            return None

        return statistics

    except Exception as error:
        print(f"Erro nas estatísticas {fixture_id}:", error)
        return None


# ==================================================
# ANÁLISE DA PRESSÃO
# ==================================================

def analyse_pressure(statistics):
    attacks_home, attacks_away = get_stat_value(
        statistics, "Dangerous Attacks"
    )

    on_home, on_away = get_stat_value(
        statistics, "On Target"
    )

    off_home, off_away = get_stat_value(
        statistics, "Off Target"
    )

    total_dangerous = attacks_home + attacks_away

    shots_home = on_home + off_home
    shots_away = on_away + off_away

    total_shots = shots_home + shots_away
    total_on_target = on_home + on_away

    dominant_danger = max(attacks_home, attacks_away)
    danger_difference = abs(attacks_home - attacks_away)

    if attacks_home > attacks_away:
        dominant_team = "CASA"
        dominant_shots = shots_home
        dominant_on_target = on_home

    elif attacks_away > attacks_home:
        dominant_team = "FORA"
        dominant_shots = shots_away
        dominant_on_target = on_away

    else:
        dominant_team = "EQUILIBRADO"
        dominant_shots = max(shots_home, shots_away)
        dominant_on_target = max(on_home, on_away)

    criteria = {
        "Ataques perigosos": total_dangerous >= 25,
        "Remates totais": total_shots >= 7,
        "Remates à baliza": total_on_target >= 2,
        "Domínio ofensivo": dominant_danger >= 16,
        "Diferença de ataques": danger_difference >= 10
    }

    # A pressão ativa exige remates à baliza,
    # domínio ofensivo e pelo menos mais um critério.
    active = (
        criteria["Remates à baliza"]
        and criteria["Domínio ofensivo"]
        and sum(criteria.values()) >= 3
    )

    strong = all(criteria.values())

    return {
        "active": active,
        "strong": strong,
        "criteria": criteria,
        "danger_home": attacks_home,
        "danger_away": attacks_away,
        "shots_home": shots_home,
        "shots_away": shots_away,
        "on_home": on_home,
        "on_away": on_away,
        "total_dangerous": total_dangerous,
        "total_shots": total_shots,
        "total_on_target": total_on_target,
        "dominant_team": dominant_team
    }


# ==================================================
# MENSAGEM
# ==================================================

def build_message(fixture, minute, analysis, level):

    home = fixture.get("homeTeamName", "Casa")
    away = fixture.get("awayTeamName", "Fora")

    home_score = fixture.get("homeTeamScore", 0)
    away_score = fixture.get("awayTeamScore", 0)

    criteria_text = "\n".join(
        [
            f"{'✅' if passed else '❌'} {name}"
            for name, passed in analysis["criteria"].items()
        ]
    )

    if analysis["dominant_team"] == "CASA":
        dominant_name = home
    elif analysis["dominant_team"] == "FORA":
        dominant_name = away
    else:
        dominant_name = "Sem domínio claro"

    return (
        f"🚨 PRESSÃO À VISTA — {level}\n\n"
        f"⚽ {home} - {away}\n"
        f"📊 Resultado: {home_score} - {away_score}\n"
        f"⏱ Minuto: {minute}'\n\n"
        f"🔥 EQUIPA COM MAIOR PRESSÃO:\n"
        f"{dominant_name}\n\n"
        f"📈 ESTATÍSTICAS:\n"
        f"• Ataques perigosos: {analysis['danger_home']} - "
        f"{analysis['danger_away']}\n"
        f"• Remates totais: {analysis['shots_home']} - "
        f"{analysis['shots_away']}\n"
        f"• Remates à baliza: {analysis['on_home']} - "
        f"{analysis['on_away']}\n\n"
        f"🔎 CRITÉRIOS:\n{criteria_text}\n\n"
        f"⚠️ Sinal estatístico, não é garantia de golo."
    )


# ==================================================
# MOTOR PRINCIPAL
# ==================================================

def main():

    print("================================")
    print("PRESSÃO À VISTA")
    print("A analisar jogos em direto...")
    print("================================")

    if not API_KEY:
        print("ERRO: falta GOAL_API_KEY.")
        return

    fixtures = get_live_fixtures()

    print("Jogos em direto:", len(fixtures))

    eligible = []

    for fixture in fixtures:

        minute = get_minute(fixture.get("matchMinute", 0))

        if not MINUTE_MIN <= minute <= MINUTE_MAX:
            continue

        if fixture.get("matchStatus") != "LIVE":
            continue

        fixture_id = fixture.get("id")

        if fixture_id:
            eligible.append(fixture)

    print("Jogos dentro da janela:", len(eligible))

    if not eligible:
        print("Sem jogos elegíveis.")
        return

    state = load_state()

    alerts = set(state.get("alerts", []))

    # Rotação para não analisar sempre os mesmos jogos.
    cursor = state.get("cursor", 0) % len(eligible)

    ordered = eligible[cursor:] + eligible[:cursor]

    selected = ordered[:MAX_STATS_PER_RUN]

    state["cursor"] = (cursor + len(selected)) % len(eligible)

    print("Jogos selecionados:", len(selected))

    for fixture in selected:

        fixture_id = fixture.get("id")
        minute = get_minute(fixture.get("matchMinute", 0))

        period = fixture.get("matchPeriod", "UNKNOWN")

        print(
            f"A analisar: {fixture.get('homeTeamName')} - "
            f"{fixture.get('awayTeamName')} | {minute}'"
        )

        statistics = get_statistics(fixture_id)

        if statistics is None:
            print("Estatísticas indisponíveis.")
            continue

        analysis = analyse_pressure(statistics)

        if not analysis["active"]:
            print("Sem pressão suficiente.")
            continue

        level = "FORTE" if analysis["strong"] else "ATIVA"

        alert_key = f"{fixture_id}_{period}_{level}"

        if alert_key in alerts:
            print("Alerta já enviado anteriormente.")
            continue

        message = build_message(
            fixture,
            minute,
            analysis,
            level
        )

        if send_telegram(message):
            alerts.add(alert_key)
            state["alerts"] = list(alerts)[-1000:]

    save_state(state)

    print("Análise concluída.")
    print("================================")


if __name__ == "__main__":
    main()
