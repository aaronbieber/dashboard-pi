#!/usr/bin/python
# -*- coding: utf-8 -*-

from PyQt4 import QtGui, QtCore
from bottle import Bottle, request, ServerAdapter
import Queue
import datetime
import pyfscache
import requests
import signal
import socket
import subprocess
import sys
import textwrap
import threading
import time
import urllib
from pprint import pprint


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
        # signal.signal(signal.SIGHUP, self.refresh)
        # signal.signal(signal.SIGINT, self.close)

    def __reduce__(self):
        """Prevent pyfscache from attempting to pickle the thread this
        runs in.
        """
        return (self.__class__, ())

    def get_fortune(self):
        """Get a `fortune' from the local fortune program."""
        fortune = subprocess.check_output(['fortune', '-s'])
        fortune = textwrap.wrap(fortune.replace('\n', ' '), 60)
        return '<br>'.join(fortune)

    @cache
    def get_weather(self):
        """Get the (my) local weather."""
        payload = {'q': 'Brookline,MA',
                   'units': 'imperial',
                   'APPID': '60bb49289f303baf72322f1f114e1790'}
        resp = requests.get('http://api.openweathermap.org/data/2.5/weather', params=payload)
        if resp.status_code == 200:
            data = resp.json()
            return (int(round(data['main']['temp'])),
                    int(round(data['main']['temp_max'])),
                    int(round(data['main']['temp_min'])),
                    ' / '.join([c['main'] for c in data['weather']]))

    @cache
    def get_stock_price(self, symbol):
        resp = requests.get('http://download.finance.yahoo.com/d/quotes.csv?s=%s&f=l1c1' % symbol)
        if resp.status_code == 200:
            parts = resp.text.split(',')
            return (parts[0], parts[1])

    def refresh(self, signum, frame):
        print('Purging cache and refreshing...')
        cache.purge()
        self.update()
        self.wait_and_update()

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

        return data


class Updater(object):
    def __init__(self, message_q):
        super(Updater, self).__init__()
        self.queue = message_q
        self.dashboard = Dashboard()
        self.running = False
        self.last_run = None

    def start(self, delay=0):
        t = threading.Thread(name='Updater', target=self.run, args=(delay,))
        self.last_run = int(time.time())
        t.start()

    def run(self, delay):
        self.running = True
        time.sleep(delay)

        while self.running:
            if int(time.time()) - self.last_run > 5:
                self.last_run = int(time.time())
                data = self.dashboard.update()
                pprint(data)
                message_q.put(data)

                # Courtesy sleep. Think of the CPUs.
                time.sleep(0.5)

    def stop(self):
        self.running = False


class StoppableServerAdapter(ServerAdapter):
    server = None

    def run(self, handler):
        from wsgiref.simple_server import make_server, WSGIRequestHandler
        if self.quiet:
            class QuietHandler(WSGIRequestHandler):
                def log_request(*args, **kw):
                    pass
            self.options['handler_class'] = QuietHandler
        self.server = make_server(self.host, self.port, handler, **self.options)
        self.server.serve_forever()

    def stop(self):
        self.server.shutdown()


class Server(threading.Thread):
    def __init__(self, message_q):
        super(Server, self).__init__()
        self.app = Bottle()
        self.server = StoppableServerAdapter(host='0.0.0.0', port=8080)
        self.queue = message_q
        self.install_routes()

    def install_routes(self):
        self.app.route('/', method='POST', callback=self.post_index)
        self.app.route('/message', method='GET', callback=self.get_message)
        self.app.route('/message', method='POST', callback=self.post_message)

    def get_index(self):
        return 'Hello, world.'

    def run(self):
        try:
            self.app.run(server=self.server)
        except Exception, ex:
            print ex

    def stop(self):
        print('Shutting down web server.')
        self.server.stop()

    def get_message(self):
        return '''
        <html>
        <style>
        body { font-family: Helvetica, Arial, sans-serif; }
        input[type=text] { padding: 0.5em; font-size: larger; width: 600px; }
        button { padding: 0.5em; font-size: x-large; }
        </style>
        <h1>Send Me a Message</h1>
        <form action="/message" method="POST">
        <input type="text" maxlength="60" name="message"/>
        <button name="submit">Send</button>
        </form>
        </html>
        '''

    def post_message(self):
        if request.params.message:
            self.queue.put(('message', request.params.message))
            return 'Message sent!'
        else:
            return 'You must enter a message, obviously.'

    def post_index(self):
        data = request.json

        if data:
            if 'title' in data.keys():
                self.queue.put(('title', urllib.unquote(data['title'])))

            if 'body' in data.keys():
                body = data['body']
                if type(body) is list:
                    body = '<br>'.join(body)

                self.queue.put(('body', urllib.unquote(body)))

        if request.query.title:
            self.queue.put(('title', urllib.unquote(request.query.title)))

        if request.query.body:
            print(request.query.body)
            self.queue.put(('body', urllib.unquote(request.query.body)))


class MessageBus(QtCore.QObject):
    set_title = QtCore.pyqtSignal(str)
    set_body = QtCore.pyqtSignal(str)
    set_message = QtCore.pyqtSignal(str)


class QueueConsumer(threading.Thread):
    def __init__(self, message_q, message_bus):
        super(QueueConsumer, self).__init__()
        self.queue = message_q
        self.bus = message_bus
        self.running = False

    def run(self):
        self.running = True

        while self.running:
            try:
                value = self.queue.get_nowait()

                if type(value) is dict:
                    self.bus.set_title.emit(value['title'])
                    self.bus.set_body.emit('<br>'.join(value['body']))

                #if value[0] == 'title':
                #    self.bus.set_title.emit(value[1])

                #if value[0] == 'body':
                #    self.bus.set_body.emit(value[1])

                #if value[0] == 'message':
                #    self.bus.set_message.emit(value[1])

                # if value[0] == 'command' and value[1] == 'end':
                #     print('Queue consumer is ending.')
                #     return
            except Queue.Empty:
                continue

    def stop(self):
        self.running = False


class Window(QtGui.QWidget):
    def __init__(self):
        super(Window, self).__init__()

        self.resize(500, 500)
        self.setObjectName('mainWindow')
        self.setWindowTitle('My Dashboard')
        self.setStyleSheet(('#mainWindow {'
                            '  background-color: black;'
                            '}'
                            'QLabel {'
                            '  color: white;'
                            '  font-family: "DejaVu Sans";'
                            '}'))

        # Main window
        mainlayout = QtGui.QVBoxLayout(self)
        mainlayout.setContentsMargins(10, 10, 10, 10)
        mainlayout.setSpacing(10)
        self.setLayout(mainlayout)

        # Top row (title + quit button)
        toprow = QtGui.QWidget()
        toprowlayout = QtGui.QHBoxLayout()
        toprowlayout.setSpacing(0)
        toprowlayout.setContentsMargins(0, 0, 0, 0)
        toprow.setLayout(toprowlayout)

        self.title = QtGui.QLabel()
        self.title.setTextFormat(QtCore.Qt.RichText)
        self.title.setText(self.get_label_text('Ready!'))
        toprowlayout.addWidget(self.title, 1)

        self.quit = QtGui.QPushButton('Quit')
        self.quit.clicked.connect(QtCore.QCoreApplication.instance().quit)
        self.quit.setStyleSheet('padding: 10px')
        toprowlayout.addWidget(self.quit)

        mainlayout.addWidget(toprow)

        # Main window widgets
        self.body = QtGui.QLabel(self)
        self.body.setText('one\ntwo\nthree')
        self.body.setAlignment(QtCore.Qt.AlignTop)
        mainlayout.addWidget(self.body, 1)

        self.message = QtGui.QLabel(self)
        self.message.setText('No message.')
        self.message.setStyleSheet(('border: 1px solid black; '
                                    'border-bottom-color: #666666; '
                                    'color: white; padding-bottom: 5px'))
        mainlayout.addWidget(self.message)

        # Bottom row (updated timestamp + IP)
        bottomrow = QtGui.QWidget()
        bottomrowlayout = QtGui.QHBoxLayout()
        bottomrowlayout.setSpacing(0)
        bottomrowlayout.setContentsMargins(0, 0, 0, 0)
        bottomrow.setLayout(bottomrowlayout)

        self.updated = QtGui.QLabel()
        bottomrowlayout.addWidget(self.updated)

        self.ip = QtGui.QLabel()
        self.ip.setAlignment(QtCore.Qt.AlignRight)
        bottomrowlayout.addWidget(self.ip)

        mainlayout.addWidget(bottomrow)

        # self.showFullScreen()
        self.show()
        self.set_updated()
        self.set_ip_address()

    def set_ip_address(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        self.ip.setText('<small>%s</small>' % ip)

    def set_updated(self):
        updated_date = datetime.datetime.now()
        updated = updated_date.strftime('%Y-%m-%d %H:%M')
        self.updated.setText('<small>%s</small>' % updated)

    def set_message(self, text):
        self.set_updated()
        self.message.setText(text)
        subprocess.check_output(['xset', 's', 'reset'])

    def get_label_text(self, text):
        return '<span style="font-size: x-large;"><b>%s</b></span>' % text

    def set_title(self, text):
        self.set_updated()
        self.title.setText(self.get_label_text(text))

    def set_body(self, text):
        self.set_updated()
        self.body.setText(text)

    def connect_bus(self, message_bus):
        self.bus = message_bus
        self.bus.set_title.connect(self.set_title)
        self.bus.set_body.connect(self.set_body)
        self.bus.set_message.connect(self.set_message)


if __name__ == '__main__':
    message_bus = MessageBus()
    message_q = Queue.Queue()

    # server = Server(message_q)
    # server.start()
    # print('Started web server thread.')

    consumer = QueueConsumer(message_q, message_bus)
    consumer.start()
    print('Started queue consumer thread.')

    updater = Updater(message_q)
    updater.start()
    print('Started updater thread.')

    app = QtGui.QApplication(sys.argv)
    win = Window()
    win.connect_bus(message_bus)
    app.exec_()
    message_q.put(('command', 'end'))

    updater.stop()
    consumer.stop()
    # server.stop()
