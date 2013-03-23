# -*- coding: utf8 -*-

# True - включить pre-commit hook, False - выключить
ENABLED = True
# перечень привилегированных пользователей
ALLOWED_USERS = ['ivanov', 'petrov']
# предельный размер транзации SVN, в байтах
MAX_TX_BYTES = 100*1024*1024
# предельный размер изменения файла SVN, в байтах
MAX_FILE_BYTES = 50*1024*1024
# почта администратора
ADMIN_EMAIL = 'admin@i-teco.ru'
# пути Subversion и соответствующие им проекты Redmine
PROJECTS = { 
  'trunk/IR199 - Безналичные расчеты': 'ir199-beznal', 
  'documents/IR199 - Безналичные расчеты': 'ir199-beznal', # один проект может принадлежать нескольким путям, но не наоборот
  '/branches/IR199 - Безналичные расчеты/': 'ir199-beznal', # допускаются лишние слеши
  'trunk/common/python': 'stand'
}
# уровень логгирования; возможные значения LOG_LEVEL: 1-error, 2-warn, 3-info, 4-debug
LOG_LEVEL = 1
# команда svnlook
SVNLOOK = '/usr/bin/svnlook'
# сервер redmine
REDMINE_HOST = 'redmine.dfu.i-teco.ru'
# пользователь Redmine, которому доступны все проекты
REDMINE_USER = 'user'
# пароль пользователя Redmine
REDMINE_PASSWORD = 'password'
