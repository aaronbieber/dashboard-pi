#!/usr/bin/python
# -*- coding: utf-8 -*-

import pyfscache
import requests
import signal
import socket
import subprocess
import sys
import textwrap
import time

# Define our local caching decorator.
cache = pyfscache.FSCache('cache', minutes=30)


class Dashboard(object):
    """
    Gather data from the Interonlinewebnets and post it to a
    separately running dashboard program via HTTP.
    """

    def __init__(self):
        """Regular constructor."""
        # Handle INT specially
        signal.signal(signal.SIGHUP, self.refresh)
        signal.signal(signal.SIGINT, self.close)

    def get_fortune(self):
        """Get a `fortune' from the local fortune program."""
        fortune = subprocess.check_output(['fortune', '-s'])
        fortune = textwrap.wrap(fortune.replace('\n', ' '), 60)
        return '<br>'.join(fortune)

    @cache
    def get_weather(self):
        """Get the (my) local weather."""
        payload = { 'q': 'Brookline,MA',
                    'units': 'imperial',
                    'APPID': '60bb49289f303baf72322f1f114e1790'}
        resp = requests.get('http://api.openweathermap.org/data/2.5/weather', params=payload)
        if resp.status_code == 200:
            data = resp.json()
            return (int(round(data['main']['temp'])),
                    int(round(data['main']['temp_max'])),
                    int(round(data['main']['temp_min'])),
                    ' / '.join([ c['main'] for c in data['weather'] ]))

    @cache
    def get_stock_price(self, symbol):
        resp = requests.get('http://download.finance.yahoo.com/d/quotes.csv?s=%s&f=l1c1' % symbol)
        if resp.status_code == 200:
            parts = resp.text.split(',')
            return (parts[0].strip(), parts[1].strip())

    def refresh(self, signum, frame):
        print('Purging cache and refreshing...')
        cache.purge()
        self.update()
        self.wait_and_update()

    def wait_and_update(self):
        while True:
            time.sleep(600)
            self.update()

    def larger(self, text):
        return u'<font size="+1">%s</font>' % text

    def update(self):
        stock = self.get_stock_price('W')
        stock_color = 'limegreen' if stock[1][0] == '+' else 'crimson'
        stock_icon = u'☺' if stock[1][0] == '+' else u'☹'
        weather = self.get_weather()

        data = {'title': 'Your Dashboard',
                'body': [self.larger(u'%s <b>W:</b> $%s (<font color="%s">%s</font>)' % (stock_icon, stock[0], stock_color, stock[1])),
                         self.larger(u'☂ <b>Temp:</b> %s&#8457; (%s/%s), %s' % (weather[0], weather[1], weather[2], weather[3])),
                         u'',
                         self.get_fortune()]}

        try:
            requests.post('http://localhost:8080', json=data)
        except requests.ConnectionError:
            # It's OK, we'll survive.
            pass

    def close(self, signum, frame):
        print('Exiting.')
        sys.exit(0)


if __name__ == '__main__':
    d = Dashboard()
    d.update()
    d.wait_and_update()
