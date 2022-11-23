#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""On-Commit-Commands - a simple pubsub client that runs a command on commit activity"""

import asfpy.messaging
import asfpy.pubsub
import asfpy.syslog
import yaml
import subprocess
import socket
import pwd
import os
import getpass

print = asfpy.syslog.Printer(stdout=True, identity="occ")

ME = socket.gethostname()
TMPL_FAILURE = ME + """ failed to reconfigure due to the following error(s):

Return code: %d
Error message: %s

Please fix this error before service can resume.
"""


class CommandException(Exception):
    reason: str
    exitcode: int

    def __init__(self, reason, exitcode=0):
        self.reason = reason
        self.exitcode = exitcode


def run_as(username=getpass.getuser(), args=()):
    """ Run a command as a specific user """
    if not args:
        return   # Nothing to do? boooo
    try:
        pw_record = pwd.getpwnam(username)
    except KeyError:
        print("Could not execute command as %s - user not found??" % username)
        raise CommandException("Subprocess error - could not run command as non-existent user %s" % username, 7)
    user_name = pw_record.pw_name
    user_uid = pw_record.pw_uid
    user_gid = pw_record.pw_gid
    env = os.environ.copy()
    env['HOME'] = pw_record.pw_dir
    env['LOGNAME'] = user_name
    env['PWD'] = os.getcwd()
    env['USER'] = username
    print("Running command %s as user %s..." % (" ".join(args), username))
    try:
        process = subprocess.Popen(
            args, preexec_fn=change_user(user_uid, user_gid), cwd=os.getcwd(), env=env, stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, universal_newlines=True
        )
        stdout_data, stderr_data = process.communicate(timeout=30)
        if stdout_data:
            print(stdout_data)    
    except FileNotFoundError:
        print("Could not find script or executable to run, %s" % args[0])
        raise CommandException("Could not find executable '%s'" % args[0], 1)
    except PermissionError:
        print("Permission denied while trying to run %s" % args[0])
        raise CommandException("Got permission denied while trying to run '%s'" % args[0], 13)
    except subprocess.TimeoutExpired:
        print("Execution timed out")
        raise CommandException("Subprocess error - execution of command timed out", 2)
    except subprocess.SubprocessError:
        print("Subprocess error - likely could not change to user %s" % username)
        raise CommandException("Subprocess error - unable to change to user %s for running command (permission denied?)" % username, 7)
    if process.returncode != 0:
        print("on-commit command failed with exit code %d!" % process.returncode)
        raise CommandException(result[0].decode('utf-8'), process.returncode)


def change_user(user_uid, user_gid):
    def result():
        os.setgid(user_gid)
        os.setuid(user_uid)
    return result


def parse_commit(payload, config):
    if 'stillalive' in payload:  # Ping, Pong...
        return
    for subkey, subdata in config.get('subscriptions', {}).items():
        sub_topics = subdata.get('topics').split('/')
        sub_changedir = subdata.get('changedir')
        if all(topic in payload['pubsub_topics'] for topic in sub_topics):
            matches = True
            if sub_changedir:  # If we require changes within a certain dir in the repo..
                matches = False
                changed_files = []
                commit = payload.get('commit', {})
                if commit and 'changed' in commit:
                    changed_files = commit.get('changed').keys()  # svn syntax
                elif commit and 'files' in commit:
                    changed_files = commit.get('files')  # git syntax
                for change in changed_files:
                    if change.startswith(sub_changedir):
                        matches = True
                        break
            if matches:
                oncommit = subdata.get('oncommit')
                runas = subdata.get('runas', getpass.getuser())
                if oncommit:
                    cmd_args = []
                    if isinstance(oncommit, str) and oncommit:
                        cmd_args = [oncommit]
                    elif isinstance(oncommit, list):
                        for cmd_arg in oncommit:
                            if cmd_arg == "$branch":
                                cmd_arg = payload.get("commit", {}).get("ref", "??")
                            if cmd_arg == "$hash":
                                cmd_arg = payload.get("commit", {}).get("hash", "??")
                            cmd_args.append(cmd_arg)
                    if cmd_args:
                        print("Found a matching payload, preparing to execute command '%s':" % " ".join(cmd_args))
                        blamelist = subdata.get('blamelist')
                        blamesubject = subdata.get('blamesubject', "OCC execution failure")
                        try:
                            run_as(runas, cmd_args)
                            print("Command executed successfully")
                        except CommandException as e:
                            print("on-commit command failed with exit code %d!" % e.exitcode)
                            if blamelist:
                                print("Sending error details to %s" % blamelist)
                                asfpy.messaging.mail(recipient=blamelist, subject=blamesubject, message=TMPL_FAILURE % (e.exitcode, e.reason))
                    if subdata.get('skiprest') == True:
                        print("Skiprest enabled, skipping any other commands that may fire from this commit")
                        break


def main():
    print("Loading occ.yaml")
    cfg = yaml.safe_load(open('occ.yaml'))
    print("Connecting to pyPubSub at %s" % cfg['pubsub']['url'])
    pypubsub = asfpy.pubsub.Listener(cfg['pubsub']['url'])
    print("Connected, listening for events :-)")
    pypubsub.attach(lambda x: parse_commit(x, cfg), auth=(cfg['pubsub']['user'], cfg['pubsub']['pass']), raw=True)


if __name__ == "__main__":
    main()
