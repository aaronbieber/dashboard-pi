#!/usr/bin/python
# -*- coding: utf-8 -*-

from PyQt4 import QtGui, QtCore
import threading
import urllib
import sys
import requests
import json
import Queue
from bottle import get, request, run

message_q = Queue.Queue()

@get('/')
def get_request():
    if request.query.title:
        message_q.put(('title', urllib.unquote(request.query.title)))

    if request.query.body:
        print(request.query.body)
        message_q.put(('body', urllib.unquote(request.query.body)))


class MessageBus(QtCore.QObject):
    set_title = QtCore.pyqtSignal(str)
    set_body = QtCore.pyqtSignal(str)


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
                    print(value[1])
                    self.bus.set_body.emit(value[1])

                if value[0] == 'command' and value[1] == 'end':
                    return
            except Queue.Empty:
                continue


class Window(QtGui.QWidget):
    def __init__(self):
        super(Window, self).__init__()

        self.layout = QtGui.QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        self.title = QtGui.QLabel(self)
        self.title.setTextFormat(QtCore.Qt.RichText)
        self.title.setText(self.get_label_text('Ready!'))
        self.layout.addWidget(self.title)

        self.body = QtGui.QLabel(self)
        self.body.setText("one\ntwo\nthree")
        self.body.setAlignment(QtCore.Qt.AlignTop)
        self.layout.addWidget(self.body, 1)

        self.quit = QtGui.QPushButton('Quit', self)
        self.quit.clicked.connect(QtCore.QCoreApplication.instance().quit)
        self.quit.resize(100, 50)
        self.quit.move(370, 10)

        self.setWindowTitle('Test Window')
        self.showFullScreen()

    def get_label_text(self, text):
        return '<span style="font-size: x-large;"><b>%s</b></span>' % text

    def set_title(self, text):
        self.title.setText(self.get_label_text(text))

    def set_body(self, text):
        self.body.setText(text)

    def connect_bus(self, message_bus):
        self.bus = message_bus
        self.bus.set_title.connect(self.set_title)
        self.bus.set_body.connect(self.set_body)


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
