"""
Bot de Rotina — envia um resumo com a rotina do dia para um canal do
Discord via webhook, uma vez por dia, de manhã.

Como funciona:
- Não precisa logar como bot (sem token, sem convite em servidor, sem
  ID de canal). Só usa a URL de um webhook do canal onde quer receber
  os avisos.
- Manda UM bloco só por dia, listando a rotina daquele dia da semana em
  faixas de horário largas, perto de HORA_RESUMO.

Configuração:
- Crie um arquivo `.env` (veja `.env.example`) com:
    ROTINA_WEBHOOK_URL=https://discord.com/api/webhooks/....
- Instale as dependências: pip install -r requirements.txt
- Rode: python bot_rotina.py
"""

import json
import os
import sys
import time
from datetime import datetime

import pytz
import requests

# --------------------------------------------------------------------------
# Configuração
# --------------------------------------------------------------------------

def _carregar_dotenv(caminho=".env"):
    """Carrega variáveis simples de um arquivo .env (KEY=VALUE) sem
    depender do pacote python-dotenv."""
    if not os.path.exists(caminho):
        return
    with open(caminho, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip())


_carregar_dotenv()

WEBHOOK_URL = os.getenv("ROTINA_WEBHOOK_URL")
if not WEBHOOK_URL:
    raise RuntimeError(
        "Defina ROTINA_WEBHOOK_URL no arquivo .env (veja .env.example)."
    )

FUSO_HORARIO = pytz.timezone("America/Sao_Paulo")

# Onde o modo --once guarda a data do último resumo diário já enviado
# (ou já descartado por atraso), para não mandar de novo no mesmo dia.
# Esse arquivo é comitado de volta no repositório pelo workflow (veja
# .github/workflows/rotina.yml).
ARQUIVO_CHECKPOINT = "estado/ultimo_resumo.json"

# Horário-alvo do resumo diário e por quanto tempo depois disso ainda
# vale a pena mandar atrasado (depois disso, desiste do dia).
HORA_RESUMO = "07:00"
ATRASO_MAXIMO_RESUMO_MINUTOS = 180

NOMES_DIAS = {
    0: "Segunda-feira",
    1: "Terça-feira",
    2: "Quarta-feira",
    3: "Quinta-feira",
    4: "Sexta-feira",
}

# --------------------------------------------------------------------------
# Cronograma (0 = Segunda ... 4 = Sexta)
# Cada item: faixa de horário ("HH:MM - HH:MM" ou só "HH:MM") e descrição.
# --------------------------------------------------------------------------

CRONOGRAMA = {
    0: [  # SEGUNDA-FEIRA
        ("06:45 - 08:00", "Acordar"),
        ("08:00 - 11:30", "Trabalho: Tieta"),
        ("11:30 - 13:00", "Almoço e janta"),
        ("13:00 - 15:40", "Estudo: Livro IA (Reunião Athon 14:15-15:15)"),
        ("15:40 - 16:00", "Pausa"),
        ("16:00 - 17:40", "Aula: CG (foco: TCC ou estudo)"),
        ("17:40 - 19:20", "Pausa"),
        ("19:20 - 21:00", "Terreiro"),
        ("21:00 - 22:00", "Janta / relaxar"),
        ("22:00 - 23:15", "Dormir"),
    ],
    1: [  # TERÇA-FEIRA
        ("06:45 - 08:00", "Acordar"),
        ("08:00 - 09:40", "Aula: Complexidade (foco total)"),
        ("09:40 - 11:30", "Estudar: Complexidade"),
        ("11:30 - 13:00", "Almoço e janta"),
        ("13:00 - 14:00", "Trabalho: Ceia Light / PDI"),
        ("14:00 - 15:40", "Aula: PDI (foco: trabalho PDI / Ceia Light)"),
        ("15:40 - 16:00", "Pausa"),
        ("16:00 - 17:40", "Aula: IHC (foco: trabalho PDI / Ceia Light)"),
        ("17:40 - 18:50", "Janta"),
        ("18:50 - 22:00", "Aula: Teste (foco: Athon)"),
        ("22:00 - 23:15", "Tempo livre / dormir"),
    ],
    2: [  # QUARTA-FEIRA
        ("06:45 - 08:00", "Acordar"),
        ("08:00 - 11:30", "Trabalho: Tieta"),
        ("11:30 - 13:00", "Almoço rápido"),
        ("13:00 - 15:40", "Trabalho: Tieta"),
        ("15:40 - 16:00", "Pausa"),
        ("16:00 - 17:40", "Estudo: Livro IA"),
        ("17:40 - 18:50", "Janta"),
        ("18:50 - 23:15", "TCC"),
        ("23:15", "Dormir"),
    ],
    3: [  # QUINTA-FEIRA
        ("06:45 - 08:00", "Acordar"),
        ("08:00 - 09:40", "Aula: Complexidade (foco total)"),
        ("09:40 - 11:30", "Trabalho: Tieta"),
        ("11:30 - 13:00", "Almoço rápido"),
        ("13:00 - 15:40", "Trabalho: Tieta"),
        ("15:40 - 16:00", "Pausa"),
        ("16:00 - 17:40", "Aula: CG (Reunião Ermis 16:00-16:45)"),
        ("17:40 - 18:50", "Janta"),
        ("18:50 - 21:00", "Estudar: Complexidade"),
        ("21:00 - 22:00", "Tempo livre"),
        ("22:00 - 23:15", "Tempo livre / dormir"),
    ],
    4: [  # SEXTA-FEIRA
        ("06:45 - 08:00", "Acordar"),
        ("08:00 - 09:40", "Trabalho: Tieta"),
        ("09:40 - 11:30", "Trabalho: Tieta (Reunião 11h, 1x/mês)"),
        ("11:30 - 13:00", "Almoço e janta"),
        ("13:00 - 14:00", "Estudo: Livro IA"),
        ("14:00 - 15:40", "Aula: PDI (foco: Athon)"),
        ("15:40 - 16:00", "Pausa"),
        ("16:00 - 17:40", "Aula: IHC (foco: Ermis)"),
        ("17:40 - 18:50", "Janta"),
        ("18:50 - 22:00", "Aula: Projeto (foco: trabalho PDI / Ceia Light)"),
        ("22:00 - 23:15", "Tempo livre"),
    ],
}


def eventos_do_dia(dia_semana, agora):
    return list(CRONOGRAMA.get(dia_semana, []))


def _minutos(hora_str):
    h, m = hora_str.split(":")
    return int(h) * 60 + int(m)


def _inicio_minutos(faixa):
    """Extrai o horário de início de uma faixa ('HH:MM - HH:MM' ou só
    'HH:MM') em minutos desde meia-noite."""
    return _minutos(faixa.split(" - ")[0])


# --------------------------------------------------------------------------
# Checkpoint (evita mandar o resumo duas vezes no mesmo dia)
# --------------------------------------------------------------------------

def _ler_checkpoint():
    """Retorna a data (YYYY-MM-DD) do último resumo diário já enviado
    ou descartado, ou None se não existir checkpoint ainda."""
    try:
        with open(ARQUIVO_CHECKPOINT, "r", encoding="utf-8") as f:
            return json.load(f)["data"]
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
        return None


def _gravar_checkpoint(data_str):
    os.makedirs(os.path.dirname(ARQUIVO_CHECKPOINT), exist_ok=True)
    with open(ARQUIVO_CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump({"data": data_str}, f)
        f.write("\n")


# --------------------------------------------------------------------------
# Decisão de envio (função pura, sem I/O - fácil de testar)
# --------------------------------------------------------------------------

def resumo_pendente(dia_semana, agora, checkpoint_data, atraso_maximo_minutos=ATRASO_MAXIMO_RESUMO_MINUTOS):
    """Decide se o resumo do dia deve ser mandado agora.

    Retorna (deve_enviar, atraso_minutos, motivo). `atraso_minutos` é
    quanto tempo já passou de HORA_RESUMO (0 se está em cima da hora).
    Se atraso_minutos > atraso_maximo_minutos, desiste do dia (não vale
    mais mandar o resumo à tarde)."""
    hoje_str = agora.strftime("%Y-%m-%d")

    if checkpoint_data == hoje_str:
        return False, 0, "resumo de hoje já foi enviado"

    eventos = eventos_do_dia(dia_semana, agora)
    if not eventos:
        return False, 0, "hoje não tem cronograma (fim de semana)"

    minutos_agora = agora.hour * 60 + agora.minute
    atraso = minutos_agora - _minutos(HORA_RESUMO)

    if atraso < 0:
        return False, 0, "ainda não é hora do resumo"
    if atraso > atraso_maximo_minutos:
        return False, atraso, "atrasado demais, desistindo do resumo de hoje"

    return True, atraso, "pendente"


# --------------------------------------------------------------------------
# Execução
# --------------------------------------------------------------------------

COR_RESUMO = 0x5865F2  # blurple do Discord


def montar_resumo(eventos):
    return "\n".join(f"**{faixa}** — {desc}" for faixa, desc in eventos)


def enviar_resumo(dia_semana, eventos, atraso_min=None):
    """Envia o resumo do dia como um embed único. Retorna True se
    enviou com sucesso, False se falhou."""
    nome_dia = NOMES_DIAS.get(dia_semana, "Hoje")
    embed = {
        "title": f"Rotina — {nome_dia}",
        "description": montar_resumo(eventos),
        "color": COR_RESUMO,
    }
    if atraso_min is not None and atraso_min > 10:
        embed["footer"] = {"text": f"Enviado com {atraso_min} min de atraso"}

    try:
        resposta = requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)
        resposta.raise_for_status()
        return True
    except requests.RequestException as erro:
        print(f"[ERRO] Falha ao enviar resumo: {erro}")
        return False


def checar_uma_vez():
    """Roda uma vez (chamado pelo agendador externo). Manda o resumo do
    dia se ele estiver pendente; se estiver atrasado demais, desiste em
    silêncio e marca o dia como tratado, pra não ficar tentando (e nem
    mandar o resumo de tardezinha)."""
    agora = datetime.now(FUSO_HORARIO)
    hoje_str = agora.strftime("%Y-%m-%d")
    dia_semana = agora.weekday()
    checkpoint_data = _ler_checkpoint()

    deve_enviar, atraso, motivo = resumo_pendente(dia_semana, agora, checkpoint_data)
    print(motivo)

    if not deve_enviar:
        if motivo.startswith("atrasado"):
            _gravar_checkpoint(hoje_str)
        return

    eventos = eventos_do_dia(dia_semana, agora)
    if enviar_resumo(dia_semana, eventos, atraso_min=atraso):
        _gravar_checkpoint(hoje_str)
        print(f"Resumo de {NOMES_DIAS.get(dia_semana)} enviado ({len(eventos)} itens).")
    else:
        # Sai com erro para o GitHub Actions marcar o workflow como
        # falho e avisar por e-mail - sem gravar checkpoint, a próxima
        # execução tenta de novo.
        sys.exit(1)


def main():
    print("Bot de rotina iniciado (modo resumo diário, às " + HORA_RESUMO + ").")
    checkpoint_data = _ler_checkpoint()

    while True:
        agora = datetime.now(FUSO_HORARIO)
        dia_semana = agora.weekday()

        deve_enviar, atraso, _motivo = resumo_pendente(dia_semana, agora, checkpoint_data)
        if deve_enviar:
            eventos = eventos_do_dia(dia_semana, agora)
            if enviar_resumo(dia_semana, eventos, atraso_min=atraso or None):
                checkpoint_data = agora.strftime("%Y-%m-%d")
                _gravar_checkpoint(checkpoint_data)

        time.sleep(20)


if __name__ == "__main__":
    if "--once" in sys.argv:
        checar_uma_vez()
    else:
        main()
