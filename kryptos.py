import krakenex
from pykrakenapi import KrakenAPI
import pandas as pd
import time
from datetime import datetime, timedelta
import streamlit as st
import matplotlib.pyplot as plt
import smtplib
from email.message import EmailMessage

# CONFIGURAÇÕES INICIAIS
MODE = "test"  # "test" ou "live"
PAIR = "MINAEUR"
INITIAL_MINA = 823.8
INITIAL_EUR = 1.26
EMA_FAST = 5
EMA_SLOW = 15
HOLDING_PERIOD_HOURS = 72  # 3 dias
FEE_RATE = 0.0016  # Taxa Kraken PRO por operação (0.16%)

# CREDENCIAIS KRAKEN (adicione as suas para modo live)
API_KEY = 'SUA_API_KEY'
API_SECRET = 'SEU_API_SECRET'
api = krakenex.API(key=API_KEY, secret=API_SECRET)
k = KrakenAPI(api)

# HISTÓRICO DE PREÇOS (baixar no modo teste)
def get_historical_data(pair, interval=60, since=None):
    if since is None:
        since = int((datetime.utcnow() - timedelta(days=30)).timestamp())
    ohlc, _ = k.get_ohlc_data(pair, interval=interval, since=since)
    return ohlc

# ESTRATÉGIA DE SINAL
def generate_signals(df):
    df['EMA_fast'] = df['close'].ewm(span=EMA_FAST).mean()
    df['EMA_slow'] = df['close'].ewm(span=EMA_SLOW).mean()
    df['signal'] = 0
    df.loc[df['EMA_fast'] > df['EMA_slow'], 'signal'] = 1
    df.loc[df['EMA_fast'] < df['EMA_slow'], 'signal'] = -1
    return df

# BACKTEST COM TAXAS KRAKEN PRO
def backtest(df, initial_mina, initial_eur):
    mina = initial_mina
    eur = initial_eur
    in_position = False
    buy_price = 0
    buy_time = None
    log = []
    total_fees = 0

    for idx, row in df.iterrows():
        price = row['close']
        signal = row['signal']

        if signal == 1 and not in_position:
            volume_bought = (eur / price) * (1 - FEE_RATE)
            fee_paid = eur * FEE_RATE
            total_fees += fee_paid

            mina += volume_bought
            buy_price = price
            eur = 0
            buy_time = idx
            in_position = True
            log.append((idx, 'BUY', price, fee_paid))

        elif in_position and (signal == -1 or (idx - buy_time).total_seconds() >= HOLDING_PERIOD_HOURS * 3600):
            proceeds = mina * price
            fee_paid = proceeds * FEE_RATE
            eur += proceeds * (1 - FEE_RATE)
            total_fees += fee_paid

            log.append((idx, 'SELL', price, fee_paid))
            mina = 0
            in_position = False

    final_value_eur = eur + mina * df.iloc[-1]['close'] * (1 - FEE_RATE)
    total_fees += mina * df.iloc[-1]['close'] * FEE_RATE if mina > 0 else 0
    return final_value_eur, log, total_fees

# EXECUÇÃO LIVE
def execute_live_trade():
    ticker = k.get_ticker_information(PAIR)
    current_price = float(ticker['c'][0])

    balance = k.get_account_balance()
    mina_bal = float(balance.loc['XMINA']['vol'])
    eur_bal = float(balance.loc['ZEUR']['vol'])

    df = get_historical_data(PAIR)
    df = generate_signals(df)
    last_signal = df.iloc[-1]['signal']

    if last_signal == 1 and eur_bal > 1:
        volume = eur_bal / current_price
        k.add_standard_order(PAIR, type='buy', ordertype='market', volume=volume)
        send_alert(f"Compra executada: {volume:.2f} MINA a {current_price:.2f} EUR")
    elif last_signal == -1 and mina_bal > 0.1:
        k.add_standard_order(PAIR, type='sell', ordertype='market', volume=mina_bal)
        send_alert(f"Venda executada: {mina_bal:.2f} MINA a {current_price:.2f} EUR")

# ALERTA EMAIL
def send_alert(message_body):
    EMAIL_ADDRESS = 'seuemail@gmail.com'
    EMAIL_PASSWORD = 'suasenha'

    msg = EmailMessage()
    msg['Subject'] = 'Alerta de Trade Kraken'
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = EMAIL_ADDRESS
    msg.set_content(message_body)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)

# DASHBOARD STREAMLIT
def show_dashboard(df, log, final_value, fees):
    st.title("Simulação de Trading - Kraken MINA/EUR")
    st.line_chart(df[['close', 'EMA_fast', 'EMA_slow']])

    for entry in log:
        st.write(f"{entry[0]} - {entry[1]} at {entry[2]:.2f} EUR | Taxa paga: {entry[3]:.4f} EUR")

    st.write(f"Valor Final Simulado: {final_value:.2f} EUR")
    st.write(f"Retorno Total: {final_value - INITIAL_EUR:.2f} EUR")
    st.write(f"Total de Taxas Pagas: {fees:.2f} EUR")

    plt.figure(figsize=(10,5))
    plt.plot(df.index, df['close'], label='Close')
    plt.plot(df.index, df['EMA_fast'], label='EMA Fast')
    plt.plot(df.index, df['EMA_slow'], label='EMA Slow')
    plt.legend()
    plt.title('Sinais e Preços')
    st.pyplot(plt)

# MAIN
if __name__ == "__main__":
    if MODE == "test":
        df = get_historical_data(PAIR)
        df = generate_signals(df)
        result, log, fees = backtest(df, INITIAL_MINA, INITIAL_EUR)
        show_dashboard(df, log, result, fees)
    elif MODE == "live":
        while True:
            execute_live_trade()
            print(f"Trade verificado em {datetime.utcnow()}.")
            time.sleep(3600)
