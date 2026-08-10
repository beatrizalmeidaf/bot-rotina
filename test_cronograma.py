"""Testes de sanidade do cronograma e da lógica do resumo diário. Rodam
a cada push via GitHub Actions (.github/workflows/testes.yml) para
pegar erros de digitação/estrutura, ou regressões na decisão de quando
mandar o resumo, antes que virem um dia sem notificação de verdade.

Rodar localmente: python -m unittest test_cronograma.py -v
"""

import datetime
import re
import unittest

import bot_rotina as bot

PADRAO_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _agora(hora_str, dia=0):
    """Monta um datetime de teste (semana de 2026-08-03, segunda) na
    hora informada, já no fuso da rotina. dia: 0=Segunda ... 6=Domingo."""
    h, m = bot._minutos(hora_str) // 60, bot._minutos(hora_str) % 60
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


class TestResumoPendente(unittest.TestCase):
    """Cobre a decisão de quando mandar o resumo diário
    (bot_rotina.resumo_pendente), incluindo o catch-up por atraso do
    agendador e o corte para não mandar um resumo tarde demais."""

    def test_antes_da_hora_nao_envia(self):
        deve, atraso, motivo = bot.resumo_pendente(0, _agora("06:59"), None)
        self.assertFalse(deve)
        self.assertEqual(atraso, 0)

    def test_na_hora_certa_envia_sem_atraso(self):
        deve, atraso, _motivo = bot.resumo_pendente(0, _agora("07:00"), None)
        self.assertTrue(deve)
        self.assertEqual(atraso, 0)

    def test_atrasado_mas_dentro_do_limite_ainda_envia(self):
        # HORA_RESUMO=07:00, agendador só roda 08:30 -> 90min de atraso,
        # dentro do limite de 180min.
        deve, atraso, _motivo = bot.resumo_pendente(0, _agora("08:30"), None)
        self.assertTrue(deve)
        self.assertEqual(atraso, 90)

    def test_atrasado_demais_desiste(self):
        # 210min de atraso > limite de 180min.
        deve, atraso, motivo = bot.resumo_pendente(0, _agora("10:30"), None)
        self.assertFalse(deve)
        self.assertEqual(atraso, 210)
        self.assertTrue(motivo.startswith("atrasado"))

    def test_ja_enviado_hoje_nao_envia_de_novo(self):
        agora = _agora("07:05")
        checkpoint_data = agora.strftime("%Y-%m-%d")
        deve, _atraso, _motivo = bot.resumo_pendente(0, agora, checkpoint_data)
        self.assertFalse(deve)

    def test_checkpoint_de_outro_dia_nao_bloqueia(self):
        agora = _agora("07:05")
        checkpoint_de_ontem = "2000-01-01"
        deve, _atraso, _motivo = bot.resumo_pendente(0, agora, checkpoint_de_ontem)
        self.assertTrue(deve)

    def test_fim_de_semana_sem_cronograma_nao_envia(self):
        # dia=5 -> sábado (sem chave em CRONOGRAMA)
        deve, _atraso, motivo = bot.resumo_pendente(5, _agora("07:00", dia=5), None)
        self.assertFalse(deve)
        self.assertIn("fim de semana", motivo)


if __name__ == "__main__":
    unittest.main()
