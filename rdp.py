#!/usr/bin/python
# -*- coding: utf8 -*-

import sys, re, os
from PyQt4 import QtGui, QtCore

class Main(QtGui.QWidget):
  def __init__(self, rdp, tab):
    app = QtGui.QApplication(sys.argv)
    QtGui.QWidget.__init__(self)
    self.rdp = rdp
    self.list = []
    expr = re.compile(r"^([^:]*):.*$")
    f = open(tab)
    try:
      for line in f:
        m = expr.match(line)
        if m != None:
          self.list.append(m.group(1))
    finally:
      f.close()
    self.setWindowTitle(u"Удалённый доступ")
    grid = QtGui.QGridLayout()
    grid.setSpacing(4)
    grid.setColumnStretch(1, 1)
    grid.addWidget(QtGui.QLabel(u"Хост:"), 0, 0)
    self.cbox = QtGui.QComboBox()
    self.cbox.addItems(self.list)
    grid.addWidget(self.cbox, 0, 1)
    ok = QtGui.QPushButton("OK")
    self.connect(ok, QtCore.SIGNAL("clicked()"), self.resktop)
    grid.addWidget(ok, 1, 0, 1, 2)
    self.setLayout(grid)
    self.resize(300, 80)
    screen = app.desktop().primaryScreen()
    size = app.desktop().screenGeometry(screen).size()
    self.move((size.width() - self.width()) / 2,
        (size.height() - self.height()) / 2)
    self.show()
    sys.exit(app.exec_())
  def resktop(self):
    self.close()
    os.system(self.rdp + ' ' + self.list[self.cbox.currentIndex()])

if __name__ == '__main__':
  if len(sys.argv) < 2:
    print "Usage: rdp.py rdp-command rdp-tab-file"
    print "Example: rdp.py $HOME/bin/rdp $HOME/bin/rdp.tab"
  else:
    Main(sys.argv[1], sys.argv[2])
