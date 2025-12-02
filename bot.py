import requests
import telebot
import pwinput
import time
import json
import csv
import os
from dotenv import load_dotenv
load_dotenv()
from tabulate import tabulate
from datetime import datetime, timedelta

class WebScraper:
    """
    Classe responsável por realizar o scraping na API e gerenciar a comunicação com o Telegram.
    """

    def __init__(self):
        # Configurações Editáveis
        self.token   = os.getenv("TELEGRAM_TOKEN")  # substitui o valor fixo
        self.chat_id = os.getenv("CHAT_ID")         # substitui o valor fixo
        self.url_API     = "https://blaze.bet.br/api/singleplayer-originals/originals/roulette_games/recent/1"
        self.gales       = 2
        self.protection  = True

        # Estatísticas gerais
        self.win_results    = 0
        self.loss_results   = 0
        self.branco_results = 0
        self.ultimo_branco_horario = "Buscando Último Branco"
        self.win_gale1      = 0
        self.win_gale2      = 0
        self.max_hate       = 0
        self.win_hate       = 0
        self.win_primeira   = 0

        # Controles de fluxo
        self.count               = 0
        self.analisar            = True
        self.estrategia_nome     = "None"
        self.estrategias_acertos_gale = {}
        self.estrategia_pausada      = False
        self.estrategia_pausada_nome = None
        self.ultimo_branco_enviado   = None
        self.falhas             = {}
        self.acertos            = {}
        self.direction_color    = "None"
        self.message_delete     = False
        self.message_ids        = None

        # Quarentena: { estrategia_nome: ciclos_restantes }
        self.quarentena = {}

        # Telegram
        self.enviar_telegram = True
        self.bot = telebot.TeleBot(token=self.token, parse_mode="MARKDOWN")

        ## Reinício diário
        #self.date_now   = datetime.now().strftime("%d/%m/%Y")
        #self.check_date = self.date_now


    def mostrar_mensagem(self, mensagem, enviar_telegram=True):
        print(mensagem)
        if not enviar_telegram:
            return None
        try:
            return self.bot.send_message(chat_id=self.chat_id, text=mensagem)
        except Exception as e:
            print("Telegram send error:", e)
            return None


    #def restart(self):
        #if self.date_now != self.check_date:
            #print("Reiniciando bot!")
            #self.check_date = self.date_now
            ## Stickers de reinício
            #self.bot.send_sticker(self.chat_id,
                #"CAACAgEAAxkBAAEBbJJjXNcB92-_4vp2v0B3Plp9FONrDwACvgEAAsFWwUVjxQN4wmmSBCoE")
            #self.results()
            #self.win_results = self.loss_results = self.branco_results = 0
            #self.win_gale1 = self.win_gale2 = self.max_hate = 0
            #self.win_hate = self.win_primeira = 0
            #time.sleep(10)
            #self.bot.send_sticker(self.chat_id,
                #"CAACAgEAAxkBAAEBPQZi-ziImRgbjqbDkPduogMKzv0zFgACbAQAAl4ByUUIjW-sdJsr6CkE")
            #self.results()
            #return True
        #return False


    def results(self):
        # Placar geral
        total        = self.win_results + self.branco_results + self.loss_results
        percentual   = ((100 / total) * (self.win_results + self.branco_results)) if total else 0
        self.win_hate     = f"{percentual:,.2f}%"
        total_gale   = (self.win_results + self.branco_results + self.win_gale1 + self.win_gale2)
        primeira     = ((self.win_results + self.branco_results) - (self.win_gale1 + self.win_gale2)) if total_gale else 0
        self.win_primeira = f"{primeira:,.1f}"

        msg = (
            f"PLACAR = Win: {self.win_results} | Branco: {self.branco_results} | Loss: {self.loss_results}\n"
            f"Consecutivas  = {self.max_hate}\n"
            f"Assertividade = {self.win_hate}\n"
            f"Win de Primeira = {self.win_primeira}\n"
            f"Win No Gale1    = {self.win_gale1}\n"
            f"Win No Gale2    = {self.win_gale2}\n\n"
            "Acertos p/ Estratégia:"
        )

        # Monta o relatório combinando acertos e erros
        all_estrats = set(self.estrategias_acertos_gale.keys()) | set(self.falhas.keys())
        for estr in sorted(all_estrats):
            dados = self.estrategias_acertos_gale.get(estr, {
                'de_primeira': 0, 'gale1': 0, 'gale2': 0, 'branco': 0
            })
            dp = dados.get('de_primeira', 0)
            g1 = dados.get('gale1', 0)
            g2 = dados.get('gale2', 0)
            br = dados.get('branco', 0)
            errs = self.falhas.get(estr, 0)

            if estr in self.quarentena:
                ciclos = self.quarentena[estr]
                status = f"⛔ Pausada ({ciclos} resultados restantes)"
            else:
                status = "✅ Ativa"

            msg += (
                f"\n• {estr}: de 1ª={dp}, G1={g1}, G2={g2}, Branco={br}, Erros={errs} → {status}"
            )

        self.mostrar_mensagem(msg, enviar_telegram=self.enviar_telegram)
        return True


    def alert_sinal(self):
        msg = self.mostrar_mensagem("ANALISANDO, FIQUE ATENTO!!!",
                                    enviar_telegram=self.enviar_telegram)
        if msg:
            self.message_ids = msg.message_id
        self.message_delete = True


    def alert_gale(self):
        msg = self.mostrar_mensagem(f"Vamos para o {self.count}º GALE",
                                    enviar_telegram=self.enviar_telegram)
        if msg:
            self.message_ids = msg.message_id
        self.message_delete = True


    def delete(self):
        if not self.message_delete or self.message_ids is None:
            return
        try:
            self.bot.delete_message(chat_id=self.chat_id,
                                    message_id=self.message_ids)
        except Exception as e:
            print("Telegram delete error:", e)
        finally:
            self.message_delete = False
            self.message_ids = None


    def send_sinal(self, mensagem, finalnum, finalhorario, estrategia_nome_local):
        if (self.estrategia_pausada and
            self.estrategia_pausada_nome == estrategia_nome_local):
            return

        self.analisar = False
        if isinstance(self.ultimo_branco_horario, datetime):
            branco = self.ultimo_branco_horario.strftime('%H:%M:%S')
        else:
            branco = self.ultimo_branco_horario

        branco_txt = (f"{branco} Hr. Último Branco"
                      if branco != "Buscando Último Branco" else "")

        sinal_msg = (
            f"{mensagem}\n"
            f"Apostar no {self.direction_color} - " + f"Fazer até {self.gales} gales\n"
            f"Último Número: {finalnum} Hr: {finalhorario}\n"
            f"{branco_txt}\n"
        )

        self.mostrar_mensagem(sinal_msg, enviar_telegram=self.enviar_telegram)
        self.estrategia_nome = estrategia_nome_local


    def martingale(self, result, estrategia_nome_local):
        txt = "WIN"
        if self.count == 0:
            txt = "WIN de 1ª"
        elif self.count == 1:
            txt = "WIN No 1º Gale"
            self.win_gale1 += 1
        elif self.count == 2:
            txt = "WIN No 2º Gale"
            self.win_gale2 += 1
            self.win_gale1 -= 1

        if result == "WIN":
            self.win_results += 1
            self.max_hate += 1

            # garante o dicionário e incrementa acertos
            if estrategia_nome_local not in self.estrategias_acertos_gale:
                self.estrategias_acertos_gale[estrategia_nome_local] = {
                    'de_primeira': 0,
                    'gale1': 0,
                    'gale2': 0,
                    'branco': 0
                }
            if self.count == 0:
                self.estrategias_acertos_gale[estrategia_nome_local]['de_primeira'] += 1
            elif self.count == 1:
                self.estrategias_acertos_gale[estrategia_nome_local]['gale1'] += 1
            else:
                self.estrategias_acertos_gale[estrategia_nome_local]['gale2'] += 1

            self.mostrar_mensagem(f"{txt} - {estrategia_nome_local} acertou!",
                                  enviar_telegram=self.enviar_telegram)

        elif result == "LOSS":
            self.count += 1
            if self.count > self.gales:
                self.loss_results += 1
                #self.win_gale2 -= 1
                self.max_hate = 0

                # registra falha
                self.falhas[estrategia_nome_local] = (
                    self.falhas.get(estrategia_nome_local, 0) + 1
                )
                # quarentena 8 ciclos
                self.quarentena[estrategia_nome_local] = 4

                falhas_msg = "\n".join(
                    f"{e} falhou! ({self.falhas[e]} vez)"
                    for e in sorted(self.falhas, key=self.falhas.get, reverse=True)
                )
                self.mostrar_mensagem(f"LOSS - \n{falhas_msg}",
                                      enviar_telegram=self.enviar_telegram)
            else:
                self.alert_gale()
                return

        elif result == "BRANCO":
            self.branco_results += 1
            self.max_hate    += 1

            # conta branco por estratégia
            if estrategia_nome_local not in self.estrategias_acertos_gale:
                self.estrategias_acertos_gale[estrategia_nome_local] = {
                    'de_primeira': 0,
                    'gale1': 0,
                    'gale2': 0,
                    'branco': 0
                }
            self.estrategias_acertos_gale[estrategia_nome_local]['branco'] += 1

            txt_gale = ("De 1ª" if self.count == 0
                        else "No 1º Gale" if self.count == 1
                        else "No 2º Gale")
            self.mostrar_mensagem(
                f"BRANCO {self.ultimo_branco_horario} - Acertou {txt_gale} -- \n"
                f"{estrategia_nome_local} acertou!",
                enviar_telegram=self.enviar_telegram
            )

        # reset do ciclo
        self.count   = 0
        self.analisar = True
        self.results()
        #self.restart()


    def check_results(self, results):
        nome = self.estrategia_nome
        if results == "B":
            if self.protection:
                self.martingale("BRANCO", nome)
            else:
                self.martingale("LOSS", nome)
            return

        if self.direction_color == "BBB":
            self.martingale("WIN" if results == "B" else "LOSS", nome)
            return

        if results == "V":
            self.martingale("WIN" if self.direction_color == "VVV" else "LOSS", nome)
            return

        if results == "P":
            self.martingale("WIN" if self.direction_color == "PPP" else "LOSS", nome)
            return


    def update_quarantine(self):
        """
        Decrementa o contador de quarentena a cada novo resultado.
        Remove estratégias cujo contador chegou a zero e notifica saída.
        """
        to_remove = []
        for estrategia, ciclos in list(self.quarentena.items()):
            novos = ciclos - 1
            if novos <= 0:
                to_remove.append(estrategia)
            else:
                self.quarentena[estrategia] = novos

        for estrategia in to_remove:
            del self.quarentena[estrategia]
            msg = f"✅ Estratégia {estrategia} saiu da pausa!"
            self.mostrar_mensagem(msg, enviar_telegram=self.enviar_telegram)


    def start(self):
        check = []
        while True:
            self.date_now = datetime.now().strftime("%d/%m/%Y")
            time.sleep(3.3)
            try:
                resp = requests.get(self.url_API, timeout=15)
                resp.raise_for_status()
                raw = resp.json()
            except requests.RequestException as e:
                print("Erro na API Blaze:", e)
                continue

            results = [{'roll': i['roll'], 'horario': i['created_at']} for i in raw]
            if results != check:
                check = results
                self.delete()
                try:
                    self.estrategy(results)
                except Exception as e:
                    print("Erro interno na estratégia:", e)


    def estrategy(self, results):
        # cada novo resultado = decrementa quarentena
        self.update_quarantine()

        finalnum = [r['roll'] for r in results]
        finalhorario = [
            (datetime.strptime(r['horario'], '%Y-%m-%dT%H:%M:%S.%fZ') - timedelta(hours=3)
            ).strftime('%H:%M:%S')
            for r in results
        ]
        finalcor = [
            "V" if 1 <= n <= 7 else "P" if 8 <= n <= 14 else "B"
            for n in finalnum
        ]
        self.resultados = list(zip(finalnum, finalhorario, finalcor))

        # atualiza último branco
        brancos = [t for t in self.resultados if t[2] == "B"]
        if brancos:
            self.ultimo_branco_horario = brancos[0][1]
            self.ultimo_branco_enviado = self.ultimo_branco_horario
        elif self.ultimo_branco_enviado:
            self.ultimo_branco_horario = self.ultimo_branco_enviado
        else:
            self.ultimo_branco_horario = "Buscando Último Branco"

        # mostra tabela
        print(tabulate(self.resultados[:5], headers=["Número", "Horário", "Cor"]))

        if not self.analisar:
            self.check_results(finalcor[0])
            return

        with open("strategies.csv", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                estrategia_nome = row[0]
                if estrategia_nome in self.quarentena:
                    continue

                padrao, aposta = row[1].split("=")
                padrao = padrao.split("-")[::-1]
                aposta = list(aposta)

                # sinal de entrada
                if all(p == "X" or p == finalcor[i] or p == str(finalnum[i])
                       for i, p in enumerate(padrao)):
                    self.direction_color = {
                        "P": "PPP", "V": "VVV", "B": "BBB"
                    }.get(aposta[0], "None")
                    sinal_txt = f"Sinal encontrado! {estrategia_nome}. Cor: {self.direction_color}"
                    self.send_sinal(
                        sinal_txt,
                        self.resultados[0][0],
                        self.resultados[0][1],
                        estrategia_nome
                    )
                    return

                # alerta possível sinal
                alerta_segmento = padrao[1:]
                if all(p == "X" or p == finalcor[i] or p == str(finalnum[i])
                       for i, p in enumerate(alerta_segmento)):
                    self.alert_sinal()
                    return


# invoca o scraper
scraper = WebScraper()
scraper.start()