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
from bottle import get, post, request, run

message_q = Queue.Queue()

@get('/message')
def get_message():
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

@post('/message')
def post_message():
    if request.params.message:
        message_q.put(('message', request.params.message))
        return 'Message sent!'
    else:
        return 'You must enter a message, obviously.'

@post('/')
def post_request():
    data = request.json

    if data:
        if 'title' in data.keys():
            message_q.put(('title', urllib.unquote(data['title'])))

        if 'body' in data.keys():
            body = data['body']
            if type(body) is list:
                body = '<br>'.join(body)

            message_q.put(('body', urllib.unquote(body)))

    if request.query.title:
        message_q.put(('title', urllib.unquote(request.query.title)))

    if request.query.body:
        print(request.query.body)
        message_q.put(('body', urllib.unquote(request.query.body)))


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
                    return
            except Queue.Empty:
                continue


class Window(QtGui.QWidget):
    def __init__(self):
        super(Window, self).__init__()

        self.setWindowTitle('Test Window')
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Window, QtCore.Qt.black)
        palette.setColor(QtGui.QPalette.WindowText, QtCore.Qt.white)
        palette.setColor(QtGui.QPalette.Button, QtCore.Qt.black)
        palette.setColor(QtGui.QPalette.ButtonText, QtCore.Qt.white)
        self.setPalette(palette)

        self.layout = QtGui.QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        self.title = QtGui.QLabel(self)
        self.title.setTextFormat(QtCore.Qt.RichText)
        self.title.setText(self.get_label_text('Ready!'))
        self.layout.addWidget(self.title)

        self.body = QtGui.QLabel(self)
        self.body.setText('one\ntwo\nthree')
        self.body.setAlignment(QtCore.Qt.AlignTop)
        self.layout.addWidget(self.body, 1)

        self.message = QtGui.QLabel(self)
        self.message.setText('No message.')
        self.layout.addWidget(self.message)

        self.updated = QtGui.QLabel(self)
        self.updated.setText('')
        self.layout.addWidget(self.updated)

        self.quit = QtGui.QPushButton('Quit', self)
        self.quit.clicked.connect(QtCore.QCoreApplication.instance().quit)
        self.quit.resize(100, 50)
        self.quit.move(370, 10)

        self.showFullScreen()

    def set_updated(self):
        updated_date = datetime.datetime.now()
        updated = updated_date.strftime('%Y-%m-%d %H:%M')
        self.updated.setText('<small>%s</small>' % updated)

    def set_message(self, text):
        self.set_updated()
        self.message.setText(text)

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


class Main(threading.Thread):
    def __init__(self):
        super(Main, self).__init__()
        self.bus = MessageBus()

        consumer = QueueConsumer(message_q, self.bus)
        consumer.start()
        print('Started queue consumer thread.')

    def run(self):
        app = QtGui.QApplication(sys.argv)
        win = Window()
        win.connect_bus(self.bus)
        app.exec_()
        return


if __name__ == '__main__':
    t = Main()
    t.start()
    print('Started GUI thread.')

    run(host='0.0.0.0', port=8080)

    # Bottle will loop forever; when interrupted, we'll wind up here
    # and kill our thread by passing the end command.
    message_q.put(('command', 'end'))

    print('Process ended.')
