"""Testes de sanidade do cronograma. Rodam a cada push via GitHub
Actions (.github/workflows/testes.yml) para pegar erros de digitação
ou de estrutura antes que virem um evento perdido/duplicado de verdade.

Rodar localmente: python -m unittest test_cronograma.py -v
"""

import datetime
import re
import unittest

import bot_rotina as bot

PADRAO_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# Precisa bater com o valor default de checar_uma_vez() em bot_rotina.py.
JANELA_TOLERANCIA_MINUTOS = 4


class TestCronograma(unittest.TestCase):
    def test_horarios_bem_formados(self):
        for dia, eventos in bot.CRONOGRAMA.items():
            for hora, _emoji, _msg in eventos:
                self.assertRegex(
                    hora, PADRAO_HORA, f"Horário inválido '{hora}' no dia {dia}"
                )

    def test_sem_horarios_duplicados(self):
        for dia, eventos in bot.CRONOGRAMA.items():
            horas = [h for h, _, _ in eventos]
            self.assertEqual(
                len(horas), len(set(horas)),
                f"Horário duplicado no dia {dia}: {horas}",
            )

    def test_ordem_cronologica(self):
        for dia, eventos in bot.CRONOGRAMA.items():
            minutos = [bot._minutos(h) for h, _, _ in eventos]
            self.assertEqual(
                minutos, sorted(minutos), f"Dia {dia} está fora de ordem cronológica"
            )

    def test_intervalo_minimo_maior_que_janela_de_tolerancia(self):
        # A janela de tolerância do modo --once precisa ficar MENOR que o
        # menor intervalo entre dois eventos do mesmo dia — senão um
        # aviso é reenviado na execução seguinte do agendador (bug real
        # que já aconteceu: aviso das 14:10 duplicava às 14:15).
        for dia, eventos in bot.CRONOGRAMA.items():
            minutos = sorted(bot._minutos(h) for h, _, _ in eventos)
            for i in range(len(minutos) - 1):
                gap = minutos[i + 1] - minutos[i]
                self.assertGreater(
                    gap, JANELA_TOLERANCIA_MINUTOS,
                    f"Dia {dia}: intervalo de {gap}min entre eventos é menor ou "
                    f"igual à janela de tolerância ({JANELA_TOLERANCIA_MINUTOS}min) "
                    "- risco de aviso duplicado",
                )

    def test_reunioes_mensais_datas_validas(self):
        for data in bot.REUNIOES_MENSAIS_SEXTA:
            try:
                d = datetime.date.fromisoformat(data)
            except ValueError:
                self.fail(f"Data inválida em REUNIOES_MENSAIS_SEXTA: '{data}'")
            self.assertEqual(
                d.weekday(), 4, f"Data '{data}' em REUNIOES_MENSAIS_SEXTA não é sexta-feira"
            )


if __name__ == "__main__":
    unittest.main()
