"""Testes de sanidade do cronograma e da lógica de catch-up. Rodam a
cada push via GitHub Actions (.github/workflows/testes.yml) para pegar
erros de digitação/estrutura, ou regressões na lógica de catch-up,
antes que virem um evento perdido/duplicado de verdade.

Rodar localmente: python -m unittest test_cronograma.py -v
"""

import datetime
import re
import unittest

import bot_rotina as bot

PADRAO_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _agora(hora_str, dia=4):
    """Monta um datetime de teste (sexta 2026-08-08 por padrão) na
    hora informada, já no fuso da rotina."""
    h, m = bot._minutos(hora_str) // 60, bot._minutos(hora_str) % 60
    # 2026-08-03 é uma segunda-feira, então dia=0..4 soma direto.
    data = datetime.date(2026, 8, 3) + datetime.timedelta(days=dia)
    return bot.FUSO_HORARIO.localize(datetime.datetime(data.year, data.month, data.day, h, m))


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

    def test_reunioes_mensais_datas_validas(self):
        for data in bot.REUNIOES_MENSAIS_SEXTA:
            try:
                d = datetime.date.fromisoformat(data)
            except ValueError:
                self.fail(f"Data inválida em REUNIOES_MENSAIS_SEXTA: '{data}'")
            self.assertEqual(
                d.weekday(), 4, f"Data '{data}' em REUNIOES_MENSAIS_SEXTA não é sexta-feira"
            )


class TestEventosPendentes(unittest.TestCase):
    """Cobre a lógica de catch-up (bot_rotina.eventos_pendentes), que
    evita tanto perder eventos (agendador atrasado) quanto duplicá-los
    (mesma execução, ou execuções seguintes no mesmo dia)."""

    def test_sem_checkpoint_pega_evento_do_instante(self):
        # Sexta 08:00 = "Iniciando: Trabalho - Tieta."
        pend = bot.eventos_pendentes(4, _agora("08:00"), None, -1)
        horas = [h for h, _, _, _ in pend]
        self.assertIn("08:00", horas)

    def test_nao_repete_evento_ja_coberto_pelo_checkpoint(self):
        agora = _agora("08:00")
        checkpoint_data = agora.strftime("%Y-%m-%d")
        pend = bot.eventos_pendentes(4, agora, checkpoint_data, bot._minutos("08:00"))
        horas = [h for h, _, _, _ in pend]
        self.assertNotIn("08:00", horas)

    def test_catchup_pega_evento_perdido_num_gap_grande(self):
        # Checkpoint em 09:40; agendador só roda de novo às 13:30 (mais
        # de 3h de buraco) -> tem que recuperar o 11:30 (100min de
        # atraso, o que uma janela fixa de poucos minutos jamais pegaria)
        # e o 13:30, sem duplicar nada anterior a 09:40.
        agora = _agora("13:30")
        checkpoint_data = agora.strftime("%Y-%m-%d")
        pend = bot.eventos_pendentes(4, agora, checkpoint_data, bot._minutos("09:40"))
        horas = [h for h, _, _, _ in pend]
        self.assertEqual(horas, ["11:30", "13:30"])

    def test_evento_velho_demais_e_descartado(self):
        # 06:45 com agendador rodando só às 14:00 (mais de 2h de atraso,
        # acima do default de 120min) não deve mais ser enviado.
        agora = _agora("14:00")
        pend = bot.eventos_pendentes(4, agora, None, -1, atraso_maximo_minutos=120)
        horas = [h for h, _, _, _ in pend]
        self.assertNotIn("06:45", horas)

    def test_evento_futuro_nao_e_pendente(self):
        pend = bot.eventos_pendentes(4, _agora("07:00"), None, -1)
        horas = [h for h, _, _, _ in pend]
        self.assertNotIn("08:00", horas)


if __name__ == "__main__":
    unittest.main()
