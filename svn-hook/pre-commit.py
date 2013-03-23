#!/usr/bin/python
# -*- coding: utf8 -*-
import sys, os, popen2, re, httplib, base64, json
from config import *

class PreCommit:
  """
    pre-commit hook для Subversion
  """
  def __init__(self):
    """ Запускает pre-commit hook для Subversion """
    if not ENABLED:
      return
    if len(sys.argv) != 3:
      info('Usage: %s "$REPOS" "$TXN"', sys.argv[0])
      sys.exit(1)
    self.repos = sys.argv[1]
    self.txn = sys.argv[2]
    self.printDebugInfo()
    self.conn = None
    self.projectNameById = {}
    user = self.svnlook('author')[0]
    if (user in ALLOWED_USERS):
      debug('%s in allowed users', user)
    else:
      debug('%s not in allowed users', user)
      self.checkRedmineIssues()
      self.checkTransactionSize()

  def checkTransactionSize(self):
    """ Проверяет размер транзакции """
    sum = 0
    for root, dirs, files in os.walk(self.repos + '/db/transactions/' + self.txn + '.txn', topdown=False):
      debug('%s\n', root)
      for name in files:
        path = root + '/' + name
        size = os.path.getsize(path)
        debug('%s, filesize=%s', name, size)
        checkSize(size, 'file change', MAX_FILE_BYTES)
        sum = sum + size
    checkSize(sum, 'transaction', MAX_TX_BYTES)

  def checkRedmineIssues(self):
    """ Проверяет наличие в коммите ссылки на открытую задачу redmine """
    projects = self.getProjectNames()
    if len(projects) == 0:
      return
    issues = self.getCommitIssues()
    if len(issues) == 0:
      exit('Redmine task must be specified in the comments: refs #redmine_task_number my comment...')
    unspecified = projects.copy()
    otherProjectIssues = []
    closedIssues = []
    closedStatuses = self.getClosedStatuses()
    for issue in issues:
      project, status = self.getRedmineIssue(issue)
      debug('checkRedmineIssue: issue=%s, project=%s', issue, project)
      if project not in projects:
        otherProjectIssues.append(issue)
        continue
      if status in closedStatuses:
        closedIssues.append(issue)
        continue
      unspecified.remove(project)
    if len(unspecified) > 0:
      if len(otherProjectIssues) > 0:
        error('Unable to find issue %s in project %s', otherProjectIssues, projects)
      if len(closedIssues) > 0:
        error('Redmine issue %s closed already. Reopen the issue or change issue number.', closedIssues)
      if len(otherProjectIssues) == 0 and len(closedIssues) == 0:
        error('Redmine task must be specified for project %s in the comments: refs #redmine_task_number my comment...',
          uspecified) 
      sys.exit(1)

  def getRedmineIssue(self, issue):
    data = self.redmineFind('issue', issue)
    project = self.getProjectNameById(data['issue']['project']['id'])
    status = data['issue']['status']['id']
    return (project, status)

  def getProjectNameById(self, id):
    """ Возвращает имя проекта по id """
    project = self.projectNameById.get(id)
    if project == None:
      data = self.redmineFind('project', id)
      project = data['project']['identifier']
      self.projectNameById[id] = project
    return project

  def getClosedStatuses(self):
    """ Возвращает список id закрытых статусов redmine """
    data = self.redmineFind('issue_statuses', '', '/issue_statuses.json')
    ids = [s['id'] for s in filter(lambda s: s.get('is_closed'), data['issue_statuses'])]
    debug('closedStatues=%s', ids)
    return ids
     
  def redmineFind(self, name, id, url=None):
    """ Запрашивает Redmine """
    if self.conn == None:
      self.conn = httplib.HTTPConnection(REDMINE_HOST)
      authKey = base64.b64encode(REDMINE_USER + ':' + REDMINE_PASSWORD)
      self.headers = {"Authorization":"Basic " + authKey}
    if url == None:
      url = '/' + name + 's/' + str(id) + '.json'
    self.conn.request('GET', url, headers=self.headers)
    response = self.conn.getresponse()
    if response.status == httplib.NOT_FOUND:
      exit('Unable to find Redmine %s %s', name, id)
    if response.status == httplib.UNAUTHORIZED:
      exit('Redmine autorization failed. Contact your adminstrator %s', ADMIN_EMAIL)
    if response.status != httplib.OK:
      exit('Unable to find Redmine %s %s, response status %s. Contact your adminstrator %s.\n%s',
        name, id, response.status, ADMIN_EMAIL, response.reason)
    data = json.loads(response.read())
    debug('%s=%s', url, data)
    return data

  def getProjectNames(self):
    """ Возвращает названия проектов, фиксируемых в Subversion """
    root = svnTree()
    debug('getProjectName: svnlook dirs-changed...')
    projects = set()
    for path in self.svnlook('dirs-changed'):
      dir = root
      debug('getProjectName. path=%s...', path)
      for name in splitIgnoreEmpty(path, '/'):
        debug('getProjectName. name=%s...', name)
        if dir.children == None:
          dir = None
        else:
          dir = dir.children.get(name)
        if dir == None:
          debug('getProjectName. Ignored [%s]', path)
          break
        if dir.project != None:
          debug('getProjectName. Found project [%s]', dir.project)
          projects.add(dir.project)
          break
    debug('getProjectName. Found projects %s', projects)
    return projects
       
  def getCommitIssues(self):
    """ Возвращает номера задач Redmine из комментария: refs #номер_задачи1, #номер_задачи2 """
    issues = set()
    found = False
    keyword = re.compile(r'^(refs|references|IssueID|fixes|closes)$')
    issue = re.compile(r'^#(\d+)$')
    for line in self.svnlook('log'):
      debug('getCommitIssues: line=%s', line)
      for s in re.split(r'(\s|,)+', line, flags=re.IGNORECASE):
        debug('getCommitIssues: s=%s', s)
        m = issue.match(s)
        if m != None:
          issues.add(m.group(1))
        elif not found:
          m = keyword.match(s)
          if m != None:
            found = True
    if found:
      debug('issues=%s', issues)
      return issues
    else:
      debug('no resf found, issues empty')
      return set()

  def svnlook(self, command):
    """ Возвращает результат команды svnlook """
    cmd = SVNLOOK + ' ' + command + ' ' + self.repos + ' -t ' + self.txn
    out, x, y = popen2.popen3(cmd)
    res = [s[:-1] for s in out.readlines()]
    debug('%s\n%s', cmd, res)
    return res 

  def printDebugInfo(self):
    if 4 <= LOG_LEVEL:
      for root, dirs, files in os.walk(self.repos + '/db/transactions', topdown=False):
        debug('%s, filesize=%s\n', root, str(os.stat(root)[6]))
        for name in files:
          debug('%s, filesize=%s', name, str(os.stat(root + '/' + name)[6]))

def svnTree():
  """ Возвращает дерево каталогов Subversion """
  root = SvnDir()
  for path, project in PROJECTS.items():
    dir = root
    for name in splitIgnoreEmpty(path, '/'):
      if dir.children == None:
        dir.children = {}
      dirs = dir.children
      dir = dirs.get(name)
      if dir == None:
        dir = SvnDir()
        dirs[name] = dir
    if dir.project == None:
      dir.project = project
    else:
      warn('Duplicatie definition for path %s. Ignored %s', path, project)
  return root

class SvnDir:
  """ Каталог Subversion """
  def __init__(self):
    self.children = None
    self.project  = None

def checkSize(size, name, limit):
  if size > limit:
    error("Sorry, you are trying to commit %s bytes of %s, which is larger than the limit of %s.",
      size, name, limit)
    exit("If you think you have a good reason to, email %s and ask for permission.", ADMIN_EMAIL)

def splitIgnoreEmpty(str, sep):
  return filter(lambda s: len(s)>0, str.split(sep))
  
def exit(msg, *args):
  log(1, sys.stderr, msg, args)
  sys.exit(1)

def error(msg, *args):
  log(1, sys.stderr, msg, args)

def warn(msg, *args):
  log(2, sys.stdout, msg, args)

def info(msg, *args):
  log(3, sys.stdout, msg, args)

def debug(msg, *args):
  log(4, sys.stdout, msg, args)

def log(level, out, msg, args):
  if level <= LOG_LEVEL:
    if args == None:
      print >> out, msg
    else:
      print >> out, (msg % tuple([toString(s) for s in args]))

def toString(val):
  if val == None:
    return ''
  if isinstance(val, set) or isinstance(val, list) or isinstance(val, tuple):
    return '[' + ', '.join([toString(s) for s in val]) + ']'
  return str(val).encode('string-escape')
    
if __name__ == '__main__':
  PreCommit()
