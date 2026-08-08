"""
Bot de Rotina — envia avisos de início, fim e alertas da agenda semanal
para um canal do Discord via webhook.

Como funciona:
- Não precisa logar como bot (sem token, sem convite em servidor, sem
  ID de canal). Só usa a URL de um webhook do canal onde quer receber
  os avisos.
- A cada 20s verifica o horário atual (fuso America/Sao_Paulo) e dispara
  as mensagens cadastradas em CRONOGRAMA para o dia da semana e horário
  correspondentes.

Configuração:
- Crie um arquivo `.env` (veja `.env.example`) com:
    ROTINA_WEBHOOK_URL=https://discord.com/api/webhooks/....
- Instale as dependências: pip install -r requirements.txt
- Rode: python bot_rotina.py
"""

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
        ("13:00", "📚", "Iniciando: Estudo - Livro de IA."),
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
        ("13:00", "💼", "Iniciando: Trabalho - Ceia Light / PDI."),
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
        ("13:00", "💼", "Voltando ao Trabalho - Tieta."),
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
        ("13:00", "💼", "Voltando ao Trabalho - Tieta."),
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
        ("13:00", "📚", "Iniciando: Estudo - Livro de IA."),
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

# --------------------------------------------------------------------------
# Execução
# --------------------------------------------------------------------------

# Cor do embed por categoria de evento (identificada pelo emoji).
COR_PADRAO = 0x99AAB5  # cinza (Discord "blurple" neutro)
CORES = {
    "⏰": 0xFFA726,  # acordar - laranja
    "💼": 0x3B82F6,  # trabalho - azul
    "📚": 0x10B981,  # estudo - verde
    "⚠️": 0xEF4444,  # aviso - vermelho
    "🧠": 0x22C55E,  # aula - verde
    "💻": 0x22C55E,
    "🗣️": 0xA855F7,  # reunião - roxo
    "⏸️": 0x9CA3AF,  # pausa (almoço, janta, pet, café, tempo livre, etc) - cinza
    "🎓": 0x1D4ED8,  # TCC - azul escuro
    "🛌": 0x4C1D95,  # dormir - roxo escuro
    "🌙": 0x4C1D95,
}


def enviar_mensagem(hora, emoji, mensagem):
    """Envia um embed colorido (cor por categoria de evento) para o
    webhook. Retorna True se enviou com sucesso, False se falhou (não
    levanta exceção para não derrubar o loop contínuo do modo local)."""
    payload = {
        "embeds": [
            {
                "description": f"{emoji} **{hora}** — {mensagem}",
                "color": CORES.get(emoji, COR_PADRAO),
            }
        ]
    }
    try:
        resposta = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        resposta.raise_for_status()
        return True
    except requests.RequestException as erro:
        print(f"[ERRO] Falha ao enviar mensagem: {erro}")
        return False


def eventos_do_dia(dia_semana, agora):
    eventos = list(CRONOGRAMA.get(dia_semana, []))
    if dia_semana == 4 and agora.strftime("%Y-%m-%d") in REUNIOES_MENSAIS_SEXTA:
        eventos += [
            ("10:55", "⚠️", "Atenção: a reunião mensal às 11h começa em 5 minutos!"),
            ("11:00", "🗣️", "Iniciando: Reunião mensal (11h)."),
        ]
    return eventos


def _minutos(hora_str):
    h, m = hora_str.split(":")
    return int(h) * 60 + int(m)


def checar_uma_vez(janela_minutos=4):
    """Faz uma única checagem: dispara qualquer evento cujo horário caiu
    dentro dos últimos `janela_minutos` minutos. Pensado para ser chamado
    por um agendador externo (cron/GitHub Actions) a cada poucos minutos,
    sem precisar manter processo nenhum vivo. Não guarda estado entre
    execuções — a janela de tolerância evita perder avisos por atraso do
    agendador, e como cada execução roda uma vez só, não duplica envio.

    A janela precisa ficar MENOR que o menor intervalo entre dois eventos
    do mesmo dia (hoje são 5 min, ex.: aviso 14:10 -> início 14:15) —
    senão o mesmo aviso dispara de novo na execução seguinte."""
    agora = datetime.now(FUSO_HORARIO)
    dia_semana = agora.weekday()
    minutos_agora = agora.hour * 60 + agora.minute

    enviados = []
    falhas = []
    for hora, emoji, msg in eventos_do_dia(dia_semana, agora):
        diff = minutos_agora - _minutos(hora)
        if 0 <= diff <= janela_minutos:
            if enviar_mensagem(hora, emoji, msg):
                enviados.append(hora)
            else:
                falhas.append(hora)

    if enviados:
        print(f"Enviados: {enviados}")
    if not enviados and not falhas:
        print("Nenhum evento para agora.")
    if falhas:
        # Sai com erro para o GitHub Actions marcar o workflow como falho
        # e te avisar por e-mail — senão a falha passa em silêncio.
        print(f"Falharam: {falhas}")
        sys.exit(1)


def main():
    print("Bot de rotina iniciado. Monitorando horários...")
    ja_enviados = set()
    dia_referencia = None

    while True:
        agora = datetime.now(FUSO_HORARIO)

        if agora.date() != dia_referencia:
            dia_referencia = agora.date()
            ja_enviados = set()

        dia_semana = agora.weekday()  # 0 = Segunda ... 6 = Domingo
        hora_atual = agora.strftime("%H:%M")

        for hora, emoji, msg in eventos_do_dia(dia_semana, agora):
            if hora == hora_atual and hora not in ja_enviados:
                enviar_mensagem(hora, emoji, msg)
                ja_enviados.add(hora)

        time.sleep(20)


if __name__ == "__main__":
    if "--once" in sys.argv:
        checar_uma_vez()
    else:
        main()
