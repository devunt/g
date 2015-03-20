#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
from flask import Flask, request, jsonify
from threading import Thread
from socket import socket, AF_INET, SOCK_STREAM
import re
import sys
import traceback

import config


app = Flask(__name__)
app.config['SECRET_KEY'] = config.FLASK_SECRET_KEY


# Alert added config directive
if hasattr(config, 'TRUST_PROXY') == False:
    print(" * `config.TRUST_PROXY` is added")
    print(" * By default `config.TRUST_PROXY` is False")
    print(" * If you are using reverse proxy, add `TRUST_PROXY = True` at your config.py")
    config.TRUST_PROXY = False


# ===== IRC ===== #
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
            print('>>> %s' % line)
            token = line.split(' ')
            if token[0] == 'PING':
                self.send_raw_line('PONG %s' % token[1])
            elif token[1] == '001':
                self.on_welcome()

    def send_raw_line(self, line):
        self.S.send(('%s\r\n' % line).encode())
        print('<<< %s' % line)

    def send_message(self, line):
        self.send_raw_line('PRIVMSG %s :%s' % (config.IRC_CHANNEL, line))

    def on_welcome(self):
        self.send_raw_line('JOIN %s %s' % (config.IRC_CHANNEL, config.IRC_CHANNEL_PW))


def short_url(url):
    r = requests.get('http://dlun.ch/api.php?destination=' + url)
    return r.content.decode()


# ===== Flask ===== #
@app.route('/hook', methods=['POST'])
def hook():
    try:
        event = ''
        event_map = {
            'ping': ping,
            'push': push,
            'issue': issue,
            'pr': pr
        }

        if 'Bitbucket.org' in request.headers.get('User-Agent', ''): # Bitbucket
            if 'payload' in request.form:
                payload = json.loads(request.form['payload'])
                event = 'push'
            else:
                payload = json.loads(request.data.decode())
                event = 'pr'

            print(payload)

            server = 'bitbucket.org'

        elif 'GitHub-Hookshot' in request.headers.get('User-Agent', ''): # GitHub
            payload = json.loads(request.data.decode())

            server = 'github.com'

            if request.headers.get('X-Github-Event', '') == 'ping':
                event = 'ping'
            elif request.headers.get('X-Github-Event', '') == 'issues':
                event = 'issue'
            elif request.headers.get('X-Github-Event', '') == 'pull_request':
                event = 'pr'
            else:
                event = 'push'

        else: # GitLab
            payload = json.loads(request.data.decode())
            
            remote_addr = request.remote_addr
            access_route = request.access_route

            if config.TRUST_PROXY and access_route:
                server_ip = access_route[0]
            else:
                server_ip = remote_addr

            server = config.GITLAB_SERVERS.get(server_ip, server_ip)

            if 'object_kind' in payload:
                if payload['object_kind'] == 'issue':
                    event = 'issue'
                elif payload['object_kind'] == 'merge_request':
                    event = 'pr'
            else:
                event = 'push'

        event_map[event](server, payload)

    except Exception:
        ty, exc, tb = sys.exc_info()
        g.send_message('ERROR! %s %s' % (ty, exc))
        traceback.print_exception(ty, exc, tb)

    finally:
        return ''


# ===== Hook to IRC ===== #
def ping(server, payload):
    # Bitbucket doesn't have ping hook

    if server == 'github.com':
        repo = payload['repository']['name']
        user_name = payload['sender']['login']
        url = ': \00302\x1f%s\x0f' % short_url(payload['repository']['html_url'])

    # Gitlab doesn't have ping hook
    # There is 'Test Hook' button that works as push hook

    else:
        return

    g.send_message('[\00306%s\x0f/\00313%s\x0f] \00315%s\x0f added new repository%s' % (server, repo, user_name, url))

def push(server, payload):
    if server == 'bitbucket.org':
        repo = payload['repository']['name']
        branch = payload['commits'][-1]['branch']
        user_name = payload['user']
        compare = ''

    elif server == 'github.com':
        repo = payload['repository']['name']
        branch = re.sub(r'^refs/heads/', '', payload['ref'])
        user_name = payload['pusher']['name']
        compare = ': \00302\x1f%s\x0f' % short_url(payload['compare'])

    else:
        repo = payload['repository']['name']
        branch = re.sub(r'^refs/heads/', '', payload['ref'])
        user_name = payload['user_name']
        compare = ''

    count = len(payload['commits'])

    g.send_message('[\00306%s\x0f/\00313%s\x0f] \00315%s\x0f pushed \002%d\x0f new commit%s to \00306%s\x0f%s' % (server, repo, user_name, count, 's'[count==1:], branch, compare))

    for commit in payload['commits'][:3]:
        if server == 'bitbucket.org':
            commit_id = commit['raw_node'][:7]
            name = commit['author']
            message = commit['message']
            url = 'https://bitbucket.org%scommits/%s' % (payload['repository']['absolute_url'], commit['raw_node'])

        else:
            commit_id = commit['id'][:7]
            name = commit['author']['name']
            message = commit['message']
            url = commit['url']

        message = message.splitlines()[0]

        g.send_message('\00313%s\x0f/\00306%s\x0f \00314%s\x0f \00315%s\x0f: %s | \00302\x1f%s\x0f' % (repo, branch, commit_id, name, message, short_url(url)))

    if len(payload['commits']) > 3:
        g.send_message('and more...')

def issue(server, payload):
    # Bitbucket doesn't have issue hook

    if server == 'github.com':
        repo = payload['repository']['name']
        user_name = payload['issue']['user']['login']
        action = payload['action']
        title = payload['issue']['title']
        number = payload['issue']['number']
        url = ': \00302\x1f%s\x0f' % short_url(payload['issue']['html_url'])

    else:
        if payload['object_attributes']['action'] == 'update':
            # It does not react at issue status update
            # It only reacts at issue open|close|reopen
            return

        repo = re.search(r'/([^/]*)/issues/\d+$', payload['object_attributes']['url']).group(1)
        user_name = payload['user']['name']
        action = payload['object_attributes']['state']
        title = payload['object_attributes']['title']
        number = payload['object_attributes']['iid']
        url = ''

    g.send_message('[\00306%s\x0f/\00313%s\x0f] \00315%s\x0f %s an issue' % (server, repo, user_name, action))
    g.send_message('\00314#%d\x0f %s%s' % (number, title, url))

def pr(server, payload):
    if server == 'bitbucket.org':
        if 'pullrequest_created' in payload:
            payload_root = payload['pullrequest_created']
            action = 'created'

            repo = payload_root['destination']['repository']['name']
            user_name = payload_root['author']['display_name']
            title = payload_root['title']
            number = payload_root['id']
            url = ': \00302\x1f%s\x0f' % short_url(payload_root['link']['href'])
        elif 'pullrequest_merged' in payload:
            payload_root = payload['pullrequest_merged']
            action = 'merged'

            repo = payload_root['destination']['repository']['name']
            user_name = payload_root['author']['display_name']
            title = payload_root['title']
            number = None
            url = ''
        else:
            # There is still many events left, maybe later?
            #     Approval, Comment Created, Comment Deleted, Comment Updated
            #     Declined, Approve Unset, Updated
            return


    elif server == 'github.com':
        repo = payload['repository']['name']
        user_name = payload['sender']['login']
        action = payload['action']
        title = payload['pull_request']['title']
        number = payload['pull_request']['number']
        url = ': \00302\x1f%s\x0f' % short_url(payload['pull_request']['html_url'])

        if action == 'assigned':
            action = 'assigned %s to' % payload['pull_request']['assignee']['login']

    else:
        repo = payload['object_attributes']['target']['name']
        user_name = payload['user']['name']
        action = payload['object_attributes']['state']
        title = payload['object_attributes']['title']
        number = payload['object_attributes']['iid']
        url = ''

        if payload['object_attributes']['action'] == 'update':
            # It does not react at issue status update
            # It only reacts at issue open|close|reopen
            return

    g.send_message('[\00306%s\x0f/\00313%s\x0f] \00315%s\x0f %s a pull request' % (server, repo, user_name, action))

    if number:
        g.send_message('\00314#%d\x0f %s%s' % (number, title, url))


# ===== MAIN ENTRY POINT ===== #
if __name__ == '__main__':
    g = G()
    g.daemon = True
    g.start()

    app.run(host='127.0.0.1', port=12147, debug=False)
