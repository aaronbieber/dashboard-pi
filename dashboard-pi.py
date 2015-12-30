#!/usr/bin/python
# -*- coding: utf-8 -*-

from PyQt4 import QtGui, QtCore
import threading
import urllib
import sys
import requests
import json
import Queue
import datetime
import subprocess
import bottle
import socket
from bottle import Bottle, request, ServerAdapter


class StoppableServerAdapter(ServerAdapter):
    server = None

    def run(self, handler):
        from wsgiref.simple_server import make_server, WSGIRequestHandler
        if self.quiet:
            class QuietHandler(WSGIRequestHandler):
                def log_request(*args, **kw): pass
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
        except Exception,ex:
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

    def run(self):
        while True:
            try:
                value = self.queue.get_nowait()
                if value[0] == 'title':
                    self.bus.set_title.emit(value[1])

                if value[0] == 'body':
                    self.bus.set_body.emit(value[1])

                if value[0] == 'message':
                    self.bus.set_message.emit(value[1])

                if value[0] == 'command' and value[1] == 'end':
                    print('Queue consumer is ending.')
                    return
            except Queue.Empty:
                continue


class Window(QtGui.QWidget):
    def __init__(self):
        super(Window, self).__init__()

        self.setObjectName('mainWindow')
        self.setWindowTitle('My Dashboard')
        self.setStyleSheet(('#mainWindow {'
                            '  background-color: black;'
                            '}'
                            'QLabel {'
                            '  color: white;'
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
        self.message.setStyleSheet('border: 1px solid black; border-bottom-color: #666666; color: white; padding-bottom: 5px')
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

        self.showFullScreen()
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

    server = Server(message_q)
    server.start()
    print('Started web server thread.')

    consumer = QueueConsumer(message_q, message_bus)
    consumer.start()
    print('Started queue consumer thread.')

    app = QtGui.QApplication(sys.argv)
    win = Window()
    win.connect_bus(message_bus)
    app.exec_()
    message_q.put(('command', 'end'))
    server.stop()
