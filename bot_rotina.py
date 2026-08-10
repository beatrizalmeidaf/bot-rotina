"""
Bot de Rotina — envia um resumo com a rotina do dia inteiro para um
canal do Discord via webhook, uma vez por dia, de manhã.

Como funciona:
- Não precisa logar como bot (sem token, sem convite em servidor, sem
  ID de canal). Só usa a URL de um webhook do canal onde quer receber
  os avisos.
- Em vez de mandar um aviso por evento ao longo do dia (que dependia de
  precisão de minuto do agendador externo), manda UM bloco só, listando
  toda a rotina daquele dia da semana, por volta de HORA_RESUMO.

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

# Datas (formato "YYYY-MM-DD") em que a reunião mensal de sexta às 11h
# acontece. Adicione a data do mês assim que ela for marcada, ex:
# REUNIOES_MENSAIS_SEXTA = {"2026-08-07", "2026-09-04"}
REUNIOES_MENSAIS_SEXTA = set()

# --------------------------------------------------------------------------
# Cronograma (0 = Segunda ... 4 = Sexta)
# Cada evento: hora "HH:MM", emoji e mensagem.
# --------------------------------------------------------------------------

CRONOGRAMA = {
    0: [  # SEGUNDA-FEIRA
        ("06:45", "⏰", "Bom dia! Hora de acordar, tomar café e cuidar da pet."),
        ("08:00", "💼", "Iniciando: Trabalho - Tieta."),
        ("11:30", "⏸️", "Pausa: Almoço e Janta."),
        ("13:30", "📚", "Iniciando: Estudo - Livro de IA."),
        ("14:10", "⚠️", "Atenção: a Reunião Athon começa em 5 minutos!"),
        ("14:15", "🗣️", "Iniciando: Reunião Athon."),
        ("15:15", "📚", "Fim da Reunião Athon. Voltando ao Estudo: Livro IA."),
        ("15:40", "⏸️", "Pausa: Café."),
        ("16:00", "💻", "Iniciando: Aula INF0338 (CG) [Foco Duplo: TCC ou Estudo]."),
        ("17:40", "⏸️", "Pausa: Pet e Lanche."),
        ("19:20", "⏸️", "Pausa: Terreiro (até 21h)."),
        ("21:00", "⏸️", "Pausa: Janta / Relaxar."),
        ("23:15", "🛌", "Hora de dormir!"),
    ],
    1: [  # TERÇA-FEIRA
        ("06:45", "⏰", "Bom dia! Hora de acordar e cuidar da pet."),
        ("07:55", "⚠️", "Atenção: a aula de Complexidade começa em 5 minutos!"),
        ("08:00", "🧠", "Iniciando: Aula INF0335 (Complexidade) - Foco Total."),
        ("09:40", "📚", "Fim da aula. Iniciando: Estudar Complexidade."),
        ("11:30", "⏸️", "Pausa: Almoço e Janta."),
        ("13:30", "💼", "Iniciando: Trabalho - Ceia Light / PDI."),
        ("13:55", "⚠️", "Atenção: a aula de PDI começa em 5 minutos!"),
        ("14:00", "💻", "Iniciando: Aula INF0370 (PDI) [Foco Duplo: Trab. PDI / Ceia Light]."),
        ("15:40", "⏸️", "Pausa: Café."),
        ("16:00", "💻", "Iniciando: Aula INF0289 (IHC) [Foco Duplo: Trab. PDI / Ceia Light]."),
        ("17:40", "⏸️", "Pausa: Pet e Janta."),
        ("18:50", "💻", "Iniciando: Aula INF0303 (Teste) [Foco Duplo: Athon]."),
        ("22:00", "⏸️", "Pausa: Tempo Livre até a hora de dormir."),
    ],
    2: [  # QUARTA-FEIRA
        ("06:45", "⏰", "Bom dia! Hora de acordar, tomar café e cuidar da pet."),
        ("08:00", "💼", "Iniciando: Trabalho - Tieta."),
        ("11:30", "⏸️", "Pausa: Almoço Rápido."),
        ("13:30", "💼", "Voltando ao Trabalho - Tieta."),
        ("15:40", "⏸️", "Pausa: Lavar o Cabelo."),
        ("16:00", "📚", "Iniciando: Estudo - Livro de IA."),
        ("17:40", "⏸️", "Pausa: Pet e Janta."),
        ("18:50", "🎓", "Iniciando: TCC."),
        ("23:15", "🛌", "Hora de dormir!"),
    ],
    3: [  # QUINTA-FEIRA
        ("06:45", "⏰", "Bom dia! Hora de acordar e cuidar da pet."),
        ("07:55", "⚠️", "Atenção: a aula de Complexidade começa em 5 minutos!"),
        ("08:00", "🧠", "Iniciando: Aula INF0335 (Complexidade) - Foco Total."),
        ("09:40", "💼", "Fim da aula. Iniciando: Trabalho - Tieta."),
        ("11:30", "⏸️", "Pausa: Almoço Rápido."),
        ("13:30", "💼", "Voltando ao Trabalho - Tieta."),
        ("15:40", "⏸️", "Pausa: Café."),
        ("15:55", "⚠️", "Atenção: a Reunião com a Ermis começa em 5 minutos!"),
        ("16:00", "💻", "Iniciando: Aula INF0338 (CG) [Reunião Ermis às 16h]."),
        ("16:45", "🗣️", "Fim da Reunião Ermis. Continue a Aula CG."),
        ("17:40", "⏸️", "Pausa: Pet e Janta."),
        ("18:50", "📚", "Iniciando: Estudar Complexidade."),
        ("21:00", "⏸️", "Pausa: Tempo Livre."),
        ("23:00", "🌙", "Já é tarde — hora de pensar em ir dormir."),
    ],
    4: [  # SEXTA-FEIRA
        ("06:45", "⏰", "Bom dia! Hora de acordar, tomar café e cuidar da pet."),
        ("08:00", "💼", "Iniciando: Trabalho - Tieta."),
        ("11:30", "⏸️", "Pausa: Almoço e Janta."),
        ("13:30", "📚", "Iniciando: Estudo - Livro de IA."),
        ("13:55", "⚠️", "Atenção: a aula de PDI começa em 5 minutos!"),
        ("14:00", "💻", "Iniciando: Aula INF0370 (PDI) [Foco Duplo: Athon]."),
        ("15:40", "⏸️", "Pausa: Café."),
        ("15:55", "⚠️", "Atenção: o foco com a Ermis começa em 5 minutos!"),
        ("16:00", "💻", "Iniciando: Aula INF0289 (IHC) [Foco Duplo: Ermis]."),
        ("17:40", "⏸️", "Pausa: Pet e Janta."),
        ("18:50", "💻", "Iniciando: Aula INF0290 (Projeto) [Foco Duplo: Trab. PDI / Ceia Light]."),
        ("22:00", "⏸️", "Pausa: Tempo Livre."),
    ],
}


def eventos_do_dia(dia_semana, agora):
    eventos = list(CRONOGRAMA.get(dia_semana, []))
    if dia_semana == 4 and agora.strftime("%Y-%m-%d") in REUNIOES_MENSAIS_SEXTA:
        eventos += [
            ("10:55", "⚠️", "Atenção: a reunião mensal às 11h começa em 5 minutos!"),
            ("11:00", "🗣️", "Iniciando: Reunião mensal (11h)."),
        ]
        eventos.sort(key=lambda e: _minutos(e[0]))
    return eventos


def _minutos(hora_str):
    h, m = hora_str.split(":")
    return int(h) * 60 + int(m)


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
    mais mandar um resumo "bom dia" à tarde)."""
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
    return "\n".join(f"{emoji} **{hora}** — {msg}" for hora, emoji, msg in eventos)


def enviar_resumo(dia_semana, eventos, atraso_min=None):
    """Envia o resumo do dia inteiro como um embed único. Retorna True
    se enviou com sucesso, False se falhou."""
    nome_dia = NOMES_DIAS.get(dia_semana, "Hoje")
    embed = {
        "title": f"📅 Rotina de {nome_dia}",
        "description": montar_resumo(eventos),
        "color": COR_RESUMO,
    }
    if atraso_min is not None and atraso_min > 10:
        embed["footer"] = {"text": f"⏱️ Enviado com {atraso_min} min de atraso (agendador demorou)"}

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
    mandar um "bom dia" de tardezinha)."""
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
        print(f"Resumo de {NOMES_DIAS.get(dia_semana)} enviado ({len(eventos)} eventos).")
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
