#!/usr/bin/python
# -*- coding: utf-8 -*-

import requests
import subprocess
import textwrap
import pyfscache
import time
import socket
import signal

cache = pyfscache.FSCache('cache', minutes=30)

class Dashboard(object):
    def __init__(self):
        # Handle INT specially
        signal.signal(signal.SIGINT, self.refresh)

    def get_fortune(self):
        fortune = subprocess.check_output(['fortune', '-s'])
        fortune = textwrap.wrap(fortune.replace('\n', ' '), 60)
        return '<br>'.join(fortune)

    @cache
    def get_weather(self):
        payload = { 'q': 'Brookline,MA',
                    'units': 'imperial',
                    'APPID': '60bb49289f303baf72322f1f114e1790'}
        resp = requests.get('http://api.openweathermap.org/data/2.5/weather', params=payload)
        if resp.status_code == 200:
            data = resp.json()
            return (int(round(data['main']['temp'])),
                    int(round(data['main']['temp_max'])),
                    int(round(data['main']['temp_min'])))

    @cache
    def get_stock_price(self, symbol):
        resp = requests.get('http://download.finance.yahoo.com/d/quotes.csv?s=%s&f=l1c1' % symbol)
        if resp.status_code == 200:
            parts = resp.text.split(',')
            return (parts[0], parts[1])

    def refresh(self, signum, frame):
        self.update()
        self.wait_and_update()

    def wait_and_update(self):
        while True:
            time.sleep(5)
            self.update()

    def update(self):
        stock = self.get_stock_price('W')
        stock_color = 'limegreen' if stock[1][0] == '+' else 'crimson'
        weather = self.get_weather()

        data = {'title': 'Your Dashboard',
                'body': ['<b>W:</b> $%s (<font color="%s">%s</font>)' % (stock[0], stock_color, stock[1]),
                         '<b>Temp:</b> %s&#8457; (%s/%s)' % (weather[0], weather[1], weather[2]),
                         '',
                         self.get_fortune()]}

        try:
            requests.post('http://localhost:8080', json=data)
        except requests.ConnectionError:
            # It's OK, we'll survive.
            pass


if __name__ == '__main__':
    d = Dashboard()
    d.update()
    d.wait_and_update()
