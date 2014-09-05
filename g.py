#!/usr/bin/env python
# -*- coding: utf-8 -*-

import requests
import simplejson
from flask import Flask, request, jsonify
from threading import Thread
from socket import socket, AF_INET, SOCK_STREAM
import re
import sys
import traceback

import config

class G(Thread):
    def __init__(self):
        self.S = socket(AF_INET, SOCK_STREAM)
        Thread.__init__(self)

    def run(self):
        self.S.connect((config.IRC_HOST, config.IRC_PORT))
        self.F = self.S.makefile()
        self.send_raw_line('NICK %s' % config.IRC_NICK)
        self.send_raw_line('USER g 8 * :G')

        while 1:
            line = self.F.readline().strip()
            if line == '':
                break
            print '>>> %s' % line
            token = line.split(' ')
            if token[0] == 'PING':
                self.send_raw_line('PONG %s' % token[1])
            elif token[1] == '001':
                self.on_welcome()

    def send_raw_line(self, line):
        self.S.send("%s\r\n" % line)
        print '<<< %s' % line

    def send_message(self, line):
        self.send_raw_line('PRIVMSG %s :%s' % (config.IRC_CHANNEL, line))

    def on_welcome(self):
        self.send_raw_line('JOIN %s %s' % (config.IRC_CHANNEL, config.IRC_CHANNEL_PW))


def short_url(url):
    r = requests.get('http://dlun.ch/api.php?destination=' + url)
    return r.content

app = Flask(__name__)
app.config['SECRET_KEY'] = config.FLASK_SECRET_KEY

@app.route('/hook', methods=['POST'])
def hook():
    try:
        if 'Bitbucket.org' in request.headers.get('User-Agent', ''): #Bitbucket
            json = simplejson.loads(request.form['payload'])
            repo = json['repository']['name']
            branch = json['commits'][-1]['branch']
            totaldiff = ''

            server = 'bitbucket.org'
            user_name = json['user']
        else:
            json = simplejson.loads(request.data)
            repo = json['repository']['name']
            branch = re.sub(r'^refs/heads/', '', json['ref'])
            totaldiff = ''

            if 'GitHub-Hookshot' in request.headers.get('User-Agent', ''): #GitHub
                server = 'github.com'
                user_name = json['pusher']['name']
                totaldiff = ': \00302\x1f%s\x0f' % short_url(json['compare'])
            else: # GitLab
                server = config.GITLAB_SERVERS[request.headers.getlist("X-Forwarded-For")[0]]
                user_name = json['user_name']

        count = len(json['commits'])
        g.send_message('[\00306%s\x0f/\00313%s\x0f] \00315%s\x0f pushed \002%d\x0f new commit%s to \00306%s\x0f%s' % (server, repo, user_name, count, 's'[count==1:], branch, totaldiff))
        for commit in json['commits'][:3]:
            if server == 'bitbucket.org':
                commit_id = commit['raw_node'][:7]
                name = commit['author']
                message = commit['message'].replace('\n', ' ')
                url = 'https://bitbucket.org%scommits/%s' % (json['repository']['absolute_url'], commit['raw_node'])
            else:
                commit_id = commit['id'][:7]
                name = commit['author']['name']
                message = commit['message']
                url = commit['url']

            name = name.encode('utf-8')
            message = message.encode('utf-8')

            g.send_message('\00313%s\x0f/\00306%s\x0f \00314%s\x0f \00315%s\x0f: %s | \00302\x1f%s\x0f' % (repo, branch, commit_id, name, message, short_url(url)))
        if len(json['commits']) > 3:
            g.send_message('and more...')
    except Exception:
        ty, exc, tb = sys.exc_info()
        g.send_message('ERROR! %s %s' % (ty, exc))
        traceback.print_exception(ty, exc, tb)
    finally:
        return ''

if __name__ == '__main__':
    g = G()
    g.daemon = True
    g.start()

    app.run(host='127.0.0.1', port=12147, debug=False)
